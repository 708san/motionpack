import json
import pathlib
import shutil
import sys
import tempfile
import unittest
import zipfile
ROOT=pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'tools'))
from validate import validate
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
    def test_reject_svg_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            (d/'assets'/'head.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"><image href="https://evil.example/a.png"/></svg>')
            errors,_=validate(d)
            self.assertTrue(any('forbidden SVG' in x or 'unsafe SVG' in x for x in errors),errors)
    def test_reject_infinite(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            m=json.loads((d/'manifest.json').read_text())
            m['nodes'][0]['x']=float('inf')
            (d/'manifest.json').write_text(json.dumps(m))
            errors,_=validate(d)
            self.assertTrue(any('invalid x' in x for x in errors),errors)
    def test_reject_parent_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=self._copy(tmp)
            m=json.loads((d/'manifest.json').read_text())
            m['nodes'][1]['parent']='body'
            (d/'manifest.json').write_text(json.dumps(m))
            errors,_=validate(d)
            self.assertTrue(any('parent cycle' in x for x in errors),errors)
if __name__=='__main__':unittest.main()
