"""Integration tests for one-load, multi-frame headless MotionPack sessions."""
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


@unittest.skipUnless(shutil.which("node"), "Node.js required")
class PoseSessionTests(unittest.TestCase):
    def test_multi_frame_matches_single_frame_evaluator(self):
        with tempfile.TemporaryDirectory() as temp:
            archive, _ = build(ROOT / "examples" / "robot_ik_demo", temp)
            cases = [
                {"timeMs": 0},
                {"timeMs": 1200, "clip": "idle"},
                {"timeMs": 590, "clip": "fire", "variant": "form_b"},
                {"timeMs": 2500, "clip": "fire"},
            ]
            data = io.StringIO("".join(json.dumps(item) + "\n" for item in cases))
            output = io.StringIO()
            serve(archive, input_stream=data, output_stream=output)
            lines = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(lines.pop(0),
                             {"type": "ready", "protocol": "motionpack-pose",
                              "version": 1})
            self.assertEqual(len(lines), len(cases))
            for item, reply in zip(cases, lines):
                self.assertEqual(reply["type"], "frame")
                self.assertEqual(reply["frame"], sample_archive(
                    archive, time_ms=item["timeMs"], clip=item.get("clip"),
                    variant=item.get("variant")))

    def test_invalid_clip_does_not_kill_session(self):
        with tempfile.TemporaryDirectory() as temp:
            archive, _ = build(ROOT / "examples" / "robot_demo", temp)
            data = io.StringIO('{"clip":"missing","timeMs":0}\n{"timeMs":100}\n')
            output = io.StringIO()
            serve(archive, input_stream=data, output_stream=output)
            lines = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(lines[1], {"type": "error", "code": "INVALID_REQUEST"})
            self.assertEqual(lines[2]["type"], "frame")

    def test_bad_request_and_bad_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            archive, _ = build(ROOT / "examples" / "robot_demo", temp)
            with self.assertRaises(ValueError):
                serve(archive, input_stream=io.StringIO('{"script":"evil"}\n'),
                      output_stream=io.StringIO())
            with self.assertRaises(ValueError):
                serve(archive, input_stream=io.StringIO('{"timeMs":NaN}\n'),
                      output_stream=io.StringIO())
            bad = pathlib.Path(temp) / "notzip.motionpack"
            bad.write_bytes(b"not zip")
            with self.assertRaises(ValueError):
                serve(bad, input_stream=io.StringIO('{"timeMs":0}\n'),
                      output_stream=io.StringIO())


if __name__ == "__main__":
    unittest.main()
