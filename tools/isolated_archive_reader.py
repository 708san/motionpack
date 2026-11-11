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
import unicodedata

try:
    from .archive_reader import (ArchiveError, MotionPackArchive, ReaderLimits, _canonical_asset_path, _file_identity, _is_source_path, _json_object, _member_parts, check_json_nesting)
except ImportError:  # Support direct import when tools/ is on sys.path.
    from archive_reader import (ArchiveError, MotionPackArchive, ReaderLimits, _canonical_asset_path, _file_identity, _is_source_path, _json_object, _member_parts, check_json_nesting)


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
PROTOCOL_MAGIC = b"MPIR\x02"
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
        before = source.stat()
        if not stat.S_ISREG(before.st_mode):
            raise ArchiveError("archive input must be a regular file")
        expected_identity = _file_identity(before)
        if expected_identity is None:
            raise ArchiveError("archive input identity cannot be verified")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(source, flags)
    except ArchiveError:
        raise
    except (OSError, RuntimeError) as exc:
        raise ArchiveError("unable to snapshot MotionPack archive") from exc

    try:
        initial = os.fstat(descriptor)
        if not stat.S_ISREG(initial.st_mode):
            raise ArchiveError("archive input must be a regular file")
        if _file_identity(initial) != expected_identity:
            raise ArchiveError("archive input changed between stat and open")
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


def _decode_result(payload, limits, include_entries=False):
    view = memoryview(payload)
    if len(view) < len(PROTOCOL_MAGIC) + 1 or bytes(view[:len(PROTOCOL_MAGIC)]) != PROTOCOL_MAGIC:
        raise IsolatedReadError("invalid isolated reader response")
    position = len(PROTOCOL_MAGIC)
    status = view[position]
    position += 1
    if status in (1, 2, 3):
        if position != len(view):
            raise IsolatedReadError("invalid isolated reader error response")
        if status == 1:
            raise ArchiveError("isolated input snapshot was rejected")
        if status == 2:
            raise ArchiveError("isolated archive was rejected")
        raise IsolatedResourceLimit("isolated reader worker exceeded a resource or response-size limit")
    if status != 0:
        raise IsolatedWorkerFailure("isolated reader worker failed")

    def take(size):
        nonlocal position
        if size < 0 or position + size > len(view):
            raise IsolatedReadError("truncated isolated reader response")
        result = view[position:position + size]
        position += size
        return result

    entry_count = struct.unpack("!I", take(4))[0]
    if entry_count == 0 or entry_count > limits.max_entries:
        raise IsolatedReadError("isolated reader returned an invalid entry count")
    entries = {}
    canonical_entries = {}
    total_bytes = 0
    for _ in range(entry_count):
        name_size, data_size = struct.unpack("!IQ", take(12))
        if name_size == 0 or name_size > 1024 or data_size > limits.max_total_uncompressed:
            raise IsolatedReadError("isolated reader entry exceeded its limit")
        try:
            name = bytes(take(name_size)).decode("utf-8")
            _member_parts(name)
        except (UnicodeDecodeError, ArchiveError) as exc:
            raise IsolatedReadError("invalid isolated reader entry name") from exc
        normalized_name = unicodedata.normalize("NFC", name)
        if name in entries or normalized_name in canonical_entries or name.endswith("/"):
            raise IsolatedReadError("isolated reader returned a duplicate or directory entry")
        canonical_entries[normalized_name] = name
        total_bytes += data_size
        if total_bytes > limits.max_total_uncompressed:
            raise IsolatedReadError("isolated reader entries exceeded their aggregate limit")
        entries[name] = bytes(take(data_size))
    if position != len(view) or "manifest.json" not in entries:
        raise IsolatedReadError("invalid isolated reader response framing")

    manifest_bytes = entries["manifest.json"]
    if len(manifest_bytes) > limits.max_manifest_bytes:
        raise IsolatedReadError("isolated reader manifest exceeded its limit")
    try:
        manifest_text = manifest_bytes.decode("utf-8")
        check_json_nesting(manifest_text)
        manifest = json.loads(
            manifest_text, object_pairs_hook=_json_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite JSON number")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise IsolatedReadError("invalid isolated reader manifest response") from exc
    if not isinstance(manifest, dict):
        raise IsolatedReadError("isolated reader returned a non-object manifest")

    declared_assets = manifest.get("assets")
    if not isinstance(declared_assets, dict) or len(declared_assets) > 512:
        raise IsolatedReadError("isolated reader returned invalid asset declarations")
    assets = {}
    expected_names = {"manifest.json"}
    total_asset_bytes = 0
    for asset_id, raw_path in declared_assets.items():
        if not isinstance(asset_id, str):
            raise IsolatedReadError("isolated reader returned an invalid asset ID")
        try:
            canonical = _canonical_asset_path(raw_path)
        except ArchiveError as exc:
            raise IsolatedReadError("isolated reader returned an unsafe asset path") from exc
        if _is_source_path(canonical):
            raise IsolatedReadError("isolated reader returned a source runtime asset")
        actual_name = canonical_entries.get(unicodedata.normalize("NFC", canonical))
        if actual_name is None:
            raise IsolatedReadError("isolated reader omitted a referenced asset")
        data = entries[actual_name]
        expected_names.add(actual_name)
        if len(data) > limits.max_asset_bytes:
            raise IsolatedReadError("isolated reader asset exceeded its limit")
        total_asset_bytes += len(data)
        if total_asset_bytes > limits.max_total_assets_bytes:
            raise IsolatedReadError("isolated reader assets exceeded their aggregate limit")
        assets[asset_id] = data
    if not include_entries and set(entries) != expected_names:
        raise IsolatedReadError("isolated reader returned unexpected entries")
    return MotionPackArchive(
        manifest=manifest, assets=assets, manifest_bytes=manifest_bytes, entries=entries
    )

def read_package_isolated(path, *, limits=None, timeout=30.0, memory_limit_bytes=None, include_entries=False):
    """Read a package in a fresh process with a deadline and bounded IPC.

    The default policy applies a 512 MiB address-space limit on Linux and a
    512 MiB committed-memory Job Object limit on Windows. macOS has no supported
    whole-process hard memory limit here; explicitly requesting one there fails.
    Set ``memory_limit_bytes=0`` to disable an OS memory limit. This is not a
    complete sandbox and does not change the synchronous ``read_package`` API.
    Set ``include_entries=True`` to retain all regular-file payloads (including
    opaque source entries); the complete framed response remains capped at 40 MiB.
    """
    limits = limits or ReaderLimits()
    if not isinstance(limits, ReaderLimits):
        raise TypeError("limits must be a ReaderLimits instance")
    if type(include_entries) is not bool:
        raise TypeError("include_entries must be a bool")
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
    max_result = MAX_RESULT_BYTES if include_entries else min(
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
             "limits": limits.__dict__, "memory_limit_bytes": memory_limit,
             "include_entries": include_entries},
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
            return _decode_result(output, limits, include_entries=include_entries)
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

