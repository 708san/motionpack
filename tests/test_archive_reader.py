import json
import io
import hashlib
import os
import pathlib
import re
import random
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import tarfile
import warnings
import unittest
import zipfile
import zlib
from unittest import mock
from tests.jpeg_fixtures import jpeg_with_dnl_defined_height

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import archive_reader
from archive_reader import ArchiveError, ReaderLimits, read_package
from package import build

def png_ihdr(width,height):
    fields=struct.pack('>IIBBBBB',width,height,8,6,0,0,0)
    chunk=b'IHDR'+fields
    crc=zlib.crc32(chunk)&0xffffffff
    return b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+chunk+struct.pack('>I',crc)

def jpeg_header(width,height):
    frame=b'\x08'+struct.pack('>HHB',height,width,3)+b'\x01\x11\0\x02\x11\0\x03\x11\0'
    return b'\xff\xd8\xff\xc0'+struct.pack('>H',len(frame)+2)+frame+b'\xff\xda'

def webp_header(width,height,kind=b'VP8X'):
    if kind==b'VP8X':
        payload=b'\0'*4+(width-1).to_bytes(3,'little')+(height-1).to_bytes(3,'little')
        bits=(width-1)|((height-1)<<14)
        chunks=b'VP8X'+struct.pack('<I',len(payload))+payload
        bitstream=b'VP8L'+struct.pack('<I',5)+b'\x2f'+bits.to_bytes(4,'little')+b'\0'
        body=b'WEBP'+chunks+bitstream
        return b'RIFF'+struct.pack('<I',len(body))+body
    elif kind==b'VP8 ':
        payload=b'\0\0\0\x9d\x01\x2a'+struct.pack('<HH',width,height)
    else:
        payload=b'\x2f'+((width-1)|((height-1)<<14)).to_bytes(4,'little')
    chunk=kind+struct.pack('<I',len(payload))+payload+(b'\0' if len(payload)&1 else b'')
    body=b'WEBP'+chunk
    return b'RIFF'+struct.pack('<I',len(body))+body

