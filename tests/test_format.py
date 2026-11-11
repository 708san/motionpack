import json
import base64
import contextlib
import io
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import traceback
import unittest
import warnings
import zipfile
import zlib
from unittest import mock
from tests.jpeg_fixtures import jpeg_with_dnl_defined_height
ROOT=pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'tools'))
import validate as validator_module
from validate import validate
import package as package_module
from package import build

def png_ihdr(width,height,*,bad_crc=False):
    fields=struct.pack('>IIBBBBB',width,height,8,6,0,0,0)
    chunk=b'IHDR'+fields
    crc=zlib.crc32(chunk)&0xffffffff
    if bad_crc:
        crc^=1
    return b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+chunk+struct.pack('>I',crc)

def jpeg_header(width,height,*,sof=0xC0,extra=b''):
    components=b'\x01\x11\x00\x02\x11\x00\x03\x11\x00'
    frame=bytes((8,))+struct.pack('>HHB',height,width,3)+components
    return b'\xff\xd8'+extra+b'\xff'+bytes((sof,))+struct.pack('>H',len(frame)+2)+frame+b'\xff\xda'

def webp_chunk(kind,payload):
    return kind+struct.pack('<I',len(payload))+payload+(b'\0' if len(payload)&1 else b'')

def webp_with_chunks(chunks):
    body=b'WEBP'+b''.join(chunks)
    return b'RIFF'+struct.pack('<I',len(body))+body

def webp_header(width,height,*,kind=b'VP8X'):
    if kind==b'VP8X':
        payload=b'\0'*4+(width-1).to_bytes(3,'little')+(height-1).to_bytes(3,'little')
        bits=(width-1)|((height-1)<<14)
        chunks=webp_chunk(kind,payload)+webp_chunk(b'VP8L',b'\x2f'+bits.to_bytes(4,'little'))
    elif kind==b'VP8 ':
        payload=b'\0\0\0\x9d\x01\x2a'+struct.pack('<HH',width|0xC000,height|0x4000)
        chunks=webp_chunk(kind,payload)
    else:
        bits=(width-1)|((height-1)<<14)
        payload=b'\x2f'+bits.to_bytes(4,'little')
        chunks=webp_chunk(kind,payload)
    body=b'WEBP'+chunks
    return b'RIFF'+struct.pack('<I',len(body))+body

