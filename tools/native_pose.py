#!/usr/bin/env python3
"""Validate a .motionpack with the isolated reader, then sample it through Rust.

Developer interoperability bridge: actual archive -> native pose JSON.
This tool does not render, decode images or execute code from a package.
"""
import argparse
import ctypes as c
import json
import math
from pathlib import Path
import platform
import sys

try:
    from .archive_reader import ArchiveError, read_package
except ImportError:
    from archive_reader import ArchiveError, read_package

ROOT = Path(__file__).resolve().parent.parent
NATIVE_FILENAME = {
    "Windows": "motionpack_core.dll",
    "Darwin": "libmotionpack_core.dylib",
    "Linux": "libmotionpack_core.so",
}
PROPERTIES = ("x", "y", "rotation", "scale", "opacity")
MAX_FRAMES = 100000


class Node(c.Structure):
    _fields_ = [("parent", c.c_int32)] + [(p, c.c_double) for p in PROPERTIES]


class Variant(c.Structure):
    _fields_ = [("node", c.c_uint32), ("mask", c.c_uint32)] + [
        (p, c.c_double) for p in PROPERTIES]


class Track(c.Structure):
    _fields_ = [(k, c.c_uint32) for k in ("node", "property", "key_start", "key_count")]


class Key(c.Structure):
    _fields_ = [("time_ms", c.c_double), ("value", c.c_double)]


class Chain(c.Structure):
    _fields_ = [("upper", c.c_uint32), ("lower", c.c_uint32)] + [
        (k, c.c_double) for k in ("length1", "length2", "target_x",
                                  "target_y", "bend", "weight")]


class IkTrack(c.Structure):
    _fields_ = [(k, c.c_uint32) for k in ("chain", "axis", "key_start", "key_count")]


class Target(c.Structure):
    _fields_ = [("chain", c.c_uint32), ("x", c.c_double), ("y", c.c_double)]


class Output(c.Structure):
    _fields_ = [(k, c.c_double) for k in (
        "x", "y", "rotation", "scale", "opacity",
        "a", "b", "c", "d", "tx", "ty")]


def _array(cls, values):
    return (cls * len(values))(*values)


