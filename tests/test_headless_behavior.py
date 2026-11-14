"""End-to-end host-owned semantic behavior tests against a real .motionpack."""
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


def run_session(archive, commands):
    stream = io.StringIO("".join(json.dumps(c) + "\n" for c in commands))
    output = io.StringIO()
    serve(archive, input_stream=stream, output_stream=output)
    return [json.loads(line) for line in output.getvalue().splitlines()]


@unittest.skipUnless(shutil.which("node"), "Node.js required")
class HeadlessBehaviorTests(unittest.TestCase):
    def test_actions_are_host_opt_in_and_do_not_modify_frame_playback(self):
        with tempfile.TemporaryDirectory() as temp:
            archive, _ = build(ROOT / "examples" / "robot_ik_demo", temp)
            profile = {
                "seed": 71,
                "actions": {
                    "greet": {"clip": "fire", "variant": "form_b"},
                    "rest": {"clip": "idle"},
                },
                "ambient": {
                    "minIntervalMs": 1000,
                    "maxIntervalMs": 2000,
                    "choices": [{"action": "greet", "weight": 1}],
                },
            }
            commands = [
                {"timeMs": 590, "clip": "fire", "variant": "form_b"},
                {"type": "act", "action": "greet"},  # No profile: fail closed
                {"type": "configureBehavior", "profile": profile},
                {"type": "act", "action": "greet"},
                {"type": "act", "action": "unknown"},
                {"type": "advanceBehavior", "deltaMs": 15000},
                {"type": "setAutonomy", "enabled": False},
                {"type": "advanceBehavior", "deltaMs": 15000},
                {"type": "setAutonomy", "enabled": True},
                {"type": "advanceBehavior", "deltaMs": 100},
                {"timeMs": 590, "clip": "fire", "variant": "form_b"},
                {"type": "configureBehavior", "profile": None},
                {"type": "act", "action": "greet"},
            ]
            a = run_session(archive, commands)
            b = run_session(archive, commands)
            self.assertEqual(a, b, "same seeded profile and command stream must replay")
            self.assertEqual(a[0], {"type": "ready", "protocol": "motionpack-pose",
                                     "version": 1})
            self.assertEqual(a[1]["type"], "frame")
            self.assertEqual(a[2], {"type": "error", "code": "INVALID_REQUEST"})
            self.assertEqual(a[3], {"type": "behaviorConfigured", "enabled": True})
            self.assertEqual(a[4], {"type": "action", "action": {
                "clip": "fire", "variant": "form_b", "action": "greet"
            }})
            self.assertEqual(a[5], {"type": "action", "action": None})
            events = a[6]["events"]
            self.assertGreater(len(events), 4)
            self.assertTrue(all(e["clip"] == "fire" for e in events))
            self.assertTrue(all(e["scheduledAtMs"] <= 15000 for e in events))
            self.assertEqual(a[7], {"type": "autonomy", "enabled": False})
            self.assertEqual(a[8], {"type": "behaviorEvents", "events": []})
            self.assertEqual(a[9], {"type": "autonomy", "enabled": True})
            self.assertEqual(a[10], {"type": "behaviorEvents", "events": []})
            self.assertEqual(a[11]["frame"], a[1]["frame"])
            self.assertEqual(a[11]["frame"], sample_archive(
                archive, clip="fire", variant="form_b", time_ms=590))
            self.assertEqual(a[12], {"type": "behaviorConfigured", "enabled": False})
            self.assertEqual(a[13], {"type": "error", "code": "INVALID_REQUEST"})

    def test_invalid_profile_is_rejected_without_losing_previous_behavior(self):
        with tempfile.TemporaryDirectory() as temp:
            archive, _ = build(ROOT / "examples" / "robot_ik_demo", temp)
            commands = [
                {"type": "configureBehavior",
                 "profile": {"actions": {"greet": {"clip": "idle"}}}},
                {"type": "configureBehavior",
                 "profile": {"actions": {"greet": {"clip": "not_real"}}}},
                {"type": "act", "action": "greet"},
                {"type": "sample", "timeMs": 100},
            ]
            replies = run_session(archive, commands)
            self.assertEqual(replies[1], {"type": "behaviorConfigured", "enabled": True})
            self.assertEqual(replies[2], {"type": "error", "code": "INVALID_REQUEST"})
            self.assertEqual(replies[3], {"type": "action",
                                           "action": {"clip": "idle", "variant": None,
                                                      "action": "greet"}})
            self.assertEqual(replies[4]["type"], "frame")

    def test_host_rejects_unrecognized_or_executable_request_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            archive, _ = build(ROOT / "examples" / "robot_demo", temp)
            for bad in (
                {"type": "execute", "script": "evil"},
                {"type": "configureBehavior", "profile": None, "execute": "evil"},
                {"type": "sample", "script": "evil"},
            ):
                with self.subTest(request=bad):
                    with self.assertRaises(ValueError):
                        run_session(archive, [bad])


if __name__ == "__main__":
    unittest.main()
