"""Cross-OS ctypes smoke test of the Rust caller-owned numeric scene ABI."""
import ctypes as c
import pathlib
import platform
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
suffix = {"Windows": "motionpack_core.dll", "Darwin": "libmotionpack_core.dylib",
          "Linux": "libmotionpack_core.so"}[platform.system()]
LIB = ROOT / "core" / "target" / "debug" / suffix


class Node(c.Structure):
    _fields_ = [("parent", c.c_int32)] + [(k, c.c_double) for k in
        ("x", "y", "rotation", "scale", "opacity")]


class Variant(c.Structure):
    _fields_ = [("node", c.c_uint32), ("mask", c.c_uint32)] + [
        (k, c.c_double) for k in ("x", "y", "rotation", "scale", "opacity")]


class Key(c.Structure):
    _fields_ = [("time_ms", c.c_double), ("value", c.c_double)]


class Track(c.Structure):
    _fields_ = [(k, c.c_uint32) for k in
                ("node", "property", "key_start", "key_count")]


class Chain(c.Structure):
    _fields_ = [("upper", c.c_uint32), ("lower", c.c_uint32)] + [
        (k, c.c_double) for k in ("length1", "length2", "target_x",
                                  "target_y", "bend", "weight")]


class IkTrack(c.Structure):
    _fields_ = [(k, c.c_uint32) for k in
                ("chain", "axis", "key_start", "key_count")]


class Target(c.Structure):
    _fields_ = [("chain", c.c_uint32), ("x", c.c_double), ("y", c.c_double)]


class Output(c.Structure):
    _fields_ = [(k, c.c_double) for k in
                ("x", "y", "rotation", "scale", "opacity",
                 "a", "b", "c", "d", "tx", "ty")]


@unittest.skipUnless(LIB.exists(), "Rust library must be built first")
class NativeSceneAbiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = c.CDLL(str(LIB))
        cls.sample_fn = cls.library.mp_scene_sample_v1
        cls.sample_fn.restype = c.c_int32
        cls.sample_fn.argtypes = [
            c.POINTER(Node), c.c_size_t,
            c.POINTER(Variant), c.c_size_t,
            c.POINTER(Track), c.c_size_t,
            c.POINTER(Key), c.c_size_t,
            c.POINTER(Chain), c.c_size_t,
            c.POINTER(IkTrack), c.c_size_t,
            c.POINTER(Target), c.c_size_t,
            c.c_double, c.c_uint32, c.c_double,
            c.POINTER(Output), c.c_size_t, c.POINTER(c.c_double)]

    def test_tracks_variants_parent_and_error_atomicity(self):
        nodes = (Node * 2)(Node(-1, 10, 20, 0, 1, 1),
                           Node(0, 5, 3, 0, 1, 1))
        variant = (Variant * 1)(Variant(1, 4, 0, 0, 30, 0, 0))
        tracks = (Track * 1)(Track(0, 1, 0, 2))
        keys = (Key * 2)(Key(0, 20), Key(1000, 40))
        output = (Output * 2)()
        sampled = c.c_double(-1)

        def call(flag=1, count=2, capacity=2):
            return self.sample_fn(nodes, count, variant, 1, tracks, 1, keys, 2,
                            None, 0, None, 0, None, 0,
                            1000, flag, 500, output, capacity, c.byref(sampled))

        self.assertEqual(call(), 0)
        self.assertEqual(sampled.value, 500)
        self.assertAlmostEqual(output[0].y, 30)
        self.assertAlmostEqual(output[1].ty, 33)
        self.assertAlmostEqual(output[1].rotation, 30)
        self.assertAlmostEqual(output[1].tx, 15)
        previous = (sampled.value, output[1].tx, output[1].ty)
        self.assertEqual(call(flag=2), 1)
        self.assertEqual((sampled.value, output[1].tx, output[1].ty), previous)
        self.assertEqual(call(capacity=1), 1)
        self.assertEqual((sampled.value, output[1].tx, output[1].ty), previous)
        self.assertEqual(call(count=4097), 1)

    def test_ik_changes_world_pose(self):
        nodes = (Node * 3)(Node(-1, 0, 0, 0, 1, 1),
                           Node(0, 0, 0, 0, 1, 1),
                           Node(1, 100, 0, 0, 1, 1))
        chain = (Chain * 1)(Chain(1, 2, 100, 80, 100, 50, -1, 1))
        output = (Output * 3)()
        sampled = c.c_double()
        result = self.sample_fn(nodes, 3, None, 0, None, 0, None, 0,
                          chain, 1, None, 0, None, 0,
                          1000, 0, 250, output, 3, c.byref(sampled))
        self.assertEqual(result, 0)
        self.assertEqual(sampled.value, 250)
        self.assertAlmostEqual(output[2].x, 100)
        self.assertNotAlmostEqual(output[1].rotation, 0)


if __name__ == "__main__":
    unittest.main()
