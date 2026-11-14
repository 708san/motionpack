"""Round-trip acceptance test for the first GPT-authored MotionPack candidate."""
import json
import pathlib
import tempfile
import unittest
import zipfile

from tools.package import build
from tools.validate import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROJECT = ROOT / "examples" / "gpt_lantern_pilot"


class GPTLanternPilotTests(unittest.TestCase):
    def test_generation_round_trip_preserves_editable_assets(self):
        errors, manifest = validate(PROJECT)
        self.assertEqual(errors, [], errors)
        self.assertEqual(manifest["version"], "0.3")
        self.assertEqual(len(manifest["assets"]), 3)
        self.assertEqual(set(manifest["clips"]), {"float"})
        with tempfile.TemporaryDirectory() as folder:
            package, preview = build(PROJECT, pathlib.Path(folder) / "dist")
            self.assertTrue(preview.is_file())
            with zipfile.ZipFile(package) as archive:
                self.assertEqual(set(archive.namelist()),
                                 {"manifest.json", *manifest["assets"].values()})
                self.assertEqual(json.loads(archive.read("manifest.json"))["assets"],
                                 manifest["assets"])
                for name in manifest["assets"].values():
                    self.assertEqual(archive.read(name), (PROJECT / name).read_bytes())
            self.assertIn("window.__MOTIONPACK__", preview.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
