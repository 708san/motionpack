"""Opt-in process-isolated wrapper for untrusted MotionPack ZIP inspection.

This is defense in depth, not a sandbox. Platform memory enforcement differs:
Linux limits address space, Windows limits committed process memory, and macOS
has no supported hard memory limit in this implementation.
"""
import json
import math
import os
import pathlib
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time

try:
    from .archive_reader import ArchiveError, MotionPackArchive, ReaderLimits
except ImportError:  # Support direct import when tools/ is on sys.path.
    from archive_reader import ArchiveError, MotionPackArchive, ReaderLimits


try:
    from .isolated_process import (
        DEFAULT_MEMORY_LIMIT_BYTES, kill_worker as _kill_worker,
        read_bounded_output as _read_output, windows_job as _windows_job,
    )
except ImportError:  # Support direct execution/import from the tools directory.
    from isolated_process import (
        DEFAULT_MEMORY_LIMIT_BYTES, kill_worker as _kill_worker,
        read_bounded_output as _read_output, windows_job as _windows_job,
    )
MAX_SNAPSHOT_BYTES = 40 * 1024 * 1024
MAX_RESULT_BYTES = 40 * 1024 * 1024
MAX_REQUEST_BYTES = 128 * 1024
MAX_TIMEOUT_SECONDS = 300.0
PROTOCOL_MAGIC = b"MPIR\x01"
WORKER_SCRIPT = pathlib.Path(__file__).with_name("archive_reader_worker.py")


class IsolatedReadError(RuntimeError):
    """The isolated reader could not complete its bounded protocol."""


class IsolatedReadTimeout(IsolatedReadError):
    """The worker exceeded its wall-clock deadline."""


class IsolatedResourceLimit(IsolatedReadError):
    """A worker exceeded or could not apply a requested resource limit."""


class IsolatedWorkerFailure(IsolatedReadError):
    """The worker exited without a valid bounded response."""


class UnsupportedMemoryLimit(IsolatedReadError):
    """This platform cannot enforce the requested memory ceiling."""


