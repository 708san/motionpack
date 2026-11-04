import json
import base64
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'tools'))
import validate as validator_module
from validate import validate
import package as package_module
from package import build
class FormatTests(unittest.TestCase):
    def test_examples_valid(self):
        for project in ('robot_demo','robot_ik_demo'):
            errors,m=validate(ROOT/'examples'/project)
            self.assertEqual(errors,[],errors)
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
    def _copy(self,tmp):
        d=pathlib.Path(tmp)/'project'
        shutil.copytree(ROOT/'examples'/'robot_ik_demo',d)
        return d
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
    def test_reject_svg_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            (d/'assets'/'head.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"><image href="https://evil.example/a.png"/></svg>')
            errors,_=validate(d)
            self.assertTrue(any('forbidden SVG' in x or 'unsafe SVG' in x for x in errors),errors)
    def _validate_svg(self,svg):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            (d/'assets'/'background.svg').write_text(svg)
            return validate(d)[0]
    def test_svg_allows_local_gradient_reference(self):
        errors=self._validate_svg('<svg xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="paint"><stop offset="0" stop-color="red"/></linearGradient></defs><path fill="url(#paint)" d="M0 0"/></svg>')
        self.assertEqual(errors,[],errors)
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
        huge='<svg xmlns="http://www.w3.org/2000/svg"><path aria-label="'+'x'*(64*1024+1)+'"/></svg>'
        many='<svg xmlns="http://www.w3.org/2000/svg">'+'<path/>'*10000+'</svg>'
        attrs=' '.join(f'a{i}="x"' for i in range(129))
        too_many_attrs=f'<svg xmlns="http://www.w3.org/2000/svg"><path {attrs}/></svg>'
        for svg in (deep,huge,many,too_many_attrs):
            with self.subTest(size=len(svg)):
                errors=self._validate_svg(svg)
                self.assertTrue(any('SVG' in error for error in errors),errors)
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
            canary.write_text('<svg xmlns="http://www.w3.org/2000/svg"><path aria-label="PRIVATE-CANARY"/></svg>')
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
            (outside/'background.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"><path aria-label="PRIVATE-CANARY"/></svg>')
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