def webp_animation(width,height,frames,*,include_control=True):
    vp8x=b'\x02\0\0\0'+(width-1).to_bytes(3,'little')+(height-1).to_bytes(3,'little')
    chunks=webp_chunk(b'VP8X',vp8x)
    if include_control:
        chunks+=webp_chunk(b'ANIM',b'\0'*6)
    for x,y,frame_width,frame_height in frames:
        frame=(x//2).to_bytes(3,'little')+(y//2).to_bytes(3,'little')
        frame+=(frame_width-1).to_bytes(3,'little')+(frame_height-1).to_bytes(3,'little')
        frame+=b'\0'*4
        bits=(frame_width-1)|((frame_height-1)<<14)
        frame+=webp_chunk(b'VP8L',b'\x2f'+bits.to_bytes(4,'little'))
        chunks+=webp_chunk(b'ANMF',frame)
    body=b'WEBP'+chunks
    return b'RIFF'+struct.pack('<I',len(body))+body

def webp_extended(canvas_width,canvas_height,image_width,image_height,*,kind=b'VP8L',extra_chunks=()):
    canvas=b'\0'*4+(canvas_width-1).to_bytes(3,'little')+(canvas_height-1).to_bytes(3,'little')
    if kind==b'VP8 ':
        bitstream=b'\0\0\0\x9d\x01\x2a'+struct.pack('<HH',image_width|0x8000,image_height|0x4000)
    else:
        bits=(image_width-1)|((image_height-1)<<14)
        bitstream=b'\x2f'+bits.to_bytes(4,'little')
    chunks=webp_chunk(b'VP8X',canvas)+webp_chunk(kind,bitstream)+b''.join(extra_chunks)
    body=b'WEBP'+chunks
    return b'RIFF'+struct.pack('<I',len(body))+body

class FormatTests(unittest.TestCase):
    def test_raster_header_rejections_have_specific_value_error_subtype(self):
        self.assertTrue(issubclass(validator_module.RasterHeaderError, ValueError))
        for parser, malformed in (
            (validator_module.parse_png_dimensions, b"not PNG"),
            (validator_module.parse_jpeg_dimensions, b"not JPEG"),
            (validator_module.parse_webp_dimensions, b"not WebP"),
        ):
            with self.subTest(parser=parser.__name__), self.assertRaises(validator_module.RasterHeaderError):
                parser(malformed)
        with self.assertRaises(validator_module.RasterLimitError):
            validator_module.parse_webp_raster(
                webp_header(8193, 1), max_dimension=8192,
            )

    def test_simple_webp_enforces_header_parser_resource_limits(self):
        with self.assertRaisesRegex(validator_module.RasterLimitError, "dimension"):
            validator_module.parse_webp_raster(
                webp_header(8193, 1, kind=b"VP8 "), max_dimension=8192,
            )
        with self.assertRaisesRegex(validator_module.RasterLimitError, "dimension"):
            validator_module.parse_webp_raster(
                webp_header(8193, 1, kind=b"VP8L"), max_dimension=8192,
            )
        with self.assertRaisesRegex(validator_module.RasterLimitError, "pixel limit"):
            validator_module.parse_webp_raster(
                webp_header(4001, 4000, kind=b"VP8 "), max_pixels=16_000_000,
            )
        with self.assertRaisesRegex(validator_module.RasterLimitError, "pixel limit"):
            validator_module.parse_webp_raster(
                webp_header(4001, 4000, kind=b"VP8L"), max_pixels=16_000_000,
            )
        with self.assertRaisesRegex(validator_module.RasterLimitError, "total raster"):
            validator_module.parse_webp_raster(
                webp_header(8192, 1, kind=b"VP8 "), max_total_pixels=8191,
            )

    def test_examples_valid(self):
        for project in ('robot_demo','robot_ik_demo'):
            errors,m=validate(ROOT/'examples'/project)
            self.assertEqual(errors,[],errors)
    def test_validator_rejects_non_boolean_loop_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self._copy(tmp)
            manifest_path=project/'manifest.json'
            manifest=json.loads(manifest_path.read_text())
            manifest['clips']['idle']['loop']='false'
            manifest_path.write_text(json.dumps(manifest))
            errors,_=validate(project)
            self.assertTrue(any('invalid loop flag' in error for error in errors),errors)
    def test_validator_rejects_non_numeric_ik_weight(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self._copy(tmp)
            manifest_path=project/'manifest.json'
            manifest=json.loads(manifest_path.read_text())
            manifest['iks'][0]['weight']='bad'
            manifest_path.write_text(json.dumps(manifest))
            errors,_=validate(project)
            self.assertTrue(any('invalid IK weight' in error for error in errors),errors)
    def test_package_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive,preview=build(ROOT/'examples'/'robot_ik_demo',pathlib.Path(tmp)/'dist')
            self.assertTrue(preview.is_file())
            self.assertIn('MotionPackRig',preview.read_text(encoding='utf8'))
            with zipfile.ZipFile(archive) as z:
                self.assertIn('manifest.json',z.namelist())
                self.assertTrue(all(not p.startswith('/') and '..' not in pathlib.PurePosixPath(p).parts for p in z.namelist()))
                asset_data=z.read(json.loads(z.read('manifest.json'))['assets']['background'])
            self.assertIn(base64.b64encode(asset_data).decode('ascii'),preview.read_text(encoding='utf8'))
    @mock.patch.object(package_module, "decode_raster_assets_isolated")
    def test_default_package_does_not_start_raster_decoder(self, decode):
        with tempfile.TemporaryDirectory() as tmp:
            build(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "dist")
        decode.assert_not_called()

    @mock.patch.object(package_module, "decode_raster_assets_isolated", create=True)
    def test_opt_in_isolated_raster_preview_preserves_archive_source_bytes(self, decode):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._copy(tmp)
            manifest_path = project / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            original_assets = {}
            rewritten = {}
            for index, (asset_id, _old_path) in enumerate(manifest["assets"].items()):
                rel = f"assets/preview-{index}.png"
                payload = png_ihdr(1, 1)
                target = project / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                original_assets[rel] = payload
                rewritten[asset_id] = rel
            manifest["assets"] = rewritten
            manifest_path.write_text(json.dumps(manifest))
            decode.return_value = {
                "asset": package_module.DecodedRaster(
                    "PNG", 1, 1, bytes((20, 40, 60, 255))
                )
            }

            archive, preview = build(
                project, pathlib.Path(tmp) / "dist", isolated_raster_decode=True
            )

            self.assertEqual(decode.call_count, len(original_assets))
            with zipfile.ZipFile(archive) as packaged:
                for rel, expected in original_assets.items():
                    self.assertEqual(packaged.read(rel), expected)
            html = preview.read_text(encoding="utf-8")
            payload_match = re.search(
                r"window.__MOTIONPACK__=(\{.*?\});</script>", html, re.DOTALL
            )
            self.assertIsNotNone(payload_match)
            embedded = json.loads(payload_match.group(1))
            for asset in embedded["assets"].values():
                self.assertTrue(asset.startswith("data:image/png;base64,"))
                canonical_png = base64.b64decode(asset.split(",", 1)[1])
                self.assertTrue(canonical_png.startswith(b"\x89PNG\r\n\x1a\n"))

    @mock.patch.object(package_module, "_encode_rgba_png")
    @mock.patch.object(package_module, "decode_raster_assets_isolated")
    def test_opt_in_preview_size_limit_preserves_existing_outputs(self, decode, encode):
        class OversizedPreview:
            def __len__(self):
                return 64 * 1024 * 1024 + 1

        with tempfile.TemporaryDirectory() as tmp:
            project = self._copy(tmp)
            manifest_path = project / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            asset_id, old_rel = next(iter(manifest["assets"].items()))
            source = project / old_rel
            source.unlink()
            rel = "assets/preview.png"
            target = project / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(png_ihdr(1, 1))
            manifest["assets"][asset_id] = rel
            manifest_path.write_text(json.dumps(manifest))

            out = pathlib.Path(tmp) / "dist"
            out.mkdir()
            archive = out / (project.name + ".motionpack")
            preview = out / "preview.html"
            archive.write_bytes(b"previous archive")
            preview.write_bytes(b"previous preview")
            decode.return_value = {
                "asset": package_module.DecodedRaster(
                    "PNG", 1, 1, bytes((20, 40, 60, 255))
                )
            }
            encode.return_value = OversizedPreview()

            with self.assertRaisesRegex(ValueError, "64 MiB"):
                build(project, out, isolated_raster_decode=True)

            self.assertEqual(archive.read_bytes(), b"previous archive")
            self.assertEqual(preview.read_bytes(), b"previous preview")

    @mock.patch.object(package_module, "decode_raster_assets_isolated", create=True)
    def test_opt_in_decoder_failure_preserves_existing_outputs(self, decode):
        with tempfile.TemporaryDirectory() as tmp:
            project = self._copy(tmp)
            out = pathlib.Path(tmp) / "dist"
            out.mkdir()
            archive = out / (project.name + ".motionpack")
            preview = out / "preview.html"
            archive.write_bytes(b"previous archive")
            preview.write_bytes(b"previous preview")
            decode.side_effect = package_module.RasterDecodeError("injected decoder failure")

            with self.assertRaises(ValueError):
                build(project, out, isolated_raster_decode=True)

            self.assertEqual(archive.read_bytes(), b"previous archive")
            self.assertEqual(preview.read_bytes(), b"previous preview")

    def test_package_warns_on_secret_like_referenced_asset_without_rejecting_or_disclosing(self):
        examples=(
            ('GitHub token-like value','xghp_'+'A'*36),
            ('OpenAI key-like value','xsk-proj-'+'A'*24),
            ('AWS access-key ID-like value','xAKIA'+'A'*16),
            ('Slack token-like value','xoxb-'+'A'*24),
            ('Slack token-like value','xapp-'+'B'*24),
            ('Slack token-like value','xwfp-'+'C'*24),
            ('private-key header','-----BEGIN ENCRYPTED PRIVATE KEY-----'),
            ('private-key header','-----BEGIN PGP PRIVATE KEY BLOCK-----'),
        )
        for index,(category,secret) in enumerate(examples):
            with self.subTest(category=category,secret=secret[:12]), tempfile.TemporaryDirectory() as tmp:
                d=self._copy(tmp)
                asset_bytes=f'<svg xmlns="http://www.w3.org/2000/svg"><path fill="{secret}"/></svg>'.encode()
                asset=d/'assets'/'private_asset.svg'
                (d/'assets'/'background.svg').rename(asset)
                manifest_path=d/'manifest.json'
                manifest=json.loads(manifest_path.read_text())
                manifest['assets']['background']=asset.relative_to(d).as_posix()
                manifest_path.write_text(json.dumps(manifest))
                asset.write_bytes(asset_bytes)
                stderr=io.StringIO()
                with contextlib.redirect_stderr(stderr), warnings.catch_warnings():
                    warnings.simplefilter('error')
                    archive,preview=build(d,pathlib.Path(tmp)/f'dist{index}')
                message=stderr.getvalue()
                self.assertIn('MotionPack secret-like content',message)
                self.assertIn(category,message)
                self.assertIn('referenced asset #1',message)
                self.assertNotIn(secret,message)
                with zipfile.ZipFile(archive) as packaged:
                    self.assertEqual(packaged.read(asset.relative_to(d).as_posix()),asset_bytes)
                self.assertIn(base64.b64encode(asset_bytes).decode('ascii'),preview.read_text(encoding='utf8'))
    def test_strict_secret_scan_rejects_slack_like_referenced_asset_before_outputs(self):
        secret='xoxb-'+'S'*24
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            manifest_path=d/'manifest.json'
            manifest=json.loads(manifest_path.read_text())
            asset=d/'assets'/'credential.svg'
            old=d/manifest['assets']['background']
            old.rename(asset)
            manifest['assets']['background']=asset.relative_to(d).as_posix()
            asset.write_text(f'<svg xmlns="http://www.w3.org/2000/svg"><path fill="{secret}"/></svg>')
            manifest_path.write_text(json.dumps(manifest))
            out=pathlib.Path(tmp)/'strict-dist'
            with self.assertRaisesRegex(ValueError,'referenced asset #1') as raised:
                build(d,out,fail_on_secret_like=True)
            self.assertIn('Slack token-like value',str(raised.exception))
            self.assertNotIn(secret,str(raised.exception))
            self.assertFalse(out.exists())
    def test_package_warns_on_secret_like_manifest_metadata_without_disclosing(self):
        secret='ghp_'+'M'*36
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            manifest_path=d/'manifest.json'
            manifest=json.loads(manifest_path.read_text())
            manifest['notes']=secret
            manifest_path.write_text(json.dumps(manifest))
            stderr=io.StringIO()
            with contextlib.redirect_stderr(stderr):
                archive,_=build(d,pathlib.Path(tmp)/'dist')
            self.assertIn('package metadata',stderr.getvalue())
            self.assertIn('GitHub token-like value',stderr.getvalue())
            self.assertNotIn(secret,stderr.getvalue())
            with zipfile.ZipFile(archive) as packaged:
                self.assertIn(secret,packaged.read('manifest.json').decode())
    def test_strict_secret_scan_rejects_manifest_and_path_matches_before_outputs(self):
        secret='ghp_'+'N'*36
        cases=('manifest','asset path')
        for case in cases:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
                d=self._copy(tmp)
                manifest_path=d/'manifest.json'
                manifest=json.loads(manifest_path.read_text())
                if case=='manifest':
                    manifest['notes']=secret
                else:
                    old=d/manifest['assets']['background']
                    new=old.with_name(f'private_{secret}.svg')
                    old.rename(new)
                    manifest['assets']['background']=new.relative_to(d).as_posix()
                manifest_path.write_text(json.dumps(manifest))
                out=pathlib.Path(tmp)/'strict-dist'
                with self.assertRaisesRegex(ValueError,'package metadata') as raised:
                    build(d,out,fail_on_secret_like=True)
                self.assertIn('GitHub token-like value',str(raised.exception))
                self.assertNotIn(secret,str(raised.exception))
                self.assertFalse(out.exists())
    def test_invalid_secret_like_asset_path_is_redacted_from_errors(self):
        secret='ghp_'+'P'*36
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            manifest_path=d/'manifest.json'
            manifest=json.loads(manifest_path.read_text())
            manifest['assets']['missing']=f'assets/{secret}.svg'
            manifest_path.write_text(json.dumps(manifest))
            out=pathlib.Path(tmp)/'cli-output'
            with self.assertRaises(ValueError) as raised:
                build(d,out)
            self.assertNotIn(secret,str(raised.exception))
            result=subprocess.run(
                [sys.executable,str(ROOT/'tools'/'package.py'),str(d),'--out',str(out)],
                capture_output=True,text=True,check=False,
            )
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn(secret,result.stderr)
            self.assertFalse(out.exists())
    def test_secret_like_path_is_redacted_from_canonicalization_traceback(self):
        secret='ghp_'+'Q'*36
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            manifest_path=d/'manifest.json'
            manifest=json.loads(manifest_path.read_text())
            first=f'assets/{secret}.svg'
            second=f'Assets/{secret}.svg'
            first_file=d/first
            first_file.write_text('<svg><path d="M0 0"/></svg>')
            second_file=d/second
            second_file.parent.mkdir(parents=True,exist_ok=True)
            if not second_file.exists():
                second_file.write_bytes(first_file.read_bytes())
            manifest['assets']['background']=first
            manifest['assets']['duplicate']=second
            manifest_path.write_text(json.dumps(manifest))
            try:
                build(d,pathlib.Path(tmp)/'dist')
            except ValueError as error:
                self.assertNotIn(secret,str(error))
                self.assertNotIn(secret,''.join(traceback.format_exception(
                    type(error),error,error.__traceback__
                )))
                self.assertIsNone(error.__cause__)
                self.assertIsNone(error.__context__)
            else:
                self.fail('casefold-colliding paths should be rejected')
    def test_strict_secret_scan_fails_before_creating_or_replacing_outputs(self):
        secret='ghp_'+'B'*36
        for preexisting in (False,True):
            with self.subTest(preexisting=preexisting), tempfile.TemporaryDirectory() as tmp:
                d=self._copy(tmp)
                manifest_path=d/'manifest.json'
                manifest=json.loads(manifest_path.read_text())
                original=d/'assets'/'background.svg'
                asset=d/'assets'/'private_asset.svg'
                original.rename(asset)
                manifest['assets']['background']=asset.relative_to(d).as_posix()
                manifest_path.write_text(json.dumps(manifest))
                asset.write_text(
                    f'<svg xmlns="http://www.w3.org/2000/svg"><path fill="{secret}"/></svg>'
                )
                out=pathlib.Path(tmp)/'dist'
                package=out/(d.name+'.motionpack')
                preview=out/'preview.html'
                if preexisting:
                    out.mkdir()
                    package.write_bytes(b'previous archive')
                    preview.write_bytes(b'previous preview')
                with self.assertRaisesRegex(ValueError,'GitHub token-like value') as raised:
                    build(d,out,fail_on_secret_like=True)
                self.assertIn('referenced asset #1',str(raised.exception))
                self.assertNotIn(secret,str(raised.exception))
                if preexisting:
                    self.assertEqual(package.read_bytes(),b'previous archive')
                    self.assertEqual(preview.read_bytes(),b'previous preview')
                else:
                    self.assertFalse(out.exists())
    def test_strict_secret_scan_accepts_v01_and_v02_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            for version,project in (('0.1','robot_demo'),('0.2','robot_ik_demo')):
                with self.subTest(version=version):
                    archive,_=build(ROOT/'examples'/project,pathlib.Path(tmp)/version,fail_on_secret_like=True)
                    with zipfile.ZipFile(archive) as packaged:
                        manifest=json.loads(packaged.read('manifest.json'))
                    self.assertEqual(manifest['version'],version)
    def test_package_cli_strict_secret_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            clean_out=pathlib.Path(tmp)/'clean-dist'
            clean_result=subprocess.run(
                [sys.executable,str(ROOT/'tools'/'package.py'),str(ROOT/'examples'/'robot_demo'),
                 '--out',str(clean_out),'--fail-on-secret-like'],
                capture_output=True,text=True,check=False,
            )
            self.assertEqual(clean_result.returncode,0,clean_result.stderr)
            self.assertTrue((clean_out/'robot_demo.motionpack').is_file())
            self.assertTrue((clean_out/'preview.html').is_file())
            d=self._copy(tmp)
            secret='ghp_'+'C'*36
            manifest_path=d/'manifest.json'
            manifest=json.loads(manifest_path.read_text())
            original=d/'assets'/'background.svg'
            asset=d/'assets'/'private_asset.svg'
            original.rename(asset)
            manifest['assets']['background']=asset.relative_to(d).as_posix()
            manifest_path.write_text(json.dumps(manifest))
            asset.write_text(
                f'<svg xmlns="http://www.w3.org/2000/svg"><path fill="{secret}"/></svg>'
            )
            default_out=pathlib.Path(tmp)/'default-dist'
            default_result=subprocess.run(
                [sys.executable,str(ROOT/'tools'/'package.py'),str(d),'--out',str(default_out)],
                capture_output=True,text=True,check=False,
            )
            self.assertEqual(default_result.returncode,0,default_result.stderr)
            self.assertIn('GitHub token-like value',default_result.stderr)
            self.assertNotIn(secret,default_result.stderr)
            self.assertTrue((default_out/'project.motionpack').is_file())
            strict_out=pathlib.Path(tmp)/'strict-dist'
            strict_out.mkdir()
            strict_archive=strict_out/'project.motionpack'
            strict_preview=strict_out/'preview.html'
            strict_archive.write_bytes(b'previous archive')
            strict_preview.write_bytes(b'previous preview')
            result=subprocess.run(
                [sys.executable,str(ROOT/'tools'/'package.py'),str(d),'--out',str(strict_out),'--fail-on-secret-like'],
                capture_output=True,text=True,check=False,
            )
            self.assertNotEqual(result.returncode,0)
            self.assertIn('GitHub token-like value',result.stderr)
            self.assertIn('referenced asset #1',result.stderr)
            self.assertNotIn(secret,result.stderr)
            self.assertEqual(strict_archive.read_bytes(),b'previous archive')
            self.assertEqual(strict_preview.read_bytes(),b'previous preview')
    def _copy(self,tmp):
        d=pathlib.Path(tmp)/'project'
        shutil.copytree(ROOT/'examples'/'robot_ik_demo',d)
        return d
    def _add_png_assets(self,folder,asset_specs):
        manifest_path=folder/'manifest.json'
        manifest=json.loads(manifest_path.read_text())
        for aid,rel,width,height in asset_specs:
            target=folder/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(png_ihdr(width,height))
            manifest['assets'][aid]=rel
        manifest_path.write_text(json.dumps(manifest))
    def _add_raster_assets(self,folder,asset_specs):
        manifest_path=folder/'manifest.json'
        manifest=json.loads(manifest_path.read_text())
        for aid,rel,data in asset_specs:
            target=folder/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(data)
            manifest['assets'][aid]=rel
        manifest_path.write_text(json.dumps(manifest))
    def test_jpeg_dimension_preflight_variants_and_malformed_headers(self):
        marker_fill=b'\xff\xff\xe0\x00\x04ab'
        for data,expected in (
            (jpeg_header(320,240), (320,240)),
            (jpeg_header(320,240,sof=0xC2,extra=marker_fill), (320,240)),
        ):
            self.assertEqual(validator_module.parse_jpeg_dimensions(data),expected)
        for data in (b'\xff\xd8', b'\xff\xd8\xff\xda\x00\x02',
                     b'\xff\xd8\xff\xe0\xff\xff',
                     b'\xff\xd8\xff\xc0\x00\x08\x08\x00\x00\x00\x00\x01'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                validator_module.parse_jpeg_dimensions(data)
    def test_jpeg_zero_sof_height_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'dimensions'):
            validator_module.parse_jpeg_dimensions(jpeg_header(320,0))
        self.assertEqual(validator_module.parse_jpeg_dimensions(jpeg_header(320,240)),(320,240))
    def test_jpeg_dnl_defined_height_is_rejected(self):
        # DNL supplies the frame height inside scan data, which this preflight does not support.
        with self.assertRaisesRegex(ValueError,'dimensions'):
            validator_module.parse_jpeg_dimensions(jpeg_with_dnl_defined_height())
    def test_webp_dimension_preflight_variants_and_malformed_headers(self):
        for kind in (b'VP8X',b'VP8 ',b'VP8L'):
            with self.subTest(kind=kind):
                self.assertEqual(validator_module.parse_webp_dimensions(webp_header(320,240,kind=kind)),(320,240))
        self.assertEqual(validator_module.parse_webp_dimensions(webp_extended(320,240,320,240,kind=b'VP8 ')),(320,240))
        self.assertEqual(validator_module.parse_webp_dimensions(webp_header(1,2000,kind=b'VP8L')),(1,2000))
        for data in (b'RIFF\x00\x00\x00\x00WEBP', webp_header(10,10)[:-1],
                     webp_header(10,10)[:25]):
            with self.subTest(data=data), self.assertRaises(ValueError):
                validator_module.parse_webp_dimensions(data)
        bad_padding=bytearray(webp_header(10,10,kind=b'VP8L'))
        bad_padding[-1]=1
        with self.assertRaisesRegex(ValueError,'padding'):
            validator_module.parse_webp_dimensions(bytes(bad_padding))
        bad_extended_padding=bytearray(webp_header(10,10))
        bad_extended_padding[-1]=1
        with self.assertRaisesRegex(ValueError,'padding'):
            validator_module.parse_webp_dimensions(bytes(bad_extended_padding))
        bad_vp8l=bytearray(webp_header(10,10,kind=b'VP8L'))
        bad_vp8l[24]|=0x20
        with self.assertRaisesRegex(ValueError,'VP8L header'):
            validator_module.parse_webp_dimensions(bytes(bad_vp8l))
        small_vp8l=b'\x2f'+(0).to_bytes(4,'little')
        large_vp8l=b'\x2f'+(8192).to_bytes(4,'little')
        small_vp8=b'\0\0\0\x9d\x01\x2a'+struct.pack('<HH',1,1)
        large_vp8=b'\0\0\0\x9d\x01\x2a'+struct.pack('<HH',8193,1)
        for kind,first,second in ((b'VP8L',small_vp8l,large_vp8l),(b'VP8 ',small_vp8,large_vp8)):
            duplicate=webp_with_chunks([webp_chunk(kind,first),webp_chunk(kind,second)])
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError,'unexpected chunk'):
                validator_module.parse_webp_raster(duplicate)
        extended_duplicate=webp_extended(1,1,1,1,extra_chunks=[webp_chunk(b'VP8L',small_vp8l)])
        with self.assertRaisesRegex(ValueError,'unexpected WebP image chunk'):
            validator_module.parse_webp_raster(extended_duplicate)
    def test_animated_webp_counts_canvas_and_frame_pixels_and_checks_regions(self):
        animated=webp_animation(2,2,[(0,0,2,2),(0,0,2,2)])
        self.assertEqual(validator_module.parse_webp_raster(animated),(2,2,12))
        with self.assertRaisesRegex(ValueError,'canvas bounds'):
            validator_module.parse_webp_raster(webp_animation(2,2,[(2,0,1,1)]))
        with self.assertRaisesRegex(ValueError,'missing control or frame'):
            validator_module.parse_webp_raster(webp_animation(2,2,[],include_control=False))
        self.assertEqual(validator_module.parse_webp_raster(webp_animation(2,2000,[(0,0,1,2000)])),(2,2000,6000))
        mismatched=webp_extended(2,2,3,2)
        with self.assertRaisesRegex(ValueError,'VP8X canvas'):
            validator_module.parse_webp_raster(mismatched)
        bad_frame_padding=bytearray(webp_animation(2,2,[(0,0,1,1)]))
        bad_frame_padding[-1]=1
        with self.assertRaisesRegex(ValueError,'padding'):
            validator_module.parse_webp_raster(bytes(bad_frame_padding))
    def test_animated_webp_shared_pixel_budget_includes_canvas_and_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self._copy(tmp)
            self._add_raster_assets(project,[('animated','assets/animated.webp',webp_animation(2,2,[(0,0,2,2),(0,0,2,2)]))])
            errors,_=validate(project,max_raster_dimension=2,max_raster_pixels=4,max_total_raster_pixels=12)
            self.assertEqual(errors,[],errors)
            errors,_=validate(project,max_raster_dimension=2,max_raster_pixels=4,max_total_raster_pixels=11)
            self.assertTrue(any('total raster pixel budget exceeded' in error for error in errors),errors)
    def test_jpeg_webp_dimension_limits_and_extension_classification(self):
        cases=(('large.jpg',jpeg_header(8193,1),'JPEG dimension limit'),
               ('large.jpeg',jpeg_header(4001,4000),'JPEG pixel limit'),
               ('large.webp',webp_header(8193,1),'WebP dimension limit'),
               ('large.WEBP',webp_header(4001,4000),'WebP pixel limit'),
               ('tall.webp',webp_header(1,8193,kind=b'VP8L'),'WebP dimension limit'))
        for name,data,message in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                project=self._copy(tmp)
                self._add_raster_assets(project,[(name,name if name.startswith('assets/') else 'assets/'+name,data)])
                errors,_=validate(project)
                self.assertTrue(any(message in error for error in errors),errors)
        with tempfile.TemporaryDirectory() as tmp:
            project=self._copy(tmp)
            self._add_raster_assets(project,[('misnamed','assets/misnamed.png',jpeg_header(9000,1))])
            errors,_=validate(project)
            self.assertTrue(any('invalid PNG header' in error for error in errors),errors)

    def test_legacy_png_limit_arguments_alias_shared_raster_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self._copy(tmp)
            self._add_raster_assets(project,[('webp','assets/image.webp',webp_header(2,2,kind=b'VP8L'))])
            errors,_=validate(project,max_png_dimension=1)
            self.assertTrue(any('WebP dimension limit exceeded' in error for error in errors),errors)
            errors,_=validate(project,max_png_dimension=1,max_raster_dimension=2)
            self.assertEqual(errors,[],errors)
    def test_jpeg_webp_dimension_limits_accept_exact_boundaries(self):
        for aid,rel,data in (
            ('jpeg_edge','assets/jpeg_edge.jpg',jpeg_header(8192,1)),
            ('jpeg_pixels','assets/jpeg_pixels.jpeg',jpeg_header(4000,4000)),
            ('webp_edge','assets/webp_edge.webp',webp_header(1,8192,kind=b'VP8 ')),
            ('webp_pixels','assets/webp_pixels.webp',webp_header(4000,4000,kind=b'VP8L')),
        ):
            with self.subTest(asset=aid), tempfile.TemporaryDirectory() as tmp:
                project=self._copy(tmp)
                self._add_raster_assets(project,[(aid,rel,data)])
                errors,_=validate(project)
                self.assertEqual(errors,[],errors)
    def test_mixed_raster_aggregate_limit_counts_distinct_files_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self._copy(tmp)
            self._add_png_assets(project,[('png','assets/one.png',2,2),('png_alias','assets/one.png',2,2)])
            manifest_path=project/'manifest.json'
            manifest=json.loads(manifest_path.read_text())
            manifest['assets']['jpeg']='assets/two.jpg'
            manifest['assets']['webp']='assets/three.webp'
            (project/'assets'/'two.jpg').write_bytes(jpeg_header(2,2))
            (project/'assets'/'three.webp').write_bytes(webp_header(2,2))
            manifest_path.write_text(json.dumps(manifest))
            errors,_=validate(project,max_raster_dimension=2,max_raster_pixels=4,max_total_raster_pixels=12)
            self.assertEqual(errors,[],errors)
            errors,_=validate(project,max_raster_dimension=2,max_raster_pixels=4,max_total_raster_pixels=11)
            self.assertTrue(any('total raster pixel budget exceeded' in error for error in errors),errors)
    def test_reject_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            m=json.loads((d/'manifest.json').read_text())
            m['assets']['evil']='../bad.svg'
            (d/'manifest.json').write_text(json.dumps(m))
            errors,_=validate(d)
            self.assertTrue(any('unsafe path' in x for x in errors),errors)
    def test_rejects_drive_qualified_asset_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            manifest=json.loads((d/'manifest.json').read_text())
            manifest['assets']['drive_path']='C:/private.svg'
            (d/'manifest.json').write_text(json.dumps(manifest))
            errors,_=validate(d)
            self.assertTrue(any('unsafe path' in error for error in errors),errors)
    def test_png_dimension_and_per_image_pixel_limits(self):
        cases=(
            ('edge_at_limit',8192,1,True),
            ('edge_height_at_limit',1,8192,True),
            ('edge_over_limit',8193,1,False),
            ('edge_height_over_limit',1,8193,False),
            ('pixels_at_limit',4000,4000,True),
            ('pixels_over_limit',4001,4000,False),
        )
        for aid,width,height,accepted in cases:
            with self.subTest(aid=aid), tempfile.TemporaryDirectory() as tmp:
                project=self._copy(tmp)
                self._add_png_assets(project,[(aid,'assets/'+aid+'.PNG',width,height)])
                errors,_=validate(project)
                if accepted:
                    self.assertEqual(errors,[],errors)
                else:
                    self.assertTrue(any('PNG' in error and ('dimension' in error or 'pixel' in error) for error in errors),errors)
                    with self.assertRaisesRegex(ValueError,'PNG'):
                        build(project,pathlib.Path(tmp)/'dist')
    def test_total_png_pixel_limit_counts_unique_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self._copy(tmp)
            specs=[(f'large_{i}',f'assets/large_{i}.png',4000,4000) for i in range(4)]
            self._add_png_assets(project,specs)
            errors,_=validate(project)
            self.assertEqual(errors,[],errors)
            self._add_png_assets(project,[('fifth','assets/large_4.png',4000,4000)])
            errors,_=validate(project)
            self.assertTrue(any('total raster pixel budget exceeded' in error for error in errors),errors)

        with tempfile.TemporaryDirectory() as tmp:
            project=self._copy(tmp)
            specs=[(f'alias_{i}','assets/shared.png',4000,4000) for i in range(5)]
            self._add_png_assets(project,specs)
            errors,_=validate(project,max_total_png_pixels=16_000_000)
            self.assertEqual(errors,[],errors)

    def test_rejects_invalid_png_ihdr(self):
        valid=png_ihdr(10,10)
        wrong_chunk=bytearray(valid)
        wrong_chunk[12:16]=b'IDAT'
        wrong_length=bytearray(valid)
        wrong_length[8:12]=struct.pack('>I',12)
        bad_headers=(
            b'not a png',valid[:32],bytes(wrong_chunk),bytes(wrong_length),
            png_ihdr(0,10),png_ihdr(10,0),png_ihdr(10,10,bad_crc=True),
        )
        for index,data in enumerate(bad_headers):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as tmp:
                project=self._copy(tmp)
                (project/'assets'/'bad.png').write_bytes(data)
                manifest=json.loads((project/'manifest.json').read_text())
                manifest['assets']['bad']='assets/bad.png'
                (project/'manifest.json').write_text(json.dumps(manifest))
                errors,_=validate(project)
                self.assertTrue(any('invalid PNG header' in error for error in errors),errors)
    def test_png_ihdr_rejects_dimensions_above_png_spec_even_with_permissive_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self._copy(tmp)
            self._add_png_assets(project,[('too_wide','assets/too_wide.png',0x80000000,1)])
            errors,_=validate(
                project,
                max_png_dimension=0xFFFFFFFF,
                max_png_pixels=0xFFFFFFFF,
                max_total_png_pixels=0xFFFFFFFF,
            )
            self.assertTrue(any('invalid PNG header' in error for error in errors),errors)
    def test_raster_parser_is_selected_by_filename_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self._copy(tmp)
            self._add_png_assets(project,[('png_bytes_jpg_path','assets/misnamed.jpg',8193,1)])
            errors,_=validate(project)
            self.assertTrue(any('invalid JPEG header' in error for error in errors),errors)
    def test_png_header_preflight_does_not_validate_image_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self._copy(tmp)
            self._add_png_assets(project,[('header_only','assets/header_only.png',1,1)])
            errors,_=validate(project)
            self.assertEqual(errors,[],errors)
    def test_validate_allows_noncanonical_asset_path_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            m=json.loads((d/'manifest.json').read_text())
            m['assets']['dot_alias']='assets/./background.svg'
            m['assets']['separator_alias']='assets//background.svg'
            (d/'manifest.json').write_text(json.dumps(m))
            errors,_=validate(d)
            self.assertEqual(errors,[],errors)
    def test_validate_preserves_project_relative_asset_paths_outside_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            shutil.copyfile(d/'assets'/'background.svg',d/'shared.svg')
            manifest=json.loads((d/'manifest.json').read_text())
            manifest['assets']['shared']='shared.svg'
            (d/'manifest.json').write_text(json.dumps(manifest))
            errors,_=validate(d)
            self.assertEqual(errors,[],errors)
            archive,_=build(d,pathlib.Path(tmp)/'dist')
            with zipfile.ZipFile(archive) as packaged:
                self.assertIn('shared.svg',packaged.namelist())
    def test_package_rejects_casefold_asset_path_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            shutil.copyfile(d/'assets'/'background.svg',d/'assets'/'ß.svg')
            shutil.copyfile(d/'assets'/'background.svg',d/'assets'/'ss.svg')
            m=json.loads((d/'manifest.json').read_text())
            m['assets']['case_alias_a']='assets/ß.svg'
            m['assets']['case_alias_b']='assets/ss.svg'
            (d/'manifest.json').write_text(json.dumps(m))
            errors,_=validate(d)
            self.assertEqual(errors,[],errors)
            with self.assertRaisesRegex(ValueError,'casefold collision'):
                build(d,pathlib.Path(tmp)/'dist')
    def test_package_rejects_unicode_normalization_asset_path_collision(self):
        manifest={"assets":{"composed":"assets/é.svg","decomposed":"assets/e\u0301.svg"}}
        with self.assertRaisesRegex(ValueError,'casefold collision'):
            package_module.canonicalize_manifest(manifest)
    def test_package_rejects_casefold_colliding_path_components(self):
        cases=(
            {"upper_root":"Assets/a.svg","lower_root":"assets/b.svg"},
            {"upper":"assets/A/x.svg","lower":"assets/a/y.svg"},
        )
        for assets in cases:
            with self.subTest(assets=assets), self.assertRaisesRegex(ValueError,'path component collision'):
                package_module.canonicalize_manifest({"assets":assets})
    def test_canonicalize_manifest_redacts_secret_like_collision_paths(self):
        secret='ghp_'+'R'*36
        cases=(
            ({'first':f'assets/{secret}.svg','second':f'Assets/{secret}.svg'},'casefold collision'),
            ({'first':f'assets/{secret}/one.svg','second':f'Assets/{secret}/two.svg'},'path component collision'),
        )
        for assets,message in cases:
            with self.subTest(message=message):
                try:
                    package_module.canonicalize_manifest({'assets':assets})
                except ValueError as error:
                    self.assertIn(message,str(error))
                    self.assertNotIn(secret,str(error))
                    rendered=''.join(traceback.format_exception(
                        type(error),error,error.__traceback__
                    ))
                    self.assertNotIn(secret,rendered)
                else:
                    self.fail('colliding paths should be rejected')
    def test_reject_svg_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            (d/'assets'/'head.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"><image href="https://evil.example/a.png"/></svg>')
            errors,_=validate(d)
            self.assertTrue(any('forbidden SVG' in x or 'unsafe SVG' in x for x in errors),errors)
    def _validate_svg(self,svg):
        return self._validate_svg_version(svg, '0.2')
    def _validate_svg_version(self,svg,version):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            manifest_path=d/'manifest.json'
            manifest=json.loads(manifest_path.read_text())
            manifest['version']=version
            manifest_path.write_text(json.dumps(manifest))
            (d/'assets'/'background.svg').write_text(svg)
            return validate(d)[0]
    def test_v03_requires_bounded_numeric_svg_dimensions_and_preserves_legacy(self):
        bare='<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'
        for version in ('0.1','0.2'):
            self.assertEqual(self._validate_svg_version(bare,version),[])
        errors=self._validate_svg_version(bare,'0.3')
        self.assertTrue(any('SVG' in error and 'width' in error for error in errors),errors)

    def test_v03_svg_dimension_values_and_limits(self):
        cases=(
            ('valid decimal px','<svg width="10.5px" height="4"/>',True,None),
            ('small positive decimal','<svg width="0.0001" height="4"/>',True,None),
            ('missing width','<svg height="4"/>',False,'width'),
            ('missing height','<svg width="4"/>',False,'height'),
            ('zero','<svg width="0" height="4"/>',False,'width'),
            ('negative','<svg width="-1" height="4"/>',False,'width'),
            ('percentage','<svg width="100%" height="4"/>',False,'width'),
            ('exponent','<svg width="1e2" height="4"/>',False,'width'),
            ('leading whitespace','<svg width=" 4" height="4"/>',False,'width'),
            ('uppercase unit','<svg width="4PX" height="4"/>',False,'width'),
            ('non-px unit','<svg width="4pt" height="4"/>',False,'width'),
            ('oversized lexical value','<svg width="'+'1'*65+'" height="4"/>',False,'width'),
            ('edge boundary','<svg width="8192" height="1"/>',True,None),
            ('edge over','<svg width="8193" height="1"/>',False,'dimension limit'),
            ('area boundary','<svg width="4000" height="4000"/>',True,None),
            ('area over','<svg width="4001" height="4000"/>',False,'pixel limit'),
        )
        for name,root,accepted,message in cases:
            svg=root.replace('/>', '><path d="M0 0"/></svg>')
            with self.subTest(name=name):
                errors=self._validate_svg_version(svg,'0.3')
                if accepted:
                    self.assertEqual(errors,[],errors)
                else:
                    self.assertTrue(any(message in error for error in errors),errors)
    def test_v03_svg_limits_cannot_be_raised_above_format_maxima(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self._copy(tmp)
            with self.assertRaisesRegex(ValueError,'cannot exceed v0.3 maxima'):
                validate(project,max_svg_dimension=8193)
            with self.assertRaisesRegex(ValueError,'cannot exceed v0.3 maxima'):
                validate(project,max_svg_pixels=16_000_001)
    def test_packager_builds_v03_with_explicit_svg_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self._copy(tmp)
            manifest_path=project/'manifest.json'
            manifest=json.loads(manifest_path.read_text())
            manifest['version']='0.3'
            manifest_path.write_text(json.dumps(manifest))
            for asset_path in set(manifest['assets'].values()):
                if asset_path.lower().endswith('.svg'):
                    path=project/asset_path
                    svg=path.read_text()
                    svg=re.sub(r'(<svg\b[^>]*?)\swidth="[^"]*"',r'\1',svg,count=1)
                    svg=re.sub(r'(<svg\b[^>]*?)\sheight="[^"]*"',r'\1',svg,count=1)
                    svg=svg.replace('<svg','<svg width="800" height="1000"',1)
                    path.write_text(svg)
            archive,_=build(project,pathlib.Path(tmp)/'dist')
            with zipfile.ZipFile(archive) as packaged:
                self.assertEqual(json.loads(packaged.read('manifest.json'))['version'],'0.3')
    def test_packaged_preview_embeds_evaluator_before_viewer(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=self._copy(tmp)
            _,preview=build(project,pathlib.Path(tmp)/'dist')
            html=preview.read_text()
            evaluator_marker='Stateless MotionPack pose evaluator'
            controller_marker='Host-driven MotionPack playback state'
            viewer_marker='experimental offline Canvas2D renderer'
            self.assertIn(evaluator_marker,html)
            self.assertIn(controller_marker,html)
            self.assertIn(viewer_marker,html)
            self.assertLess(html.index(evaluator_marker),html.index(viewer_marker))
            self.assertLess(html.index(controller_marker),html.index(viewer_marker))
    def test_svg_allows_local_gradient_reference(self):
        errors=self._validate_svg('<svg xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="paint"><stop offset="0" stop-color="red"/></linearGradient></defs><path fill="url(#paint)" d="M0 0"/></svg>')
        self.assertEqual(errors,[],errors)
    def test_svg_tag_specific_attribute_allowlist(self):
        supported=(
            '<svg width="10" height="10" viewBox="0 0 10 10"><g>'
            '<path d="M0 0L1 1" fill="red" stroke="blue" stroke-width="1" opacity=".5"/>'
            '<rect x="0" y="0" width="1" height="1" rx=".1" ry=".1" fill="red"/>'
            '<circle cx="1" cy="1" r="1" fill="red"/>'
            '<ellipse cx="1" cy="1" rx="1" ry=".5" fill="red"/>'
            '<line x1="0" y1="0" x2="1" y2="1" stroke="red"/>'
            '<polyline points="0,0 1,1" stroke="red"/>'
            '<polygon points="0,0 1,0 1,1" fill="red"/>'
            '<defs><linearGradient id="paint"><stop offset="0" stop-color="red"/></linearGradient>'
            '<radialGradient id="radial"><stop offset="0" stop-color="white"/></radialGradient></defs>'
            '<path d="M0 0L1 1" fill="url(#paint)"/><circle cx="1" cy="1" r="1" fill="url(#radial)"/></g></svg>'
        )
        self.assertEqual(self._validate_svg(supported),[])
        rejected=(
            '<path d="M0 0" vendor-feature="x"/>',
            '<path d="M0 0" filter="blur(2px)"/>',
            '<path d="M0 0" mask="none"/>',
            '<path d="M0 0" cx="1"/>',
            '<path d="M0 0" id="not-a-gradient"/>',
            '<g transform="translate(1 1)"/>',
            '<svg preserveAspectRatio="xMidYMid meet"/>',
            '<svg viewbox="0 0 1 1"/>',
        )
        for element in rejected:
            with self.subTest(element=element):
                errors=self._validate_svg(f'<svg xmlns="http://www.w3.org/2000/svg">{element}</svg>')
                self.assertTrue(any('unsupported SVG attribute' in error for error in errors),errors)
    def test_svg_rejects_noncanonical_element_names_and_text_tail(self):
        cases=(
            ('<SVG xmlns="http://www.w3.org/2000/svg"/>','root element must be svg'),
            ('<svg xmlns="http://www.w3.org/2000/svg"><PATH d="M0 0"/></svg>','forbidden SVG element'),
            ('<svg xmlns="http://www.w3.org/2000/svg"><g><path d="M0 0"/>unexpected</g></svg>','SVG text content is forbidden'),
        )
        for svg,message in cases:
            with self.subTest(svg=svg):
                errors=self._validate_svg(svg)
                self.assertTrue(any(message in error for error in errors),errors)
        self.assertEqual(self._validate_svg('<svg xmlns="http://www.w3.org/2000/svg"><g><path d="M0 0"/> \n</g></svg>'),[])
    def test_svg_rejects_remote_or_unresolved_css_references(self):
        for value in ('url(https://example.test/a.svg#paint)','url(//example.test/a.svg)','url(file:///tmp/a.svg)','url(data:image/svg+xml,x)','url(#missing)','url(#paint) red'):
            with self.subTest(value=value):
                errors=self._validate_svg(f'<svg xmlns="http://www.w3.org/2000/svg"><path fill="{value}" d="M0 0"/></svg>')
                self.assertTrue(any('SVG' in error for error in errors),errors)
    def test_svg_rejects_css_evasion_and_non_paint_urls(self):
        for attr,value in (('fill','u/**/rl(#paint)'),('fill',r'url(\23 paint)'),('filter','url(#paint)')):
            with self.subTest(attr=attr,value=value):
                errors=self._validate_svg(f'<svg xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="paint"/></defs><path {attr}="{value}" d="M0 0"/></svg>')
                self.assertTrue(any('SVG' in error for error in errors),errors)
    def test_svg_rejects_doctype_entities_bad_namespace_and_xml_base(self):
        cases=(
            '<!DOCTYPE svg [<!ENTITY x "boom">]><svg xmlns="http://www.w3.org/2000/svg"><title>&x;</title></svg>',
            '<?xml-stylesheet href="https://example.test/style.css"?><svg xmlns="http://www.w3.org/2000/svg"/>',
            '<svg xmlns="urn:attacker"><path d="M0 0"/></svg>',
            '<svg xmlns="http://www.w3.org/2000/svg" xml:base="https://example.test/"><path d="M0 0"/></svg>',
        )
        for svg in cases:
            with self.subTest(svg=svg):
                errors=self._validate_svg(svg)
                self.assertTrue(any('SVG' in error for error in errors),errors)
    def test_svg_rejects_excessive_depth_and_attribute_size(self):
        deep='<svg xmlns="http://www.w3.org/2000/svg">'+'<g>'*128+'<path d="M0 0"/>'+'</g>'*128+'</svg>'
        huge='<svg xmlns="http://www.w3.org/2000/svg"><path fill="'+'x'*(64*1024+1)+'"/></svg>'
        many='<svg xmlns="http://www.w3.org/2000/svg">'+'<path/>'*10000+'</svg>'
        attrs=' '.join(f'a{i}="x"' for i in range(129))
        too_many_attrs=f'<svg xmlns="http://www.w3.org/2000/svg"><path {attrs}/></svg>'
        for svg,message in ((deep,'nesting exceeds maximum'),
                            (huge,'attribute value exceeds maximum size'),
                            (many,'element count exceeds maximum'),
                            (too_many_attrs,'attribute count exceeds maximum')):
            with self.subTest(size=len(svg),message=message), self.assertRaisesRegex(ValueError,message):
                validator_module.parse_svg(svg.encode())
    def test_svg_asset_aliases_are_parsed_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            manifest=json.loads((d/'manifest.json').read_text())
            manifest['assets']['background_alias']=manifest['assets']['background']
            (d/'manifest.json').write_text(json.dumps(manifest))
            unique_svg_paths={
                (d/pathlib.PurePosixPath(path)).resolve()
                for path in manifest['assets'].values()
                if pathlib.PurePosixPath(path).suffix.lower()=='.svg'
            }
            original=validator_module.parse_svg
            with mock.patch.object(validator_module,'parse_svg',wraps=original) as parser:
                errors,_=validate(d)
            self.assertEqual(errors,[],errors)
            self.assertEqual(parser.call_count,len(unique_svg_paths))
    def test_packager_asset_snapshot_respects_total_size_budget_before_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            sink={}
            with mock.patch.object(validator_module,'MAX_TOTAL_ASSETS',0), \
                 mock.patch.object(validator_module,'read_stable_asset') as snapshot_reader:
                errors,_=validate(d,asset_data_sink=sink)
            self.assertTrue(any('total asset budget exceeded' in error for error in errors),errors)
            snapshot_reader.assert_not_called()
            self.assertEqual(sink,{})
    def test_svg_rejects_malformed_xml_and_duplicate_gradient_ids(self):
        cases=(
            '',
            '<svg xmlns="http://www.w3.org/2000/svg"><path></svg>',
            '<svg xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="paint"/><radialGradient id="paint"/></defs><path fill="url(#paint)"/></svg>',
        )
        for svg in cases:
            with self.subTest(svg=svg):
                errors=self._validate_svg(svg)
                self.assertTrue(any('SVG' in error for error in errors),errors)
    def test_reject_infinite(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            m=json.loads((d/'manifest.json').read_text())
            m['nodes'][0]['x']=float('inf')
            (d/'manifest.json').write_text(json.dumps(m))
            with self.assertRaises(ValueError):
                validate(d)  # JSON Infinity is rejected before semantic checks
    def test_reject_parent_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            m=json.loads((d/'manifest.json').read_text())
            m['nodes'][1]['parent']='body'
            (d/'manifest.json').write_text(json.dumps(m))
            errors,_=validate(d)
            self.assertTrue(any('parent cycle' in x for x in errors),errors)
    def test_reject_non_positive_node_and_variant_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            m=json.loads((d/'manifest.json').read_text())
            m['nodes'][0]['width']=-1
            m['variants']['form_b']['nodes']['body']['height']=-2
            (d/'manifest.json').write_text(json.dumps(m))
            errors,_=validate(d)
            self.assertTrue(any('invalid width for bg' in x for x in errors),errors)
            self.assertTrue(any('invalid height' in x and 'variant' in x for x in errors),errors)
    def test_package_deduplicates_asset_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            m=json.loads((d/'manifest.json').read_text())
            m['assets']['background_alias']=m['assets']['background']
            m['assets']['background_dot_alias']='assets/./background.svg'
            m['assets']['background_separator_alias']='assets//background.svg'
            (d/'manifest.json').write_text(json.dumps(m))
            original_manifest=(d/'manifest.json').read_text()
            errors,manifest=validate(d)
            self.assertEqual(errors,[],errors)
            archive,_=build(d,pathlib.Path(tmp)/'dist')
            self.assertEqual((d/'manifest.json').read_text(),original_manifest)
            with zipfile.ZipFile(archive) as z:
                names=z.namelist()
                self.assertEqual(len(names),len(set(names)),names)
                packaged_manifest=json.loads(z.read('manifest.json'))
                self.assertEqual(packaged_manifest['assets']['background'],manifest['assets']['background'])
                self.assertEqual(packaged_manifest['assets']['background_alias'],manifest['assets']['background'])
                self.assertEqual(packaged_manifest['assets']['background_dot_alias'],manifest['assets']['background'])
                self.assertEqual(packaged_manifest['assets']['background_separator_alias'],manifest['assets']['background'])
                entry=manifest['assets']['background']
                self.assertIn(entry,names)
                self.assertEqual(names.count(entry),1,names)
                self.assertEqual(set(packaged_manifest['assets'].values()), set(names)-{'manifest.json'})
    def test_reject_deep_json_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=pathlib.Path(tmp)/'project'
            d.mkdir()
            (d/'manifest.json').write_text('['+'['*1100+'0'+']'*1100+']')
            with self.assertRaisesRegex(ValueError,'nesting'):
                validate(d)
            result=subprocess.run(
                [sys.executable,str(ROOT/'tools'/'validate.py'),str(d)],
                capture_output=True,text=True,check=False,
            )
            self.assertNotEqual(result.returncode,0)
            self.assertIn('INVALID:',result.stderr)
            self.assertNotIn('Traceback',result.stderr)
    def test_reject_huge_integer_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            m=json.loads((d/'manifest.json').read_text())
            m['nodes'][0]['width']=10**1000
            (d/'manifest.json').write_text(json.dumps(m))
            errors,_=validate(d)
            self.assertTrue(any('invalid width for bg' in x for x in errors),errors)
            result=subprocess.run(
                [sys.executable,str(ROOT/'tools'/'validate.py'),str(d)],
                capture_output=True,text=True,check=False,
            )
            self.assertNotEqual(result.returncode,0)
            self.assertIn('INVALID',result.stderr)
            self.assertNotIn('Traceback',result.stderr)
    def test_reject_symlink_loop_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            (d/'assets'/'loop.svg').symlink_to('loop.svg')
            m=json.loads((d/'manifest.json').read_text())
            m['assets']['loop']='assets/loop.svg'
            (d/'manifest.json').write_text(json.dumps(m))
            errors,_=validate(d)
            self.assertTrue(any('unable to resolve asset' in x for x in errors),errors)
            result=subprocess.run(
                [sys.executable,str(ROOT/'tools'/'validate.py'),str(d)],
                capture_output=True,text=True,check=False,
            )
            self.assertNotEqual(result.returncode,0)
            self.assertIn('INVALID',result.stderr)
            self.assertNotIn('Traceback',result.stderr)
    def test_reject_project_root_symlink_loop_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=pathlib.Path(tmp)/'project-loop'
            d.symlink_to('project-loop',target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'project root'):
                validate(d)
            with self.assertRaisesRegex(ValueError,'project root'):
                build(d,pathlib.Path(tmp)/'dist')
            result=subprocess.run(
                [sys.executable,str(ROOT/'tools'/'validate.py'),str(d)],
                capture_output=True,text=True,check=False,
            )
            self.assertNotEqual(result.returncode,0)
            self.assertIn('INVALID:',result.stderr)
            self.assertNotIn('Traceback',result.stderr)
    def test_package_excludes_source_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            (d/'.env').write_text('TOKEN=do-not-package')
            (d/'private-prompt.txt').write_text('private prompt')
            (d/'source'/'.env').write_text('TOKEN=do-not-package')
            (d/'source'/'private-prompt.txt').write_text('private prompt')
            source_svg=d/'source'/'private.svg'
            shutil.copyfile(d/'assets'/'background.svg',source_svg)
            source_before=source_svg.read_bytes()
            archive,preview=build(d,pathlib.Path(tmp)/'dist')
            with zipfile.ZipFile(archive) as z:
                names=z.namelist()
                self.assertTrue(all(not name.startswith('source/') for name in names),names)
                self.assertEqual(set(names),{'manifest.json',*json.loads((d/'manifest.json').read_text())['assets'].values()})
                self.assertNotIn(b'do-not-package',b''.join(z.read(name) for name in names))
            preview_text=preview.read_text(encoding='utf-8')
            self.assertNotIn('do-not-package',preview_text)
            self.assertNotIn('private prompt',preview_text)
            self.assertEqual(source_svg.read_bytes(),source_before)
    def test_rejects_source_directory_as_runtime_asset(self):
        for raw_path in ('source/private.svg','source//private.svg','SOURCE/private.svg'):
            with self.subTest(raw_path=raw_path), tempfile.TemporaryDirectory() as tmp:
                d=self._copy(tmp)
                (d/'source').mkdir(exist_ok=True)
                shutil.copyfile(d/'assets'/'background.svg',d/'source'/'private.svg')
                manifest=json.loads((d/'manifest.json').read_text())
                manifest['assets']['private']=raw_path
                (d/'manifest.json').write_text(json.dumps(manifest))
                errors,_=validate(d)
                self.assertTrue(any('source directory cannot be a runtime asset' in error for error in errors),errors)
                with self.assertRaisesRegex(ValueError,'source directory cannot be a runtime asset'):
                    build(d,pathlib.Path(tmp)/'dist')
    def test_rejects_symlinked_asset_path_component(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            (d/'source').mkdir(exist_ok=True)
            shutil.copyfile(d/'assets'/'background.svg',d/'source'/'private.svg')
            try:
                (d/'source_alias').symlink_to(d/'source',target_is_directory=True)
            except (NotImplementedError,OSError) as exc:
                self.skipTest('directory symlinks unavailable: '+str(exc))
            manifest=json.loads((d/'manifest.json').read_text())
            manifest['assets']['private']='source_alias/private.svg'
            (d/'manifest.json').write_text(json.dumps(manifest))
            errors,_=validate(d)
            self.assertTrue(any('symlink' in error.lower() for error in errors),errors)
            with self.assertRaisesRegex(ValueError,'symlink'):
                build(d,pathlib.Path(tmp)/'dist')
    def test_rejects_symlinked_asset_directory_outside_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            try:
                (d/'assets_alias').symlink_to(d/'assets',target_is_directory=True)
            except (NotImplementedError,OSError) as exc:
                self.skipTest('directory symlinks unavailable: '+str(exc))
            manifest=json.loads((d/'manifest.json').read_text())
            manifest['assets']['alias']='assets_alias/background.svg'
            (d/'manifest.json').write_text(json.dumps(manifest))
            errors,_=validate(d)
            self.assertTrue(any('symlink in asset path' in error for error in errors),errors)
    def test_package_uses_validated_asset_bytes_after_path_swap(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            asset=d/'assets'/'background.svg'
            original_bytes=asset.read_bytes()
            canary=pathlib.Path(tmp)/'private.svg'
            canary.write_text('<svg xmlns="http://www.w3.org/2000/svg"><path fill="PRIVATE-CANARY"/></svg>')
            real_validate=package_module.validate
            did_swap=False
            def validate_then_swap(folder,**kwargs):
                nonlocal did_swap
                result=real_validate(folder,**kwargs)
                if pathlib.Path(folder).resolve()==d.resolve() and not did_swap:
                    asset.unlink()
                    asset.symlink_to(canary)
                    did_swap=True
                return result
            with mock.patch.object(package_module,'validate',side_effect=validate_then_swap):
                archive,preview=build(d,pathlib.Path(tmp)/'dist')
            self.assertTrue(did_swap)
            with zipfile.ZipFile(archive) as packaged:
                self.assertEqual(packaged.read('assets/background.svg'),original_bytes)
                self.assertNotIn(b'PRIVATE-CANARY',b''.join(packaged.read(name) for name in packaged.namelist()))
            self.assertNotIn(base64.b64encode(canary.read_bytes()).decode('ascii'),preview.read_text(encoding='utf-8'))
    def test_package_rejects_parent_symlink_swap_during_open(self):
        if not (getattr(os,'O_NOFOLLOW',0) and getattr(os,'O_DIRECTORY',0) and os.open in os.supports_dir_fd):
            self.skipTest('descriptor-relative no-follow open unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            outside=pathlib.Path(tmp)/'outside'
            outside.mkdir()
            (outside/'background.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"><path fill="PRIVATE-CANARY"/></svg>')
            real_open=os.open
            swapped=False
            def open_with_parent_swap(path,flags,*args,**kwargs):
                nonlocal swapped
                if pathlib.Path(path)==d.resolve() and 'dir_fd' not in kwargs and not swapped:
                    fd=real_open(path,flags,*args,**kwargs)
                    (d/'assets').rename(d/'assets_original')
                    (d/'assets').symlink_to(outside,target_is_directory=True)
                    swapped=True
                    return fd
                return real_open(path,flags,*args,**kwargs)
            with mock.patch.object(validator_module.os,'open',side_effect=open_with_parent_swap):
                with self.assertRaisesRegex(ValueError,'unable to snapshot asset'):
                    build(d,pathlib.Path(tmp)/'dist')
            self.assertTrue(swapped)
            self.assertFalse((pathlib.Path(tmp)/'dist').exists())
    def test_package_rejects_fifo_swap_without_blocking(self):
        if not (hasattr(os,'mkfifo') and getattr(os,'O_NONBLOCK',0)
                and getattr(os,'O_NOFOLLOW',0) and getattr(os,'O_DIRECTORY',0)
                and os.open in os.supports_dir_fd):
            self.skipTest('nonblocking descriptor-relative file open unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            manifest=json.loads((d/'manifest.json').read_text())
            target=d/pathlib.PurePosixPath(next(iter(manifest['assets'].values())))
            real_open=os.open
            swapped=False
            def open_with_fifo_swap(path,flags,*args,**kwargs):
                nonlocal swapped
                if kwargs.get('dir_fd') is not None and pathlib.Path(path).name==target.name and not swapped:
                    target.unlink()
                    os.mkfifo(target)
                    swapped=True
                return real_open(path,flags,*args,**kwargs)
            with mock.patch.object(validator_module.os,'open',side_effect=open_with_fifo_swap):
                with self.assertRaisesRegex(ValueError,'unable to snapshot asset'):
                    build(d,pathlib.Path(tmp)/'dist')
            self.assertTrue(swapped)
            self.assertFalse((pathlib.Path(tmp)/'dist').exists())
    def test_validate_rejects_fifo_swap_without_blocking(self):
        if not (hasattr(os,'mkfifo') and getattr(os,'O_NONBLOCK',0)
                and getattr(os,'O_NOFOLLOW',0) and getattr(os,'O_DIRECTORY',0)
                and os.open in os.supports_dir_fd):
            self.skipTest('nonblocking descriptor-relative file open unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            manifest=json.loads((d/'manifest.json').read_text())
            target=d/pathlib.PurePosixPath(next(iter(manifest['assets'].values())))
            real_open=os.open
            swapped=False
            def open_with_fifo_swap(path,flags,*args,**kwargs):
                nonlocal swapped
                if kwargs.get('dir_fd') is not None and pathlib.Path(path).name==target.name and not swapped:
                    target.unlink()
                    os.mkfifo(target)
                    swapped=True
                return real_open(path,flags,*args,**kwargs)
            with mock.patch.object(validator_module.os,'open',side_effect=open_with_fifo_swap):
                errors,_=validate(d)
            self.assertTrue(swapped)
            self.assertTrue(any('SVG' in error and 'asset changed' in error for error in errors),errors)
if __name__=='__main__':unittest.main()