def _finite(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("invalid " + label)
    return float(value)


def _native_library(path=None):
    if path is None:
        system = platform.system()
        if system not in NATIVE_FILENAME:
            raise ValueError("unsupported native operating system")
        path = ROOT / "core" / "target" / "debug" / NATIVE_FILENAME[system]
    library = c.CDLL(str(Path(path).resolve()))
    sample_fn = library.mp_scene_sample_v1
    sample_fn.restype = c.c_int32
    sample_fn.argtypes = [
        c.POINTER(Node), c.c_size_t,
        c.POINTER(Variant), c.c_size_t,
        c.POINTER(Track), c.c_size_t,
        c.POINTER(Key), c.c_size_t,
        c.POINTER(Chain), c.c_size_t,
        c.POINTER(IkTrack), c.c_size_t,
        c.POINTER(Target), c.c_size_t,
        c.c_double, c.c_uint32, c.c_double,
        c.POINTER(Output), c.c_size_t, c.POINTER(c.c_double)
    ]
    return sample_fn


class NativePoseSession:
    """One validated archive and one native Rust library, reusable for frames."""

    def __init__(self, archive, *, library_path=None):
        package = read_package(archive)
        self.manifest = package.manifest
        self.sample_fn = _native_library(library_path)
        self.base = self.manifest["nodes"]
        self.ids = {node["id"]: i for i, node in enumerate(self.base)}
        self.iks = self.manifest.get("iks", [])
        self.ik_ids = {ik["id"]: i for i, ik in enumerate(self.iks)}
        if len(self.ids) != len(self.base) or len(self.ik_ids) != len(self.iks):
            raise ValueError("duplicate node or IK identifiers")
        self.nodes = _array(Node, [
            Node(-1 if not node.get("parent") else self.ids[node["parent"]],
                 *(node.get(prop, 1 if prop in ("scale", "opacity") else 0)
                   for prop in PROPERTIES))
            for node in self.base
        ])
        self.chains = _array(Chain, [
            Chain(self.ids[ik["upper"]], self.ids[ik["lower"]],
                  *ik["lengths"], *ik["target"],
                  ik.get("bend", 1), ik.get("weight", 1))
            for ik in self.iks
        ])
        self._clip_cache = {}
        self._variant_cache = {}
        for name, variant in self.manifest["variants"].items():
            numeric = []
            for node_id, changes in variant.get("nodes", {}).items():
                mask = sum(1 << i for i, prop in enumerate(PROPERTIES)
                           if prop in changes)
                if mask:
                    numeric.append(Variant(self.ids[node_id], mask,
                        *(changes.get(prop, 0) for prop in PROPERTIES)))
            self._variant_cache[name] = _array(Variant, numeric)
        for name, clip in self.manifest["clips"].items():
            keys = []
            tracks = []
            ik_tracks = []
            for tr in clip.get("tracks", []):
                start = len(keys)
                keys.extend(Key(k["time_ms"], k["value"]) for k in tr["keys"])
                tracks.append(Track(self.ids[tr["node"]],
                                    PROPERTIES.index(tr["property"]),
                                    start, len(tr["keys"])))
            for tr in clip.get("ik_tracks", []):
                start = len(keys)
                keys.extend(Key(k["time_ms"], k["value"]) for k in tr["keys"])
                ik_tracks.append(IkTrack(self.ik_ids[tr["ik"]],
                                         0 if tr["axis"] == "x" else 1,
                                         start, len(tr["keys"])))
            self._clip_cache[name] = (
                clip, _array(Track, tracks), _array(Key, keys),
                _array(IkTrack, ik_tracks)
            )

    def sample(self, *, time_ms=0, clip=None, variant=None, ik_targets=None):
        time_ms = _finite(time_ms, "timeMs")
        if time_ms < 0 or time_ms > 2**53 - 1:
            raise ValueError("timeMs outside supported range")
        clip = clip if clip is not None else self.manifest["defaults"]["clip"]
        variant = variant if variant is not None else self.manifest["defaults"]["variant"]
        if not isinstance(clip, str) or clip not in self._clip_cache:
            raise ValueError("unknown clip")
        if not isinstance(variant, str) or variant not in self._variant_cache:
            raise ValueError("unknown variant")
        if ik_targets is not None and not isinstance(ik_targets, dict):
            raise ValueError("IK targets must be an object")
        targets = []
        for name, point in (ik_targets or {}).items():
            if name not in self.ik_ids or not isinstance(point, list) or len(point) != 2:
                raise ValueError("invalid IK target")
            targets.append(Target(self.ik_ids[name], *(
                _finite(coord, "IK coordinate") for coord in point)))
        target_array = _array(Target, targets)
        info, tracks, keys, ik_tracks = self._clip_cache[clip]
        overrides = self._variant_cache[variant]
        output = (Output * len(self.base))()
        sampled = c.c_double(-1)
        status = self.sample_fn(
            self.nodes, len(self.nodes), overrides, len(overrides),
            tracks, len(tracks), keys, len(keys),
            self.chains, len(self.chains),
            ik_tracks, len(ik_tracks), target_array, len(target_array),
            info["duration_ms"], 1 if info.get("loop", False) else 0,
            time_ms, output, len(output), c.byref(sampled)
        )
        if status != 0:
            raise ValueError("native scene evaluation rejected")
        entries = []
        for index, (base, result) in enumerate(zip(self.base, output)):
            patched = {**base, **self.manifest["variants"][variant]
                       .get("nodes", {}).get(base["id"], {})}
            local = {p: getattr(result, p) for p in PROPERTIES}
            entries.append({
                "id": base["id"], "parent": patched.get("parent"),
                "asset": patched.get("asset"), "z": patched.get("z", 0),
                "width": patched.get("width", 0),
                "height": patched.get("height", 0),
                "anchor": patched.get("anchor", [0.5, 0.5]),
                "local": local,
                "world": [result.a, result.b, result.c, result.d,
                          result.tx, result.ty]
            })
        entries.sort(key=lambda item: item["z"])
        effects = []
        for effect in info.get("effects", []):
            age = sampled.value - effect["start_ms"]
            if 0 <= age <= effect["duration_ms"]:
                effects.append({**effect, "age_ms": age,
                                "progress": age / effect["duration_ms"]})
        return {
            "protocol": "motionpack-pose", "version": 1,
            "clip": clip, "variant": variant, "time_ms": sampled.value,
            "canvas": {"width": self.manifest["canvas"]["width"],
                       "height": self.manifest["canvas"]["height"],
                       "background": self.manifest["canvas"].get("background")},
            "nodes": entries, "effects": effects
        }


def main():
    parser = argparse.ArgumentParser(
        description="Sample a validated .motionpack through the native Rust core.")
    parser.add_argument("archive")
    parser.add_argument("--time-ms", type=float, default=0)
    parser.add_argument("--clip")
    parser.add_argument("--variant")
    parser.add_argument("--out")
    args = parser.parse_args()
    try:
        frame = NativePoseSession(args.archive).sample(
            time_ms=args.time_ms, clip=args.clip, variant=args.variant)
        payload = json.dumps(frame, ensure_ascii=False, allow_nan=False,
                             separators=(",", ":")) + "\n"
        if args.out:
            with Path(args.out).open("x", encoding="utf-8") as destination:
                destination.write(payload)
        else:
            sys.stdout.write(payload)
        return 0
    except (ValueError, ArchiveError, OSError, KeyError, OverflowError):
        print("MotionPack native pose rejected or failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
