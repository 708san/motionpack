#!/usr/bin/env python3
"""Persistent headless MotionPack pose session over newline-delimited JSON.

Load each trusted data-only archive exactly once with the repository's bounded
isolated reader. Keep the trusted Node evaluator alive for repeated requests.
This is a local interprocess bridge, not yet a compiled embeddable Unity runtime.
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

SCRIPT = Path(__file__).resolve().parent.parent / "runtime" / "pose_stream.js"
MAX_INIT_BYTES = 2 * 1024 * 1024
MAX_LINE_BYTES = 8192
MAX_RESPONSE_BYTES = 8 * 1024 * 1024 + 1024


def serve(archive, *, input_stream=None, output_stream=None, node_executable="node"):
    input_stream = input_stream if input_stream is not None else sys.stdin
    output_stream = output_stream if output_stream is not None else sys.stdout
    package = read_package(archive)
    init = json.dumps({"manifest": package.manifest}, ensure_ascii=False,
                      allow_nan=False, separators=(",", ":")) + "\n"
    if len(init.encode("utf-8")) > MAX_INIT_BYTES:
        raise ValueError("validated manifest exceeds pose initialization budget")
    process = subprocess.Popen(
        [node_executable, str(SCRIPT)], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    try:
        process.stdin.write(init.encode("utf-8"))
        process.stdin.flush()
        hello = process.stdout.readline(MAX_RESPONSE_BYTES + 1)
        if len(hello) > MAX_RESPONSE_BYTES:
            raise ValueError("pose stream initialization response too large")
        ready = json.loads(hello)
        if ready != {"type": "ready", "protocol": "motionpack-pose", "version": 1}:
            raise ValueError("pose stream initialization failed")
        output_stream.write(json.dumps(ready, separators=(",", ":")) + "\n")
        output_stream.flush()
        count = 0
        for raw in input_stream:
            count += 1
            if count > 100000:
                raise ValueError("pose stream request count exceeded")
            if len(raw.encode("utf-8")) > MAX_LINE_BYTES:
                raise ValueError("pose request exceeds input budget")
            try:
                request = json.loads(raw)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError("malformed pose request") from exc
            if not isinstance(request, dict):
                raise ValueError("pose request must be an object")
            # The trusted host can supply behavior data separately from the
            # archive. Never infer executable actions from .motionpack metadata.
            kind = request.get("type", "sample")
            fields = {
                "sample": {"type", "timeMs", "clip", "variant", "ikTargets"},
                "configureBehavior": {"type", "profile"},
                "act": {"type", "action"},
                "advanceBehavior": {"type", "deltaMs"},
                "setAutonomy": {"type", "enabled"},
            }
            if not isinstance(kind, str) or kind not in fields or set(request) - fields[kind]:
                raise ValueError("unsupported pose request field")
            request["type"] = kind
            data = json.dumps(request, allow_nan=False, separators=(",", ":")) + "\n"
            process.stdin.write(data.encode("utf-8"))
            process.stdin.flush()
            response_bytes = process.stdout.readline(MAX_RESPONSE_BYTES + 1)
            if not response_bytes or len(response_bytes) > MAX_RESPONSE_BYTES:
                raise ValueError("invalid pose response")
            reply = json.loads(response_bytes)
            if not isinstance(reply, dict):
                raise ValueError("unexpected pose result")
            response_type = reply.get("type")
            if response_type == "frame":
                frame = reply.get("frame")
                if not isinstance(frame, dict) or frame.get("protocol") != "motionpack-pose":
                    raise ValueError("unexpected pose frame")
            elif response_type == "action":
                if set(reply) != {"type", "action"} or (
                    reply["action"] is not None and not isinstance(reply["action"], dict)
                ):
                    raise ValueError("unexpected semantic action")
            elif response_type == "behaviorEvents":
                if set(reply) != {"type", "events"} or not isinstance(reply["events"], list):
                    raise ValueError("unexpected ambient events")
            elif response_type == "behaviorConfigured":
                if set(reply) != {"type", "enabled"} or type(reply["enabled"]) is not bool:
                    raise ValueError("unexpected behavior configuration")
            elif response_type == "autonomy":
                if set(reply) != {"type", "enabled"} or type(reply["enabled"]) is not bool:
                    raise ValueError("unexpected autonomy state")
            elif reply != {"type": "error", "code": "INVALID_REQUEST"}:
                raise ValueError("unexpected pose result")
            output_stream.write(json.dumps(reply, ensure_ascii=False,
                                           separators=(",", ":")) + "\n")
            output_stream.flush()
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(
        description="Keep one validated MotionPack loaded; input JSON requests on stdin."
    )
    parser.add_argument("archive")
    args = parser.parse_args()
    try:
        serve(args.archive)
    except (ArchiveError, ValueError, OSError, subprocess.SubprocessError,
            BrokenPipeError):
        print("MotionPack pose session rejected or failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
