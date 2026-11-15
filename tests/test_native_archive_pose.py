"""End-to-end native Rust .motionpack pose parity against the JS reference."""
import json
import pathlib
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.native_pose import NativePoseSession, NATIVE_FILENAME
from tools.package import build
from tools.sample_pose import sample_archive

ROOT = pathlib.Path(__file__).resolve().parents[1]


def compare_frames(testcase, actual, expected, context):
    testcase.assertEqual((actual["protocol"], actual["version"]),
                         ("motionpack-pose", 1))
    testcase.assertEqual((actual["clip"], actual["variant"]),
                         (expected["clip"], expected["variant"]))
    testcase.assertEqual(actual["canvas"], expected["canvas"])
    testcase.assertEqual(len(actual["nodes"]), len(expected["nodes"]))
    testcase.assertAlmostEqual(actual["time_ms"], expected["time_ms"],
                               delta=1e-7)
    for a, b in zip(actual["nodes"], expected["nodes"]):
        for key in ("id", "parent", "asset", "z", "width", "height", "anchor"):
            testcase.assertEqual(a[key], b[key], context + " " + key)
        for key in ("x", "y", "rotation", "scale", "opacity"):
            testcase.assertAlmostEqual(a["local"][key], b["local"][key],
                delta=2e-7 * max(1, abs(b["local"][key])),
                msg=context + " " + a["id"] + " local " + key)
        for i, (x, y) in enumerate(zip(a["world"], b["world"])):
            testcase.assertAlmostEqual(x, y,
                delta=2e-7 * max(1, abs(y)),
                msg=context + " " + a["id"] + " world " + str(i))
    testcase.assertEqual(len(actual["effects"]), len(expected["effects"]))
    for a, b in zip(actual["effects"], expected["effects"]):
        testcase.assertEqual(set(a), set(b))
        for key in b:
            if key in ("age_ms", "progress"):
                testcase.assertAlmostEqual(a[key], b[key], delta=1e-7)
            else:
                testcase.assertEqual(a[key], b[key])


@unittest.skipUnless(shutil.which("node") and
    (ROOT / "core" / "target" / "debug" /
     NATIVE_FILENAME.get(platform.system(), "unsupported-platform")).exists(),
    "native Rust library and Node.js are required")
class NativeArchivePoseTests(unittest.TestCase):
    def test_packaged_archive_native_matches_js_and_reuses_one_session(self):
        # Build all archives using the real packager, not hand-assembled JSON.
        with tempfile.TemporaryDirectory() as temp:
            count = 0
            for example in ("robot_ik_demo", "robot_demo", "layered_plant_demo"):
                archive, _ = build(ROOT / "examples" / example, temp)
                session = NativePoseSession(archive)
                for clip, desc in session.manifest["clips"].items():
                    for variant in session.manifest["variants"]:
                        for time in (0, desc["duration_ms"] // 3,
                                     desc["duration_ms"], desc["duration_ms"] + 123):
                            target_options = (None,)
                            if session.iks:
                                target_options = (None, {
                                    session.iks[0]["id"]: [760, 320]
                                })
                            for targets in target_options:
                                actual = session.sample(time_ms=time, clip=clip,
                                    variant=variant, ik_targets=targets)
                                # Existing JS one-shot CLI does not accept IK
                                # overrides, so use independent JS headless script
                                # for those in the parity helper below.
                                expected = reference_frame(
                                    session.manifest, time, clip, variant, targets)
                                compare_frames(self, actual, expected,
                                    f"{example}/{clip}/{variant}@{time}")
                                count += 1
            self.assertGreaterEqual(count, 70)

    def test_invalid_inputs_and_archives(self):
        with tempfile.TemporaryDirectory() as temp:
            archive, _ = build(ROOT / "examples" / "robot_ik_demo", temp)
            session = NativePoseSession(archive)
            for invalid in (
                {"time_ms": -1}, {"time_ms": float("nan")},
                {"clip": "missing"}, {"variant": "missing"},
                {"ik_targets": {"unknown": [100, 200]}},
                {"ik_targets": {"aim_right": [1]}},
                {"ik_targets": {"aim_right": [1, float("inf")]}},
            ):
                with self.subTest(invalid=invalid):
                    with self.assertRaises(ValueError):
                        session.sample(**invalid)
            bad = pathlib.Path(temp) / "invalid.motionpack"
            bad.write_bytes(b"not a zip")
            with self.assertRaises(ValueError):
                NativePoseSession(bad)

    def test_cli_emits_native_pose_json(self):
        with tempfile.TemporaryDirectory() as temp:
            archive, _ = build(ROOT / "examples" / "robot_demo", temp)
            run = subprocess.run(
                [sys.executable, "-m", "tools.native_pose", str(archive),
                 "--time-ms", "250"],
                cwd=ROOT, capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            self.assertEqual(result["protocol"], "motionpack-pose")
            self.assertEqual(result["version"], 1)
            # Old JS and new native Rust produce the same frame contract.
            expected = sample_archive(archive, time_ms=250)
            compare_frames(self, result, expected, "CLI")


def reference_frame(manifest, time, clip, variant, targets):
    # A fixed repository-owned Node entrypoint only, no archive-controlled code.
    request = {"manifest": manifest, "options": {
        "timeMs": time, "clip": clip, "variant": variant, "ikTargets": targets}}
    cmd = subprocess.run(
        ["node", str(ROOT / "runtime" / "headless_pose.js")],
        cwd=ROOT, input=json.dumps(request), capture_output=True,
        text=True, timeout=15)
    if cmd.returncode:
        raise ValueError("JavaScript reference rejected a validated test case")
    return json.loads(cmd.stdout)


if __name__ == "__main__":
    unittest.main()
