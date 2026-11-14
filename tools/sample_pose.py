#!/usr/bin/env python3
"""Headless MotionPack pose sampler. Uses the canonical bounded isolated ZIP reader.

This is a developer interoperability bridge, NOT a production embeddable
runtime. The Node subprocess evaluates only repository-owned JS code; nothing
from the archive is executed. Poses are data, not rendered images.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

try:
    from .archive_reader import ArchiveError, read_package
except ImportError:
    from archive_reader import ArchiveError, read_package

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_FRAME_BYTES = 8 * 1024 * 1024
NODE_SCRIPT = Path(__file__).resolve().parent.parent / "runtime" / "headless_pose.js"


def sample_archive(archive, *, time_ms, clip=None, variant=None, node_executable="node"):
    if not 0 <= time_ms <= 2**53 - 1:
        raise ValueError("time must be a finite nonnegative number")
    package = read_package(archive)
    request = {
        "manifest": package.manifest,
        "options": {"timeMs": time_ms, "clip": clip, "variant": variant},
    }
    command = json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(command) > MAX_INPUT_BYTES:
        raise ValueError("manifest is too large for the headless pose bridge")
    process = subprocess.run(
        [node_executable, str(NODE_SCRIPT)],
        input=command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
        check=False,
    )
    if process.returncode:
        raise ValueError("headless pose evaluation failed")
    if len(process.stdout) > MAX_FRAME_BYTES:
        raise ValueError("pose frame exceeds output budget")
    result = json.loads(process.stdout)
    if result.get("protocol") != "motionpack-pose" or result.get("version") != 1:
        raise ValueError("unexpected pose protocol")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate a .motionpack as a portable JSON pose (no browser/HTML)."
    )
    parser.add_argument("archive", help="validated v0.1-v0.4 .motionpack package")
    parser.add_argument("--time-ms", type=float, default=0)
    parser.add_argument("--clip", default=None)
    parser.add_argument("--variant", default=None)
    parser.add_argument("--out", default=None,
                        help="optional new JSON destination; default stdout")
    args = parser.parse_args()
    try:
        frame = sample_archive(args.archive, time_ms=args.time_ms,
                               clip=args.clip, variant=args.variant)
        payload = json.dumps(frame, ensure_ascii=False, allow_nan=False,
                             separators=(",", ":")) + "\n"
        if args.out:
            path = Path(args.out)
            with path.open("x", encoding="utf-8") as file:
                file.write(payload)
        else:
            sys.stdout.write(payload)
    except (ArchiveError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        # Do not echo untrusted archive paths, text, or subprocess stderr.
        print("MotionPack headless sample rejected or failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