def _snapshot_archive(source, destination, limits):
    source = pathlib.Path(source)
    try:
        if not stat.S_ISREG(source.stat().st_mode):
            raise ArchiveError("archive input must be a regular file")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(source, flags)
    except ArchiveError:
        raise
    except OSError as exc:
        raise ArchiveError("unable to snapshot MotionPack archive") from exc

    try:
        initial = os.fstat(descriptor)
        if not stat.S_ISREG(initial.st_mode):
            raise ArchiveError("archive input must be a regular file")
        ceiling = min(limits.max_archive_bytes, MAX_SNAPSHOT_BYTES)
        if initial.st_size > ceiling:
            raise ArchiveError("archive file size exceeds isolated reader limit")
        total = 0
        with os.fdopen(descriptor, "rb", closefd=False) as source_file:
            with open(destination, "wb") as snapshot:
                while True:
                    chunk = source_file.read(min(64 * 1024, ceiling - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > ceiling:
                        raise ArchiveError("archive file size exceeds isolated reader limit")
                    snapshot.write(chunk)
        final = os.fstat(descriptor)
        if (initial.st_size, initial.st_mtime_ns, initial.st_ino) != (
            final.st_size, final.st_mtime_ns, final.st_ino
        ) or total != final.st_size:
            raise ArchiveError("archive input changed while taking isolated snapshot")
    finally:
        os.close(descriptor)


def _decode_result(payload, limits):
    view = memoryview(payload)
    if len(view) < len(PROTOCOL_MAGIC) + 1 or bytes(view[:len(PROTOCOL_MAGIC)]) != PROTOCOL_MAGIC:
        raise IsolatedReadError("invalid isolated reader response")
    position = len(PROTOCOL_MAGIC)
    status = view[position]
    position += 1
    if status == 1:
        if position != len(view):
            raise IsolatedReadError("invalid isolated reader rejection response")
        raise ArchiveError("isolated input snapshot was rejected")
    if status == 2:
        if position != len(view):
            raise IsolatedReadError("invalid isolated reader rejection response")
        raise ArchiveError("isolated archive was rejected")
    if status == 3:
        if position != len(view):
            raise IsolatedReadError("invalid isolated reader resource response")
        raise IsolatedResourceLimit("isolated reader worker exceeded its memory limit")
    if status != 0:
        raise IsolatedWorkerFailure("isolated reader worker failed")

    def take(size):
        nonlocal position
        if size < 0 or position + size > len(view):
            raise IsolatedReadError("truncated isolated reader response")
        result = view[position:position + size]
        position += size
        return result

    manifest_size = struct.unpack("!I", take(4))[0]
    if manifest_size > limits.max_manifest_bytes:
        raise IsolatedReadError("isolated reader manifest exceeded its limit")
    try:
        manifest = json.loads(bytes(take(manifest_size)).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise IsolatedReadError("invalid isolated reader manifest response") from exc
    asset_count = struct.unpack("!I", take(4))[0]
    if asset_count > 512:
        raise IsolatedReadError("isolated reader returned too many assets")
    assets = {}
    total_asset_bytes = 0
    for _ in range(asset_count):
        asset_id_size, asset_size = struct.unpack("!IQ", take(12))
        if asset_id_size > limits.max_manifest_bytes:
            raise IsolatedReadError("isolated reader asset ID exceeded its limit")
        try:
            asset_id = bytes(take(asset_id_size)).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise IsolatedReadError("invalid isolated reader asset ID") from exc
        if asset_size > limits.max_asset_bytes:
            raise IsolatedReadError("isolated reader asset exceeded its limit")
        total_asset_bytes += asset_size
        if total_asset_bytes > limits.max_total_assets_bytes:
            raise IsolatedReadError("isolated reader assets exceeded their aggregate limit")
        if asset_id in assets:
            raise IsolatedReadError("isolated reader returned duplicate asset IDs")
        assets[asset_id] = bytes(take(asset_size))
    if position != len(view) or not isinstance(manifest, dict):
        raise IsolatedReadError("invalid isolated reader response framing")
    manifest_assets = manifest.get("assets")
    if not isinstance(manifest_assets, dict) or set(manifest_assets) != set(assets):
        raise IsolatedReadError("isolated reader returned inconsistent assets")
    return MotionPackArchive(manifest=manifest, assets=assets)


def read_package_isolated(path, *, limits=None, timeout=30.0, memory_limit_bytes=None):
    """Read a package in a fresh process with a deadline and bounded IPC.

    The default policy applies a 512 MiB address-space limit on Linux and a
    512 MiB committed-memory Job Object limit on Windows. macOS has no supported
    whole-process hard memory limit here; explicitly requesting one there fails.
    Set ``memory_limit_bytes=0`` to disable an OS memory limit. This is not a
    complete sandbox and does not change the synchronous ``read_package`` API.
    """
    limits = limits or ReaderLimits()
    if not isinstance(limits, ReaderLimits):
        raise TypeError("limits must be a ReaderLimits instance")
    if (type(timeout) not in (int, float) or not math.isfinite(timeout)
            or timeout <= 0 or timeout > MAX_TIMEOUT_SECONDS):
        raise ValueError("timeout must be positive and at most 300 seconds")
    if memory_limit_bytes is not None and (
        type(memory_limit_bytes) is not int or memory_limit_bytes < 0
    ):
        raise ValueError("memory_limit_bytes must be a non-negative integer or None")

    if memory_limit_bytes is None:
        memory_limit = DEFAULT_MEMORY_LIMIT_BYTES if os.name == "nt" or sys.platform.startswith("linux") else 0
    else:
        memory_limit = memory_limit_bytes
    if memory_limit and sys.platform == "darwin":
        raise UnsupportedMemoryLimit("a hard total-process memory limit is unsupported on macOS")
    if memory_limit and os.name != "nt" and not sys.platform.startswith("linux"):
        raise UnsupportedMemoryLimit("memory limits are supported only on Linux and Windows")
    max_result = min(
        MAX_RESULT_BYTES,
        limits.max_manifest_bytes * 2 + limits.max_total_assets_bytes + 64 * 1024,
    )
    if max_result <= 0:
        raise ValueError("configured result budget is invalid")

    started = time.monotonic()
    source_path = pathlib.Path(path).expanduser().absolute()
    with tempfile.TemporaryDirectory(prefix="motionpack-isolated-") as temp_dir:
        snapshot = pathlib.Path(temp_dir) / "input.motionpack"
        request = json.dumps(
            {"path": str(source_path), "snapshot_path": str(snapshot),
             "limits": limits.__dict__, "memory_limit_bytes": memory_limit},
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        if len(request) > MAX_REQUEST_BYTES:
            raise ValueError("isolated reader request exceeds its limit")
        command = [sys.executable, "-I", str(WORKER_SCRIPT.resolve())]
        keep_environment = ("PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL", "LC_CTYPE")
        child_environment = {key: os.environ[key] for key in keep_environment if key in os.environ}
        if os.name == "nt":
            child_environment.update({"TEMP": temp_dir, "TMP": temp_dir})
        else:
            child_environment["TMPDIR"] = temp_dir
        kwargs = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE,
                  "stderr": subprocess.DEVNULL, "cwd": temp_dir, "close_fds": True,
                  "env": child_environment}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(command, **kwargs)
        job = None
        worker_cleaned = False
        output = bytearray()
        overflow = threading.Event()
        reader = threading.Thread(
            target=_read_output, args=(process.stdout, output, overflow, process, max_result), daemon=True
        )
        reader.start()
        try:
            if os.name == "nt":
                try:
                    job = _windows_job(process, memory_limit)
                except OSError as exc:
                    _kill_worker(process)
                    raise IsolatedResourceLimit("unable to configure Windows worker job limits") from exc
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise IsolatedReadTimeout("isolated archive read timed out")
            process.stdin.write(b"G" + struct.pack("!I", len(request)) + request)
            process.stdin.flush()
            process.stdin.close()
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired as exc:
                raise IsolatedReadTimeout("isolated archive read timed out") from exc
            reader.join(max(0.0, timeout - (time.monotonic() - started)))
            if reader.is_alive():
                raise IsolatedReadTimeout("isolated archive result did not finish before deadline")
            if overflow.is_set():
                raise IsolatedResourceLimit("isolated reader response exceeded its byte limit")
            if process.returncode != 0:
                raise IsolatedWorkerFailure("isolated reader worker exited unexpectedly")
            return _decode_result(output, limits)
        except BaseException:
            _kill_worker(process, job)
            job = None
            worker_cleaned = True
            raise
        finally:
            if not worker_cleaned and (process.poll() is None or os.name != "nt"):
                _kill_worker(process, job)
                job = None
                worker_cleaned = True
            if job is not None:
                handle, close_handle = job
                close_handle(handle)
            if reader.is_alive():
                try:
                    process.stdout.close()
                except OSError:
                    pass
                reader.join(1)
            for stream in (process.stdin, process.stdout):
                if stream is not None and not stream.closed:
                    stream.close()

