"""Headless runtime CLI integration with the bounded packaged archive reader."""
import json
import pathlib
import shutil
import tempfile
import unittest

from tools.package import build
from tools.sample_pose import sample_archive

ROOT = pathlib.Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which("node"), "Node.js needed for headless integration")
class HeadlessPoseIntegrationTests(unittest.TestCase):
    def test_archive_round_trip_for_all_supported_sample_types(self):
        for example in ("robot_demo", "robot_ik_demo", "layered_plant_demo",
                        "interaction_demo"):
            with self.subTest(example=example), tempfile.TemporaryDirectory() as temp:
                archive, _ = build(ROOT / "examples" / example, pathlib.Path(temp))
                manifest = json.loads((ROOT / "examples" / example / "manifest.json").read_text())
                pose = sample_archive(archive, time_ms=750)
                self.assertEqual(pose["protocol"], "motionpack-pose")
                self.assertEqual(pose["version"], 1)
                self.assertEqual(pose["clip"], manifest["defaults"]["clip"])
                self.assertEqual(len(pose["nodes"]), len(manifest["nodes"]))
                self.assertEqual(pose["canvas"]["width"], manifest["canvas"]["width"])
                self.assertTrue(all(len(node["world"]) == 6 for node in pose["nodes"]))

    def test_nonloop_clip_ends_and_variant_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            archive, _ = build(ROOT / "examples" / "robot_ik_demo", temp)
            pose = sample_archive(archive, clip="fire", variant="form_b", time_ms=9999)
            self.assertEqual(pose["time_ms"], 2500)
            body = next(node for node in pose["nodes"] if node["id"] == "body")
            self.assertEqual(body["asset"], "torso_power")

    def test_invalid_package_and_unsupported_clip_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            bad = pathlib.Path(temp) / "bad.motionpack"
            bad.write_bytes(b"not a valid zip")
            with self.assertRaises(ValueError):
                sample_archive(bad, time_ms=0)
            archive, _ = build(ROOT / "examples" / "robot_demo", temp)
            with self.assertRaises(ValueError):
                sample_archive(archive, time_ms=0, clip="__proto__")
            with self.assertRaises(ValueError):
                sample_archive(archive, time_ms=float("nan"))

    def test_idempotent_sampling(self):
        with tempfile.TemporaryDirectory() as temp:
            archive, _ = build(ROOT / "examples" / "robot_ik_demo", temp)
            self.assertEqual(sample_archive(archive, time_ms=1200),
                             sample_archive(archive, time_ms=1200))


if __name__ == "__main__":
    unittest.main()