def webp_animation(width,height,frames):
    def chunk(kind,payload):
        return kind+struct.pack('<I',len(payload))+payload+(b'\0' if len(payload)&1 else b'')
    vp8x=b'\x02\0\0\0'+(width-1).to_bytes(3,'little')+(height-1).to_bytes(3,'little')
    chunks=chunk(b'VP8X',vp8x)+chunk(b'ANIM',b'\0'*6)
    for x,y,frame_width,frame_height in frames:
        frame=(x//2).to_bytes(3,'little')+(y//2).to_bytes(3,'little')
        frame+=(frame_width-1).to_bytes(3,'little')+(frame_height-1).to_bytes(3,'little')+b'\0'*4
        bits=(frame_width-1)|((frame_height-1)<<14)
        frame+=chunk(b'VP8L',b'\x2f'+bits.to_bytes(4,'little'))
        chunks+=chunk(b'ANMF',frame)
    body=b'WEBP'+chunks
    return b'RIFF'+struct.pack('<I',len(body))+body


class NonSeekableBuffer(io.BytesIO):
    def seekable(self):
        return False

    def seek(self, *args):
        raise io.UnsupportedOperation("not seekable")


class ArchiveReaderTests(unittest.TestCase):
    def _package(self, folder, out):
        archive, _ = build(folder, out)
        return archive

    def _zip(self, path, entries, *, compression=zipfile.ZIP_STORED):
        with zipfile.ZipFile(path, "w", compression=compression) as archive:
            for name, data in entries:
                archive.writestr(name, data)
        return path

    def test_reads_frozen_v01_and_current_v02_packages(self):
        frozen_v01 = ROOT / "tests" / "fuzz_corpus" / "archive_reader" / "valid_v01.motionpack"
        self.assertEqual(
            hashlib.sha256(frozen_v01.read_bytes()).hexdigest(),
            "e76a7a60c12b3e2c5045ee655b9714995b1f66a7491dfe1584a51c3cd9a48982",
            "update the frozen v0.1 fixture hash only with an explicit compatibility review",
        )

        legacy = read_package(frozen_v01)
        self.assertEqual(legacy.manifest["format"], "motionpack")
        self.assertEqual(legacy.manifest["version"], "0.1")
        self.assertEqual(legacy.manifest["id"], "legacy-rigid-demo")
        self.assertEqual(
            legacy.manifest["canvas"],
            {"width": 800, "height": 1000, "background": "#0b1225"},
        )
        self.assertEqual(len(legacy.manifest["nodes"]), 9)
        self.assertEqual(set(legacy.manifest["clips"]), {"idle", "fire", "transform"})
        self.assertEqual(legacy.manifest["defaults"], {"clip": "idle", "variant": "form_a"})
        self.assertNotIn("iks", legacy.manifest)
        self.assertEqual(set(legacy.assets), set(legacy.manifest["assets"]))
        self.assertTrue(all(legacy.assets.values()))

        with tempfile.TemporaryDirectory() as tmp:
            current_v02 = self._package(
                ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "out"
            )
            current = read_package(current_v02)
        self.assertEqual(current.manifest["format"], "motionpack")
        self.assertEqual(current.manifest["version"], "0.2")
        self.assertEqual(current.manifest["canvas"]["width"], 1000)
        self.assertIn("iks", current.manifest)
        self.assertEqual(set(current.assets), set(current.manifest["assets"]))
        self.assertTrue(all(current.assets.values()))

    def test_reads_frozen_v03_and_v04_packages(self):
        expected_hashes = {
            "0.3": "06ad0b8b4b05e8212573784cbdda00a6c8dee9cfe8a9840888feb50cbf6611ea",
            "0.4": "c98a270b566a6792748fc479a63af484fc1c9378d3a4e7c638db96704943bcb8",
        }
        fixture_dir = ROOT / "tests" / "fixtures" / "compatibility_archive_reader"
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tests" / "build_compatibility_fixtures.py"),
                    "--output-dir",
                    tmp,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            for version, expected_hash in expected_hashes.items():
                filename = f"valid_v{version.replace('.', '')}.motionpack"
                regenerated = pathlib.Path(tmp) / filename
                committed = fixture_dir / filename
                self.assertEqual(hashlib.sha256(regenerated.read_bytes()).hexdigest(), expected_hash)
                self.assertEqual(regenerated.read_bytes(), committed.read_bytes())

        for version, expected_hash in expected_hashes.items():
            with self.subTest(version=version):
                fixture = fixture_dir / f"valid_v{version.replace('.', '')}.motionpack"
                self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), expected_hash)
                package = read_package(fixture)
                self.assertEqual(package.manifest["version"], version)
                self.assertEqual(set(package.assets), set(package.manifest["assets"]))
                self.assertTrue(all(package.assets.values()))
                with zipfile.ZipFile(fixture) as archive:
                    self.assertEqual(
                        set(archive.namelist()),
                        {"manifest.json", *package.manifest["assets"].values()},
                    )
                    self.assertFalse(any(name.casefold().startswith("source/") for name in archive.namelist()))

        v03 = read_package(fixture_dir / "valid_v03.motionpack")
        self.assertEqual(v03.manifest["id"], "layered-plant-demo")
        self.assertEqual(set(v03.assets), {"foliage", "pot"})

        v04 = read_package(fixture_dir / "valid_v04.motionpack")
        self.assertEqual(v04.manifest["id"], "node-interaction-demo")
        interactions = {
            node["id"]: node.get("interaction")
            for node in v04.manifest["nodes"]
        }
        self.assertEqual(interactions["hover_only"], {"hover": True})
        self.assertEqual(interactions["tap_only"], {"tap": True})
        self.assertEqual(interactions["click_only"], {"click": True})
        self.assertIsNone(interactions["disabled"])

    def test_reads_v03_and_enforces_svg_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            packaged=self._package(ROOT/'examples'/'robot_ik_demo',pathlib.Path(tmp)/'build')
            with zipfile.ZipFile(packaged) as original:
                entries=[]
                for item in original.infolist():
                    content=original.read(item)
                    if item.filename=='manifest.json':
                        manifest=json.loads(content)
                        manifest['version']='0.3'
                        content=json.dumps(manifest).encode()
                    elif item.filename.lower().endswith('.svg'):
                        content=re.sub(rb'(<svg\b[^>]*?)\swidth="[^"]*"',rb'\1',content,count=1)
                        content=re.sub(rb'(<svg\b[^>]*?)\sheight="[^"]*"',rb'\1',content,count=1)
                        content=content.replace(b'<svg',b'<svg width="10" height="10"',1)
                    entries.append((item.filename,content))
            archive=self._zip(pathlib.Path(tmp)/'v03.motionpack',entries)
            result=read_package(archive)
            self.assertEqual(result.manifest['version'],'0.3')
            for name,width,height,message in (
                ('default-edge',8193,1,'SVG dimension limit exceeded'),
                ('default-area',4001,4000,'SVG pixel limit exceeded'),
            ):
                oversized=[]
                for path,content in entries:
                    if path.lower().endswith('.svg'):
                        content=re.sub(rb'(<svg\b[^>]*?)\swidth="[^"]*"',rb'\1',content,count=1)
                        content=re.sub(rb'(<svg\b[^>]*?)\sheight="[^"]*"',rb'\1',content,count=1)
                        content=content.replace(b'<svg',f'<svg width="{width}" height="{height}"'.encode(),1)
                    oversized.append((path,content))
                oversized_archive=self._zip(pathlib.Path(tmp)/f'{name}.motionpack',oversized)
                with self.assertRaisesRegex(ArchiveError,message):
                    read_package(oversized_archive)
            limited=ReaderLimits(max_svg_dimension=5)
            with self.assertRaisesRegex(ArchiveError,'SVG dimension limit exceeded'):
                read_package(archive,limits=limited)
            dimensionless=[(name,content.replace(b' width="10" height="10"',b'',1)
                            if name.lower().endswith('.svg') else content)
                           for name,content in entries]
            bad=self._zip(pathlib.Path(tmp)/'v03-no-svg-size.motionpack',dimensionless)
            with self.assertRaisesRegex(ArchiveError,'SVG width is required'):
                read_package(bad)

    def test_v01_and_v02_archives_keep_dimensionless_svg_compatibility(self):
        for project,version in (("robot_demo","0.1"),("robot_ik_demo","0.2")):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                packaged=self._package(ROOT/'examples'/project,pathlib.Path(tmp)/'build')
                with zipfile.ZipFile(packaged) as original:
                    entries=[]
                    for item in original.infolist():
                        content=original.read(item)
                        if item.filename.lower().endswith('.svg'):
                            content=re.sub(rb'(<svg\b[^>]*?)\swidth="[^"]*"',rb'\1',content,count=1)
                            content=re.sub(rb'(<svg\b[^>]*?)\sheight="[^"]*"',rb'\1',content,count=1)
                        entries.append((item.filename,content))
                archive=self._zip(pathlib.Path(tmp)/f'legacy-{version}.motionpack',entries)
                result=read_package(archive)
                self.assertEqual(result.manifest['version'],version)

    def test_reader_svg_limits_cannot_be_raised_above_v03_format_maxima(self):
        with self.assertRaisesRegex(ValueError,'cannot exceed v0.3 maxima'):
            ReaderLimits(max_svg_dimension=8193)
        with self.assertRaisesRegex(ValueError,'cannot exceed v0.3 maxima'):
            ReaderLimits(max_svg_pixels=16_000_001)

    def test_untrusted_svg_is_rejected_through_archive_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            packed = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "out")
            with zipfile.ZipFile(packed) as original:
                manifest = json.loads(original.read("manifest.json"))
                target = next(iter(manifest["assets"].values()))
                entries = [(item.filename, original.read(item)) for item in original.infolist()]
            entries = [(name, b'<!DOCTYPE svg [<!ENTITY x "boom">]><svg xmlns="http://www.w3.org/2000/svg"/>' if name == target else data) for name, data in entries]
            unsafe = self._zip(pathlib.Path(tmp) / "unsafe-svg.motionpack", entries)
            with self.assertRaisesRegex(ArchiveError, "invalid package manifest or assets"):
                read_package(unsafe)

    def test_reads_zip_with_leading_stub_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = self._package(ROOT / "examples" / "robot_demo", pathlib.Path(tmp) / "build")
            prefixed = pathlib.Path(tmp) / "prefixed.motionpack"
            prefixed.write_bytes(b"MOTIONPACK-STUB-DATA" + package.read_bytes())
            result = read_package(prefixed)
            self.assertEqual(result.manifest["version"], "0.1")

    def test_source_entries_are_not_read_or_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = ROOT / "examples" / "robot_ik_demo"
            archive = self._package(project, pathlib.Path(tmp) / "out")
            entries = []
            with zipfile.ZipFile(archive) as original:
                entries = [(item.filename, original.read(item)) for item in original.infolist()]
            entries.append(("source/private.txt", b"private source bytes"))
            source_archive = self._zip(pathlib.Path(tmp) / "with-source.motionpack", entries)
            package = read_package(source_archive)
            self.assertEqual(set(package.assets), set(package.manifest["assets"]))

    def test_casefold_source_entries_remain_opaque(self):
        with tempfile.TemporaryDirectory() as tmp:
            packed = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "out")
            with zipfile.ZipFile(packed) as original:
                entries = [(item.filename, original.read(item)) for item in original.infolist()]
            entries.append(("SOURCE/private.zip", b"opaque source bytes"))
            archive = self._zip(pathlib.Path(tmp) / "uppercase-source.motionpack", entries)
            original_read = archive_reader._bounded_read
            with mock.patch.object(archive_reader, "_bounded_read", wraps=original_read) as read_member:
                package = read_package(archive)
            self.assertEqual(set(package.assets), set(package.manifest["assets"]))
            read_names = [call.args[1].filename for call in read_member.call_args_list]
            self.assertNotIn("SOURCE/private.zip", read_names)

    def test_manifest_cannot_expose_source_as_runtime_asset(self):
        for source_path in ("source/private.svg", "SOURCE/private.svg"):
            with self.subTest(source_path=source_path), tempfile.TemporaryDirectory() as tmp:
                archive = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "out")
                with zipfile.ZipFile(archive) as original:
                    manifest = json.loads(original.read("manifest.json"))
                    entries = [(item.filename, original.read(item)) for item in original.infolist()]
                manifest["assets"]["source_probe"] = source_path
                entries = [(name, json.dumps(manifest).encode() if name == "manifest.json" else data) for name, data in entries]
                entries.append((source_path, b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"))
                source_archive = self._zip(pathlib.Path(tmp) / "referenced-source.motionpack", entries)
                with self.assertRaisesRegex(ArchiveError, "source entries"):
                    read_package(source_archive)

    def test_rejects_unsafe_names_before_returning_assets(self):
        unsafe_names = ("../escape", "/absolute", "C:/drive", "\\\\server\\share", "assets\\x.svg", "assets//x.svg", "assets/./x.svg")
        for name in unsafe_names:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                archive = self._zip(pathlib.Path(tmp) / "bad.motionpack", [(name, b"x"), ("manifest.json", b"{}")])
                with self.assertRaises(ArchiveError):
                    read_package(archive)

    def test_rejects_duplicate_and_casefold_colliding_names(self):
        fixtures = (
            [("manifest.json", b"{}"), ("manifest.json", b"{}")],
            [("manifest.json", b"{}"), ("Assets/a.svg", b"a"), ("assets/A.svg", b"b")],
            [("manifest.json", b"{}"), ("assets/\u00e9.svg", b"a"), ("assets/e\u0301.svg", b"b")],
        )
        for entries in fixtures:
            with self.subTest(entries=[name for name, _ in entries]), tempfile.TemporaryDirectory() as tmp:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    archive = self._zip(pathlib.Path(tmp) / "collision.motionpack", entries)
                with self.assertRaises(ArchiveError):
                    read_package(archive)

    def test_rejects_file_directory_prefix_collisions(self):
        for extra_entries in (
            [("orphan", b"file"), ("orphan/child.txt", b"child")],
            [("orphan/child.txt", b"child"), ("orphan", b"file")],
        ):
            with self.subTest(entries=[name for name, _ in extra_entries]), tempfile.TemporaryDirectory() as tmp:
                packed = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "out")
                with zipfile.ZipFile(packed) as original:
                    entries = [(item.filename, original.read(item)) for item in original.infolist()]
                archive = self._zip(pathlib.Path(tmp) / "prefix-collision.motionpack", entries + extra_entries)
                with self.assertRaisesRegex(ArchiveError, "file/directory path collision"):
                    read_package(archive)

    def test_rejects_symlink_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "symlink.motionpack"
            info = zipfile.ZipInfo("assets/link.svg")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("manifest.json", b"{}")
                archive.writestr(info, "../../outside")
            with self.assertRaisesRegex(ArchiveError, "symlink"):
                read_package(path)

    def test_entry_and_expanded_size_limits_are_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(pathlib.Path(tmp) / "many.motionpack", [("manifest.json", b"{}"), ("extra", b"x")])
            with self.assertRaisesRegex(ArchiveError, "entry count"):
                read_package(path, limits=ReaderLimits(max_entries=1))
            with self.assertRaisesRegex(ArchiveError, "expanded size"):
                read_package(path, limits=ReaderLimits(max_total_uncompressed=2))

    def test_entry_count_is_checked_before_zipfile_parses_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(pathlib.Path(tmp) / "too-many.motionpack", [("manifest.json", b"{}"), ("extra", b"x")])
            with mock.patch.object(archive_reader.zipfile, "ZipFile") as zip_file:
                with self.assertRaisesRegex(ArchiveError, "entry count"):
                    read_package(path, limits=ReaderLimits(max_entries=1))
                zip_file.assert_not_called()

    def test_central_directory_limit_and_count_mismatch_precede_zipfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(pathlib.Path(tmp) / "directory-limit.motionpack", [("manifest.json", b"{}")])
            with mock.patch.object(archive_reader.zipfile, "ZipFile") as zip_file:
                with self.assertRaisesRegex(ArchiveError, "central directory"):
                    read_package(path, limits=ReaderLimits(max_central_directory_bytes=1))
                zip_file.assert_not_called()

            data = bytearray(path.read_bytes())
            end = data.rfind(b"PK\x05\x06")
            data[end + 8:end + 12] = struct.pack("<HH", 0, 0)
            path.write_bytes(data)
            with mock.patch.object(archive_reader.zipfile, "ZipFile") as zip_file:
                with self.assertRaisesRegex(ArchiveError, "entry count"):
                    read_package(path)
                zip_file.assert_not_called()

    def test_rejects_zip64_locator_and_eocd_signature_in_comment_before_zipfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(pathlib.Path(tmp) / "locator.motionpack", [("manifest.json", b"{}")])
            data = path.read_bytes()
            end = data.rfind(b"PK\x05\x06")
            path.write_bytes(data[:end] + b"PK\x06\x07" + b"\0" * 16 + data[end:])
            with mock.patch.object(archive_reader.zipfile, "ZipFile") as zip_file:
                with self.assertRaisesRegex(ArchiveError, "ZIP64"):
                    read_package(path)
                zip_file.assert_not_called()

            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("manifest.json", b"{}")
                archive.comment = b"PK\x05\x06"
            with mock.patch.object(archive_reader.zipfile, "ZipFile") as zip_file:
                with self.assertRaises(ArchiveError):
                    read_package(path)
                zip_file.assert_not_called()

    def test_rejects_zip64_local_extra_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "zip64-local.motionpack"
            with zipfile.ZipFile(path, "w") as archive:
                with archive.open("manifest.json", "w", force_zip64=True) as manifest:
                    manifest.write(b"{}")
            with self.assertRaisesRegex(ArchiveError, "ZIP64"):
                read_package(path)

    def test_accepts_valid_data_descriptors(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "build")
            buffer = NonSeekableBuffer()
            with zipfile.ZipFile(original) as source, zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as target:
                for info in source.infolist():
                    with target.open(info.filename, "w") as member:
                        member.write(source.read(info))
            path = pathlib.Path(tmp) / "descriptor.motionpack"
            path.write_bytes(buffer.getvalue())
            result = read_package(path)
            self.assertEqual(result.manifest["version"], "0.2")

    def test_rejects_local_crc_or_size_mismatch(self):
        for offset in (14, 18, 22):
            with self.subTest(offset=offset), tempfile.TemporaryDirectory() as tmp:
                path = self._zip(pathlib.Path(tmp) / "bad-local.motionpack", [("manifest.json", b"{}")])
                data = bytearray(path.read_bytes())
                data[offset] ^= 0x01
                path.write_bytes(data)
                with mock.patch.object(archive_reader.zipfile, "ZipFile") as zip_file:
                    with self.assertRaisesRegex(ArchiveError, "CRC/size"):
                        read_package(path)
                    zip_file.assert_not_called()

    def test_local_flags_and_compression_mismatches_are_rejected_before_zipfile(self):
        cases = (
            ("flag", 6, 1),
            ("compression", 8, zipfile.ZIP_DEFLATED),
        )
        for label, offset, local_value in cases:
            with self.subTest(field=label), tempfile.TemporaryDirectory() as tmp:
                path = self._zip(
                    pathlib.Path(tmp) / f"{label}-mismatch.motionpack",
                    [("manifest.json", b"{}")],
                )
                data = bytearray(path.read_bytes())
                self.assertEqual(data[:4], bytes.fromhex("504b0304"))
                struct.pack_into("<H", data, offset, local_value)
                path.write_bytes(data)

                with mock.patch.object(archive_reader.zipfile, "ZipFile") as zip_file:
                    with self.assertRaisesRegex(
                        ArchiveError, "local and central metadata disagree"
                    ):
                        read_package(path)
                    zip_file.assert_not_called()

    def test_rejects_overlapping_local_records_before_zipfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = self._zip(
                root / "overlapping.motionpack",
                [("manifest.json", b"placeholder"), ("assets/orphan.svg", b"payload")],
            )
            original = path.read_bytes()
            with zipfile.ZipFile(path) as archive:
                info = archive.getinfo("assets/orphan.svg")
                local_name_length, local_extra_length = struct.unpack_from(
                    "<HH", original, info.header_offset + 26
                )
                record_start = info.header_offset
                record_end = (
                    record_start + 30 + local_name_length + local_extra_length
                    + info.compress_size
                )
                embedded_record = original[record_start:record_end]

            prefix = b"embedded local record:"
            self._zip(
                path,
                [
                    ("manifest.json", prefix + embedded_record),
                    ("assets/orphan.svg", b"payload"),
                ],
            )
            data = bytearray(path.read_bytes())
            manifest_name_length, manifest_extra_length = struct.unpack_from(
                "<HH", data, 26
            )
            embedded_offset = (
                30 + manifest_name_length + manifest_extra_length + len(prefix)
            )

            cursor = 0
            while cursor + 46 <= len(data) and data[cursor:cursor + 4] != bytes.fromhex("504b0102"):
                cursor += 1
            while cursor + 46 <= len(data) and data[cursor:cursor + 4] == bytes.fromhex("504b0102"):
                name_length, extra_length, comment_length = struct.unpack_from(
                    "<HHH", data, cursor + 28
                )
                name_start = cursor + 46
                name = bytes(data[name_start:name_start + name_length])
                if name == b"assets/orphan.svg":
                    struct.pack_into("<L", data, cursor + 42, embedded_offset)
                    break
                cursor += 46 + name_length + extra_length + comment_length
            else:
                self.fail("orphan entry central-directory record not found")
            path.write_bytes(data)

            with mock.patch.object(archive_reader.zipfile, "ZipFile") as zip_file:
                with self.assertRaisesRegex(ArchiveError, "local entry records overlap"):
                    read_package(path)
                zip_file.assert_not_called()

    def test_local_filename_mismatch_is_rejected_before_zipfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(
                pathlib.Path(tmp) / "local-name-mismatch.motionpack",
                [("manifest.json", b"{}")],
            )
            data = bytearray(path.read_bytes())
            self.assertEqual(data[:4], b"PK\x03\x04")
            filename_length, extra_length = struct.unpack_from("<HH", data, 26)
            self.assertEqual(data[30:30 + filename_length], b"manifest.json")
            data[30] ^= 0x01
            path.write_bytes(data)

            with mock.patch.object(archive_reader.zipfile, "ZipFile") as zip_file:
                with self.assertRaisesRegex(ArchiveError, "local and central names disagree"):
                    read_package(path)
                zip_file.assert_not_called()

    def test_data_descriptor_mismatch_is_rejected_before_zipfile(self):
        buffer = NonSeekableBuffer()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            with archive.open("manifest.json", "w") as member:
                member.write(b"{}")

        data = bytearray(buffer.getvalue())
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("manifest.json")
            filename_length, extra_length = struct.unpack_from(
                "<HH", data, info.header_offset + 26
            )
            data_start = info.header_offset + 30 + filename_length + extra_length
            descriptor_start = data_start + info.compress_size
        self.assertEqual(data[descriptor_start:descriptor_start + 4], b"PK\x07\x08")
        data[descriptor_start + 4] ^= 0x01

        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "descriptor-mismatch.motionpack"
            path.write_bytes(data)
            with mock.patch.object(archive_reader.zipfile, "ZipFile") as zip_file:
                with self.assertRaisesRegex(
                    ArchiveError, "data descriptor disagrees with central directory"
                ):
                    read_package(path)
                zip_file.assert_not_called()

    def test_aggregate_limit_counts_unique_zip_assets_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_copy = pathlib.Path(tmp) / "project"
            shutil.copytree(ROOT / "examples" / "robot_ik_demo", project_copy)
            manifest_path = project_copy / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["assets"]["background_alias"] = manifest["assets"]["background"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            path = self._package(project_copy, pathlib.Path(tmp) / "build")
            with zipfile.ZipFile(path) as archive:
                unique_asset_paths = set(json.loads(archive.read("manifest.json"))["assets"].values())
                asset_total = sum(archive.getinfo(name).file_size for name in unique_asset_paths)
            result = read_package(path, limits=ReaderLimits(max_total_assets_bytes=asset_total))
            self.assertEqual(result.assets["background_alias"], result.assets["background"])

    def test_total_asset_limit_is_checked_before_asset_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "build")
            with self.assertRaisesRegex(ArchiveError, "declared total asset size"):
                read_package(path, limits=ReaderLimits(max_total_assets_bytes=1))

    def test_rejects_excessive_compression_ratio(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = b"A" * 8192
            path = self._zip(pathlib.Path(tmp) / "ratio.motionpack", [("manifest.json", b"{}"), ("extra", data)], compression=zipfile.ZIP_DEFLATED)
            with self.assertRaisesRegex(ArchiveError, "compression ratio"):
                read_package(path, limits=ReaderLimits(max_compression_ratio=2))

    def test_rejects_nested_archive_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(pathlib.Path(tmp) / "nested.motionpack", [("manifest.json", b"{}"), ("extras/nested.zip", b"PK\x03\x04")])
            with self.assertRaisesRegex(ArchiveError, "nested archive"):
                read_package(path)

    def test_rejects_misnamed_and_unreferenced_nested_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            valid = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "build")
            with zipfile.ZipFile(valid) as original:
                entries = [(item.filename, original.read(item)) for item in original.infolist()]
            # No manifest reference, and the filename hides the archive type.
            entries.append(("extras/data.bin", b"PK\x03\x04" + b"nested zip payload"))
            disguised = self._zip(pathlib.Path(tmp) / "disguised.motionpack", entries)
            with self.assertRaisesRegex(ArchiveError, "nested archive"):
                read_package(disguised)

    def test_source_archive_entries_remain_opaque(self):
        with tempfile.TemporaryDirectory() as tmp:
            valid = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "build")
            with zipfile.ZipFile(valid) as original:
                entries = [(item.filename, original.read(item)) for item in original.infolist()]
            entries.append(("source/original.zip", b"PK\x03\x04" + b"opaque source bytes"))
            package = self._zip(pathlib.Path(tmp) / "source-opaque.motionpack", entries)
            result = read_package(package)
            self.assertNotIn("source/original.zip", result.assets)

    def test_root_entry_named_source_is_not_treated_as_source_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            valid = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "build")
            with zipfile.ZipFile(valid) as original:
                entries = [(item.filename, original.read(item)) for item in original.infolist()]
            entries.append(("source", bytes.fromhex("504b0304") + b"not under source directory"))
            package = self._zip(pathlib.Path(tmp) / "root-source-file.motionpack", entries)
            with self.assertRaisesRegex(ArchiveError, "nested archive"):
                read_package(package)

    def test_reader_rejects_each_supported_nested_archive_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            valid = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "build")
            with zipfile.ZipFile(valid) as original:
                entries = [(item.filename, original.read(item)) for item in original.infolist()]
            tar_buffer = io.BytesIO()
            with tarfile.open(fileobj=tar_buffer, mode="w") as nested:
                member = tarfile.TarInfo("item")
                member.size = 1
                nested.addfile(member, io.BytesIO(b"x"))
            signatures = (
                ("zip", b"PK\x03\x04payload"), ("gzip", b"\x1f\x8bpayload"),
                ("bzip2", b"BZh9payload"), ("xz", b"\xfd7zXZ\x00payload"),
                ("7zip", b"7z\xbc\xaf\x27\x1c"),
                ("rar4", b"Rar!\x1a\x07\x00payload"),
                ("rar5", b"Rar!\x1a\x07\x01\x00payload"),
                ("tar", tar_buffer.getvalue()[:512]),
            )
            for name, payload in signatures:
                with self.subTest(format=name):
                    candidate = self._zip(
                        pathlib.Path(tmp) / f"nested-{name}.motionpack",
                        entries + [("extras/payload.bin", payload)],
                    )
                    with self.assertRaisesRegex(ArchiveError, "nested archive"):
                        read_package(candidate)

            ordinary = self._zip(
                pathlib.Path(tmp) / "ordinary-bzh.motionpack",
                entries + [("extras/notes.bin", b"BZh-not-a-valid-bzip-header")],
            )
            result = read_package(ordinary)
            self.assertNotIn("extras/notes.bin", result.assets)

    def test_archive_signature_sniffer_recognizes_supported_container_headers(self):
        for payload in (
            b"PK\x03\x04payload", b"\x1f\x8bpayload", b"BZh9payload",
            b"\xfd7zXZ\x00payload", b"7z\xbc\xaf\x27\x1c",
            b"Rar!\x1a\x07\x00payload", b"Rar!\x1a\x07\x01\x00payload",
        ):
            with self.subTest(payload=payload[:8]):
                self.assertTrue(archive_reader._looks_like_archive(payload))

        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w") as nested:
            member = tarfile.TarInfo("item")
            member.size = 1
            nested.addfile(member, io.BytesIO(b"x"))
        self.assertTrue(archive_reader._looks_like_archive(tar_buffer.getvalue()[:512]))
        self.assertFalse(archive_reader._looks_like_archive(b"BZh-not-a-valid-bzip-header"))

    def test_rejects_invalid_reader_limits(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            ReaderLimits(max_entries=0)
        with self.assertRaisesRegex(ValueError, "PNG integer limits"):
            ReaderLimits(max_total_png_pixels=0)
        with self.assertRaisesRegex(ValueError, "PNG specification maximum"):
            ReaderLimits(max_png_dimension=0x80000000)
        with self.assertRaisesRegex(ValueError, "finite"):
            ReaderLimits(max_compression_ratio=float("inf"))

    def test_missing_or_invalid_manifest_is_rejected(self):
        for entries in ([("assets/a.svg", b"x")], [("manifest.json", b"not json")]):
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as tmp:
                path = self._zip(pathlib.Path(tmp) / "invalid.motionpack", entries)
                with self.assertRaises(ArchiveError):
                    read_package(path)

    def test_rejects_duplicate_json_keys_and_missing_referenced_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            duplicate = self._zip(
                pathlib.Path(tmp) / "duplicate-json.motionpack",
                [("manifest.json", b'{"format":"motionpack","assets":{},"assets":{}}')],
            )
            with self.assertRaisesRegex(ArchiveError, "invalid package manifest"):
                read_package(duplicate)

            valid = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "build")
            with zipfile.ZipFile(valid) as package:
                manifest = json.loads(package.read("manifest.json"))
                omitted = next(iter(manifest["assets"].values()))
                entries = [(item.filename, package.read(item)) for item in package.infolist() if item.filename != omitted]
            missing = self._zip(pathlib.Path(tmp) / "missing-asset.motionpack", entries)
            with self.assertRaisesRegex(ArchiveError, "missing archive asset"):
                read_package(missing)

    def test_manifest_and_asset_read_limits_are_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "build")
            with self.assertRaisesRegex(ArchiveError, "manifest size"):
                read_package(path, limits=ReaderLimits(max_manifest_bytes=1))
            with self.assertRaisesRegex(ArchiveError, "asset size"):
                read_package(path, limits=ReaderLimits(max_asset_bytes=1))

    def test_archive_reader_enforces_png_limits_and_unique_entry_accounting(self):
        with tempfile.TemporaryDirectory() as tmp:
            packed=self._package(ROOT/'examples'/'robot_ik_demo',pathlib.Path(tmp)/'build')
            with zipfile.ZipFile(packed) as original:
                manifest=json.loads(original.read('manifest.json'))
                entries=[(item.filename,original.read(item)) for item in original.infolist()]
            manifest['assets']['pixel']='assets/pixel.png'
            entries=[(name,json.dumps(manifest).encode() if name=='manifest.json' else data) for name,data in entries]
            entries.append(('assets/pixel.png',png_ihdr(2,2)))
            archive=self._zip(pathlib.Path(tmp)/'png-limits.motionpack',entries)

            with self.assertRaisesRegex(ArchiveError,'PNG pixel limit exceeded'):
                read_package(archive,limits=ReaderLimits(max_png_dimension=2,max_png_pixels=3,max_total_png_pixels=4))
            with self.assertRaisesRegex(ArchiveError,'PNG dimension limit exceeded'):
                read_package(archive,limits=ReaderLimits(max_png_dimension=1,max_png_pixels=4,max_total_png_pixels=4))
            result=read_package(archive,limits=ReaderLimits(max_png_dimension=2,max_png_pixels=4,max_total_png_pixels=4))
            self.assertIn('pixel',result.assets)

    def test_archive_reader_rejects_invalid_png_ihdr(self):
        with tempfile.TemporaryDirectory() as tmp:
            packed=self._package(ROOT/'examples'/'robot_ik_demo',pathlib.Path(tmp)/'build')
            with zipfile.ZipFile(packed) as original:
                manifest=json.loads(original.read('manifest.json'))
                entries=[(item.filename,original.read(item)) for item in original.infolist()]
            manifest['assets']['bad_png']='assets/bad.png'
            entries=[(name,json.dumps(manifest).encode() if name=='manifest.json' else data) for name,data in entries]
            entries.append(('assets/bad.png',b'not a png'))
            archive=self._zip(pathlib.Path(tmp)/'invalid-png.motionpack',entries)
            with self.assertRaisesRegex(ArchiveError,'invalid package manifest or assets.*invalid PNG header'):
                read_package(archive)

    def test_archive_reader_classifies_raster_by_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            packed=self._package(ROOT/'examples'/'robot_ik_demo',pathlib.Path(tmp)/'build')
            with zipfile.ZipFile(packed) as original:
                manifest=json.loads(original.read('manifest.json'))
                entries=[(item.filename,original.read(item)) for item in original.infolist()]
            manifest['assets']['png_bytes_jpg_path']='assets/misnamed.jpg'
            entries=[(name,json.dumps(manifest).encode() if name=='manifest.json' else data) for name,data in entries]
            entries.append(('assets/misnamed.jpg',png_ihdr(8193,1)))
            archive=self._zip(pathlib.Path(tmp)/'misnamed-png.motionpack',entries)
            with self.assertRaisesRegex(ArchiveError,'invalid package manifest or assets.*invalid JPEG header'):
                read_package(archive)

    def test_archive_reader_rejects_png_spec_dimensions_above_permissive_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            packed=self._package(ROOT/'examples'/'robot_ik_demo',pathlib.Path(tmp)/'build')
            with zipfile.ZipFile(packed) as original:
                manifest=json.loads(original.read('manifest.json'))
                entries=[(item.filename,original.read(item)) for item in original.infolist()]
            manifest['assets']['too_wide']='assets/too_wide.png'
            entries=[(name,json.dumps(manifest).encode() if name=='manifest.json' else data) for name,data in entries]
            entries.append(('assets/too_wide.png',png_ihdr(0x80000000,1)))
            archive=self._zip(pathlib.Path(tmp)/'png-spec-dimension.motionpack',entries)
            permissive=ReaderLimits(
                max_png_dimension=0x7FFFFFFF,
                max_png_pixels=0xFFFFFFFF,
                max_total_png_pixels=0xFFFFFFFF,
            )
            with self.assertRaisesRegex(ArchiveError,'invalid package manifest or assets.*invalid PNG header'):
                read_package(archive,limits=permissive)

    def test_archive_reader_enforces_aggregate_png_pixel_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            packed=self._package(ROOT/'examples'/'robot_ik_demo',pathlib.Path(tmp)/'build')
            with zipfile.ZipFile(packed) as original:
                manifest=json.loads(original.read('manifest.json'))
                entries=[(item.filename,original.read(item)) for item in original.infolist()]
            for index in range(5):
                rel=f'assets/pixel_{index}.png'
                manifest['assets'][f'pixel_{index}']=rel
                entries.append((rel,png_ihdr(2,2)))
            entries=[(name,json.dumps(manifest).encode() if name=='manifest.json' else data) for name,data in entries]
            archive=self._zip(pathlib.Path(tmp)/'png-total-limit.motionpack',entries)
            limits=ReaderLimits(max_png_dimension=2,max_png_pixels=4,max_total_png_pixels=16)
            with self.assertRaisesRegex(ArchiveError,'total raster pixel budget exceeded'):
                read_package(archive,limits=limits)

    def test_archive_reader_applies_shared_limits_to_jpeg_webp(self):
        with tempfile.TemporaryDirectory() as tmp:
            packed=self._package(ROOT/'examples'/'robot_ik_demo',pathlib.Path(tmp)/'build')
            with zipfile.ZipFile(packed) as original:
                manifest=json.loads(original.read('manifest.json'))
                entries=[(item.filename,original.read(item)) for item in original.infolist()]
            manifest['assets'].update({'jpeg':'assets/large.jpg','webp':'assets/large.webp'})
            entries.extend([('assets/large.jpg',jpeg_header(8193,1)),('assets/large.webp',webp_header(1,1))])
            entries=[(name,json.dumps(manifest).encode() if name=='manifest.json' else data) for name,data in entries]
            archive=self._zip(pathlib.Path(tmp)/'large-raster.motionpack',entries)
            with self.assertRaisesRegex(ArchiveError,'JPEG dimension limit exceeded'):
                read_package(archive)
            with self.assertRaisesRegex(ArchiveError,'JPEG dimension limit exceeded'):
                read_package(archive,limits=ReaderLimits(max_png_dimension=1))
            override=ReaderLimits(max_png_dimension=1,max_raster_dimension=8193)
            self.assertIn('jpeg',read_package(archive,limits=override).assets)

    def test_archive_reader_mixed_raster_aggregate_counts_alias_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            packed=self._package(ROOT/'examples'/'robot_ik_demo',pathlib.Path(tmp)/'build')
            with zipfile.ZipFile(packed) as original:
                manifest=json.loads(original.read('manifest.json'))
                entries=[(item.filename,original.read(item)) for item in original.infolist()]
            manifest['assets'].update({
                'png':'assets/one.png','png_alias':'assets/one.png',
                'jpeg':'assets/two.jpg','webp':'assets/three.webp',
            })
            entries.extend([('assets/one.png',png_ihdr(2,2)),('assets/two.jpg',jpeg_header(2,2)),
                            ('assets/three.webp',webp_header(2,2,b'VP8L'))])
            entries=[(name,json.dumps(manifest).encode() if name=='manifest.json' else data) for name,data in entries]
            archive=self._zip(pathlib.Path(tmp)/'mixed-raster.motionpack',entries)
            accepted=ReaderLimits(max_raster_dimension=2,max_raster_pixels=4,max_total_raster_pixels=12)
            result=read_package(archive,limits=accepted)
            self.assertEqual(result.assets['png'],result.assets['png_alias'])
            rejected=ReaderLimits(max_raster_dimension=2,max_raster_pixels=4,max_total_raster_pixels=11)
            with self.assertRaisesRegex(ArchiveError,'total raster pixel budget exceeded'):
                read_package(archive,limits=rejected)

    def test_archive_reader_counts_animated_webp_canvas_and_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            packed=self._package(ROOT/'examples'/'robot_ik_demo',pathlib.Path(tmp)/'build')
            with zipfile.ZipFile(packed) as original:
                manifest=json.loads(original.read('manifest.json'))
                entries=[(item.filename,original.read(item)) for item in original.infolist()]
            manifest['assets']['animated']='assets/animated.webp'
            entries.append(('assets/animated.webp',webp_animation(2,2,[(0,0,2,2),(0,0,2,2)])))
            entries=[(name,json.dumps(manifest).encode() if name=='manifest.json' else data) for name,data in entries]
            archive=self._zip(pathlib.Path(tmp)/'animated-webp.motionpack',entries)
            accepted=ReaderLimits(max_raster_dimension=2,max_raster_pixels=4,max_total_raster_pixels=12)
            self.assertIn('animated',read_package(archive,limits=accepted).assets)
            rejected=ReaderLimits(max_raster_dimension=2,max_raster_pixels=4,max_total_raster_pixels=11)
            with self.assertRaisesRegex(ArchiveError,'total raster pixel budget exceeded'):
                read_package(archive,limits=rejected)

    def test_archive_reader_rejects_malformed_jpeg_and_webp_headers(self):
        for path,data in (('assets/bad.jpg',b'\xff\xd8'),('assets/bad.webp',b'RIFF\0\0\0\0WEBP')):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as tmp:
                packed=self._package(ROOT/'examples'/'robot_ik_demo',pathlib.Path(tmp)/'build')
                with zipfile.ZipFile(packed) as original:
                    manifest=json.loads(original.read('manifest.json'))
                    entries=[(item.filename,original.read(item)) for item in original.infolist()]
                manifest['assets']['bad']=path
                entries.append((path,data))
                entries=[(name,json.dumps(manifest).encode() if name=='manifest.json' else content) for name,content in entries]
                archive=self._zip(pathlib.Path(tmp)/'bad-raster.motionpack',entries)
                with self.assertRaisesRegex(ArchiveError,'invalid package manifest or assets.*invalid (JPEG|WebP) header'):
                    read_package(archive)

    def test_archive_reader_rejects_jpeg_zero_sof_height(self):
        path='assets/zero-height.jpg'
        with tempfile.TemporaryDirectory() as tmp:
            packed=self._package(ROOT/'examples'/'robot_ik_demo',pathlib.Path(tmp)/'build')
            with zipfile.ZipFile(packed) as original:
                manifest=json.loads(original.read('manifest.json'))
                entries=[(item.filename,original.read(item)) for item in original.infolist()]
            manifest['assets']['zero_height']=path
            entries.append((path,jpeg_header(320,0)))
            entries=[(name,json.dumps(manifest).encode() if name=='manifest.json' else data) for name,data in entries]
            archive=self._zip(pathlib.Path(tmp)/'zero-height.motionpack',entries)
            with self.assertRaisesRegex(ArchiveError,'invalid package manifest or assets.*invalid JPEG header'):
                read_package(archive)

    def test_archive_reader_rejects_jpeg_dnl_defined_height(self):
        path='assets/dnl-height.jpg'
        data=jpeg_with_dnl_defined_height()
        with tempfile.TemporaryDirectory() as tmp:
            packed=self._package(ROOT/'examples'/'robot_ik_demo',pathlib.Path(tmp)/'build')
            with zipfile.ZipFile(packed) as original:
                manifest=json.loads(original.read('manifest.json'))
                entries=[(item.filename,original.read(item)) for item in original.infolist()]
            manifest['assets']['dnl_height']=path
            entries.append((path,data))
            entries=[(name,json.dumps(manifest).encode() if name=='manifest.json' else content)
                     for name,content in entries]
            archive=self._zip(pathlib.Path(tmp)/'dnl-height.motionpack',entries)
            with self.assertRaisesRegex(ArchiveError,'invalid package manifest or assets.*invalid JPEG header'):
                read_package(archive)

    def test_archive_reader_counts_unicode_path_aliases_as_one_png_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            packed=self._package(ROOT/'examples'/'robot_ik_demo',pathlib.Path(tmp)/'build')
            with zipfile.ZipFile(packed) as original:
                manifest=json.loads(original.read('manifest.json'))
                entries=[(item.filename,original.read(item)) for item in original.infolist()]
            manifest['assets']['pixel_composed']='assets/é.png'
            manifest['assets']['pixel_decomposed']='assets/e\u0301.png'
            entries=[(name,json.dumps(manifest,ensure_ascii=False).encode() if name=='manifest.json' else data) for name,data in entries]
            entries.append(('assets/é.png',png_ihdr(2,2)))
            archive=self._zip(pathlib.Path(tmp)/'png-aliases.motionpack',entries)
            limits=ReaderLimits(max_png_dimension=2,max_png_pixels=4,max_total_png_pixels=4)
            result=read_package(archive,limits=limits)
            self.assertEqual(result.assets['pixel_composed'],result.assets['pixel_decomposed'])

    def test_rejects_truncated_or_non_zip_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "not-a-zip.motionpack"
            path.write_bytes(b"not a ZIP archive")
            with self.assertRaises(ArchiveError):
                read_package(path)

            valid = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "build")
            truncated = pathlib.Path(tmp) / "truncated.motionpack"
            truncated.write_bytes(valid.read_bytes()[:-24])
            with self.assertRaises(ArchiveError):
                read_package(truncated)

    def test_corrupt_deflate_stream_uses_archive_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "corrupt-deflate.motionpack"
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", b'{"format":"motionpack"}')
            with zipfile.ZipFile(path) as archive:
                info = archive.getinfo("manifest.json")
                offset = info.header_offset
            data = bytearray(path.read_bytes())
            filename_length, extra_length = struct.unpack_from("<HH", data, offset + 26)
            compressed_data_offset = offset + 30 + filename_length + extra_length
            data[compressed_data_offset] ^= 0xFF
            path.write_bytes(data)
            with self.assertRaisesRegex(ArchiveError, "unable to inspect archive entry"):
                read_package(path)

    def test_deterministic_archive_mutations_reject_or_return_consistent_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            valid = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "build")
            original = valid.read_bytes()
            mutated = pathlib.Path(tmp) / "mutated.motionpack"
            rng = random.Random(0x4D4F54494F4E)
            rejected = 0

            for _ in range(128):
                data = bytearray(original)
                for _ in range(rng.randint(1, 4)):
                    offset = rng.randrange(len(data))
                    data[offset] ^= rng.randrange(1, 256)
                mutated.write_bytes(data)
                try:
                    package = read_package(mutated)
                except ArchiveError:
                    rejected += 1
                else:
                    self.assertIsInstance(package.manifest, dict)
                    self.assertEqual(set(package.assets), set(package.manifest["assets"]))
                    self.assertTrue(all(isinstance(asset, bytes) for asset in package.assets.values()))

            self.assertGreater(rejected, 0, "mutation corpus unexpectedly contained no rejected archives")

    def test_does_not_create_files_outside_archive_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            outside = root / "escape"
            archive = self._zip(root / "slip.motionpack", [("../escape", b"owned"), ("manifest.json", b"{}")])
            with self.assertRaises(ArchiveError):
                read_package(archive)
            self.assertFalse(outside.exists())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "named pipes are unavailable")
    def test_fifo_input_is_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            fifo = root / "input.motionpack"
            os.mkfifo(fifo)
            script = (
                "import sys\n"
                "from archive_reader import read_package, ArchiveError\n"
                "try:\n"
                "    read_package(sys.argv[1])\n"
                "except ArchiveError:\n"
                "    raise SystemExit(0)\n"
                "raise SystemExit(2)\n"
            )
            result = subprocess.run(
                [sys.executable, "-c", script, str(fifo)],
                cwd=ROOT / "tools",
                capture_output=True,
                text=True,
                timeout=2,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "named pipes are unavailable")
    def test_fifo_is_rejected_before_opening_the_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            fifo = pathlib.Path(tmp) / "input.motionpack"
            os.mkfifo(fifo)
            alias = pathlib.Path(tmp) / "input-link.motionpack"
            alias.symlink_to(fifo)
            with mock.patch.object(archive_reader.os, "open", side_effect=AssertionError("must not open special file")):
                for candidate in (fifo, alias):
                    with self.subTest(candidate=candidate), self.assertRaisesRegex(ArchiveError, "regular file"):
                        read_package(candidate)

    @unittest.skipUnless(hasattr(os, "mkfifo") and hasattr(os, "O_NONBLOCK"), "non-blocking named pipes are unavailable")
    def test_fifo_replaced_after_stat_is_rejected_by_descriptor_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            regular = root / "regular.motionpack"
            regular.write_bytes(b"not a package")
            fifo = root / "input.motionpack"
            os.mkfifo(fifo)
            original_stat = type(fifo).stat

            def report_regular(path, *args, **kwargs):
                return original_stat(regular if path == fifo else path, *args, **kwargs)

            with mock.patch.object(type(fifo), "stat", autospec=True, side_effect=report_regular):
                with self.assertRaisesRegex(ArchiveError, "regular file"):
                    read_package(fifo)

    def test_regular_file_symlink_input_remains_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            package = self._package(ROOT / "examples" / "robot_demo", root / "build")
            alias = root / "regular-file-link.motionpack"
            alias.symlink_to(package)
            self.assertEqual(read_package(alias).manifest["version"], "0.1")


if __name__ == "__main__":
    unittest.main()
