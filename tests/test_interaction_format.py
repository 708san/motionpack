import json
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from archive_reader import read_package
from package import build
from validate import validate


class InteractionFormatTests(unittest.TestCase):
    def project(self, tmp):
        project = pathlib.Path(tmp) / "project"
        shutil.copytree(ROOT / "examples" / "robot_ik_demo", project)
        return project, project / "manifest.json"

    def test_v04_flags_validate_package_and_round_trip_through_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, manifest_path = self.project(tmp)
            manifest = json.loads(manifest_path.read_text())
            manifest["version"] = "0.4"
            manifest["nodes"][0]["interaction"] = {"hover": True, "tap": False, "click": True}
            manifest_path.write_text(json.dumps(manifest))

            errors, validated = validate(project)
            self.assertEqual(errors, [], errors)
            self.assertEqual(validated["nodes"][0]["interaction"],
                             {"hover": True, "tap": False, "click": True})
            archive, preview = build(project, pathlib.Path(tmp) / "out")
            self.assertIn("MotionPackInteractionAdapter", preview.read_text(encoding="utf-8"))
            packaged = read_package(archive)
            self.assertEqual(packaged.manifest["version"], "0.4")
            self.assertEqual(packaged.manifest["nodes"][0]["interaction"],
                             {"hover": True, "tap": False, "click": True})

    def test_flags_are_strict_and_rejected_before_v04(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, manifest_path = self.project(tmp)
            manifest = json.loads(manifest_path.read_text())
            manifest["version"] = "0.4"
            for invalid in (None, "true", 1, {}, []):
                manifest["nodes"][0]["interaction"] = {"hover": invalid}
                manifest_path.write_text(json.dumps(manifest))
                errors, _ = validate(project)
                self.assertTrue(any("invalid interaction hover" in error for error in errors), errors)

            manifest["nodes"][0]["interaction"] = {"focus": True}
            manifest_path.write_text(json.dumps(manifest))
            errors, _ = validate(project)
            self.assertTrue(any("unknown interaction flag" in error for error in errors), errors)

            manifest["nodes"][0]["interaction"] = {"tap": True}
            for version in ("0.1", "0.2", "0.3"):
                manifest["version"] = version
                manifest_path.write_text(json.dumps(manifest))
                errors, _ = validate(project)
                self.assertTrue(any("interaction requires format version 0.4" in error
                                    for error in errors), errors)


    def test_v04_interaction_example_validates_and_packages(self):
        project = ROOT / "examples" / "interaction_demo"
        errors, validated = validate(project)
        self.assertEqual(errors, [], errors)
        self.assertEqual(validated["version"], "0.4")
        self.assertEqual(len(validated["nodes"]), 4)

        with tempfile.TemporaryDirectory() as tmp:
            archive, _ = build(project, pathlib.Path(tmp) / "out")
            packaged = read_package(archive)
            nodes = {node["id"]: node for node in packaged.manifest["nodes"]}
            self.assertEqual(nodes["hover_only"]["interaction"], {"hover": True})
            self.assertEqual(nodes["tap_only"]["interaction"], {"tap": True})
            self.assertEqual(nodes["click_only"]["interaction"], {"click": True})
            self.assertNotIn("interaction", nodes["disabled"])

if __name__ == "__main__":
    unittest.main()
