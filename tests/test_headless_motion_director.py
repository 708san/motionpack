"""Host-neutral procedural motion parity and explicit opt-in tests."""
import io
import json
import pathlib
import shutil
import tempfile
import unittest

from tools.package import build
from tools.pose_session import serve
from tools.sample_pose import sample_archive

ROOT = pathlib.Path(__file__).resolve().parent.parent


def exchange(archive, commands):
    output = io.StringIO()
    serve(archive, input_stream=io.StringIO(
        "".join(json.dumps(cmd) + "\n" for cmd in commands)), output_stream=output)
    return [json.loads(line) for line in output.getvalue().splitlines()]


@unittest.skipUnless(shutil.which("node"), "Node.js required")
class HeadlessMotionDirectorTests(unittest.TestCase):
    def test_overlay_changes_pose_then_restores_exact_base(self):
        with tempfile.TemporaryDirectory() as temp:
            archive, _ = build(ROOT / "examples" / "robot_ik_demo", temp)
            profile = {"channels": [
                {"id": "gentle-bob", "node": "mech", "property": "y",
                 "amplitude": 10, "periodMs": 1000, "phase": 0},
            ]}
            commands = [
                {"timeMs": 250, "clip": "idle"},
                {"type": "configureMotion", "profile": profile},
                {"timeMs": 250, "clip": "idle", "motionTimeMs": 250},
                {"timeMs": 250, "clip": "idle", "motionTimeMs": 250},
                {"type": "configureMotion", "profile": None},
                {"timeMs": 250, "clip": "idle"},
            ]
            replies = exchange(archive, commands)
            self.assertEqual(replies[0]["type"], "ready")
            self.assertEqual(replies[2], {"type": "motionConfigured", "enabled": True})
            base = replies[1]["frame"]
            overlay = replies[3]["frame"]
            self.assertEqual(overlay, replies[4]["frame"], "same sampled time is deterministic")
            self.assertEqual(replies[5], {"type": "motionConfigured", "enabled": False})
            self.assertEqual(replies[6]["frame"], base)
            self.assertEqual(base, sample_archive(archive, clip="idle", time_ms=250))
            old = next(n for n in base["nodes"] if n["id"] == "mech")
            new = next(n for n in overlay["nodes"] if n["id"] == "mech")
            self.assertAlmostEqual(new["local"]["y"]-old["local"]["y"], 10)
            self.assertAlmostEqual(new["world"][5]-old["world"][5], 10)
            self.assertEqual([n["asset"] for n in base["nodes"]],
                             [n["asset"] for n in overlay["nodes"]])

    def test_rejected_motion_profile_preserves_last_valid_instance(self):
        with tempfile.TemporaryDirectory() as temp:
            archive, _ = build(ROOT / "examples" / "robot_ik_demo", temp)
            commands = [
                {"type": "configureMotion", "profile": {"channels": [
                    {"id": "one", "node": "mech", "property": "rotation",
                     "amplitude": 6, "periodMs": 1000}
                ]}},
                {"type": "configureMotion", "profile": {"channels": [
                    {"id": "unsafe", "node": "missing", "property": "rotation",
                     "amplitude": 6, "periodMs": 1000}
                ]}},
                {"timeMs": 250, "clip": "idle", "motionTimeMs": 250},
                {"type": "configureMotion", "profile": None},
                {"timeMs": 250, "clip": "idle"},
            ]
            replies = exchange(archive, commands)
            self.assertEqual(replies[1], {"type": "motionConfigured", "enabled": True})
            self.assertEqual(replies[2], {"type": "error", "code": "INVALID_REQUEST"})
            baseline = replies[5]["frame"]
            animated = replies[3]["frame"]
            old = next(n for n in baseline["nodes"] if n["id"] == "mech")
            new = next(n for n in animated["nodes"] if n["id"] == "mech")
            self.assertAlmostEqual(new["local"]["rotation"] - old["local"]["rotation"], 6)

    def test_unexpected_request_field_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            archive, _ = build(ROOT / "examples" / "robot_demo", temp)
            with self.assertRaises(ValueError):
                exchange(archive, [{"type": "configureMotion",
                                    "profile": {"channels": []}, "script": "evil"}])


if __name__ == "__main__":
    unittest.main()
