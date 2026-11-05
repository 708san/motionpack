"""Private stdio worker for isolated_archive_reader; not a public CLI."""
import json
import os
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from archive_reader import ArchiveError, ReaderLimits, read_package  # noqa: E402
from isolated_archive_reader import _snapshot_archive  # noqa: E402

MAGIC = b"MPIR\x01"
MAX_REQUEST_BYTES = 128 * 1024
MAX_RESPONSE_BYTES = 40 * 1024 * 1024


def _read_exact(stream, size):
    chunks = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise ValueError("truncated worker request")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _apply_linux_memory_limit(memory_limit_bytes):
    if not memory_limit_bytes:
        return
    import resource

    limit = resource.RLIMIT_AS
    _, hard = resource.getrlimit(limit)
    if hard != resource.RLIM_INFINITY:
        memory_limit_bytes = min(memory_limit_bytes, hard)
    resource.setrlimit(limit, (memory_limit_bytes, memory_limit_bytes))


def _encode_success(package, max_bytes):
    manifest = json.dumps(package.manifest, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
    assets = package.assets
    chunks = [MAGIC, b"\x00", struct.pack("!I", len(manifest)), manifest,
              struct.pack("!I", len(assets))]
    total = sum(map(len, chunks))
    for asset_id, data in assets.items():
        encoded_id = asset_id.encode("utf-8")
        piece = struct.pack("!IQ", len(encoded_id), len(data)) + encoded_id + data
        total += len(piece)
        if total > max_bytes:
            raise ValueError("worker result exceeds its byte limit")
        chunks.append(piece)
    if total > max_bytes:
        raise ValueError("worker result exceeds its byte limit")
    return b"".join(chunks)


def main():
    source = sys.stdin.buffer
    if _read_exact(source, 1) != b"G":
        return 2
    request_size = struct.unpack("!I", _read_exact(source, 4))[0]
    if request_size > MAX_REQUEST_BYTES:
        return 2
    try:
        request = json.loads(_read_exact(source, request_size).decode("utf-8"))
        limits = ReaderLimits(**request["limits"])
        memory_limit = request["memory_limit_bytes"]
        if os.name != "nt":
            _apply_linux_memory_limit(memory_limit)
        snapshot = request["snapshot_path"]
    except MemoryError:
        response = MAGIC + b"\x03"
    except BaseException:
        response = MAGIC + b"\x04"
    else:
        try:
            _snapshot_archive(request["path"], snapshot, limits)
        except ArchiveError:
            response = MAGIC + b"\x01"
        except MemoryError:
            response = MAGIC + b"\x03"
        except BaseException:
            response = MAGIC + b"\x04"
        else:
            try:
                package = read_package(snapshot, limits=limits)
                response = _encode_success(package, MAX_RESPONSE_BYTES)
            except ArchiveError:
                response = MAGIC + b"\x02"
            except MemoryError:
                response = MAGIC + b"\x03"
            except BaseException:
                response = MAGIC + b"\x04"
    sys.stdout.buffer.write(response)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
