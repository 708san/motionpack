"""Optional process-isolated decoder for explicitly referenced static raster assets.

The worker is resource limited where supported, but is not an OS permission
sandbox. This API does not change package formats or existing preview behavior.
"""
from dataclasses import dataclass
import json
import math
import os
import pathlib
import struct
import subprocess
import sys
import tempfile
import threading
import time
from typing import Mapping

try:
    from .archive_reader import MAX_ASSETS, MAX_ASSET, MAX_TOTAL_ASSETS
    from .isolated_process import (
        DEFAULT_MEMORY_LIMIT_BYTES, kill_worker, read_bounded_output, windows_job,
    )
    from .validate import (
        MAX_PNG_DIMENSION, MAX_PNG_PIXELS, MAX_TOTAL_PNG_PIXELS,
        RasterHeaderError, RasterLimitError, parse_raster_dimensions, parse_webp_raster,
    )
except ImportError:  # Support direct imports from the tools directory.
    from archive_reader import MAX_ASSETS, MAX_ASSET, MAX_TOTAL_ASSETS
    from isolated_process import (
        DEFAULT_MEMORY_LIMIT_BYTES, kill_worker, read_bounded_output, windows_job,
    )
    from validate import (
        MAX_PNG_DIMENSION, MAX_PNG_PIXELS, MAX_TOTAL_PNG_PIXELS,
        RasterHeaderError, RasterLimitError, parse_raster_dimensions, parse_webp_raster,
    )

MAX_TIMEOUT_SECONDS = 300.0
MAX_ASSET_ID_BYTES = 1024
WORKER_SCRIPT = pathlib.Path(__file__).with_name("raster_decode_worker.py")
REQUEST_MAGIC = b"MPRQ\x01"
RESPONSE_MAGIC = b"MPRS\x01"
FORMAT_NAMES = {1: "PNG", 2: "JPEG", 3: "WEBP"}
RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class RasterDecodeError(RuntimeError):
    """An input image is unsupported, malformed, or rejected by the worker."""


class RasterDecodeTimeout(RasterDecodeError):
    """The decoder worker exceeded its deadline."""


class RasterDecodeResourceLimit(RasterDecodeError):
    """The decoder exceeded a configured process, input, or output limit."""


class RasterDecodeWorkerFailure(RasterDecodeError):
    """The decoder worker exited or returned an invalid response."""


class UnsupportedMemoryLimit(RasterDecodeError):
    """The requested hard memory limit is unavailable on this platform."""


@dataclass(frozen=True)
class RasterDecodeLimits:
    max_dimension: int = MAX_PNG_DIMENSION
    max_image_pixels: int = MAX_PNG_PIXELS
    max_input_pixels: int = MAX_TOTAL_PNG_PIXELS
    max_decoded_pixels: int = MAX_TOTAL_PNG_PIXELS
    max_asset_bytes: int = MAX_ASSET
    max_total_asset_bytes: int = MAX_TOTAL_ASSETS
    max_assets: int = MAX_ASSETS
    max_response_bytes: int = MAX_TOTAL_PNG_PIXELS * 4 + 2 * 1024 * 1024

    def __post_init__(self):
        values = (
            (self.max_dimension, MAX_PNG_DIMENSION),
            (self.max_image_pixels, MAX_PNG_PIXELS),
            (self.max_input_pixels, MAX_TOTAL_PNG_PIXELS),
            (self.max_decoded_pixels, MAX_TOTAL_PNG_PIXELS),
            (self.max_asset_bytes, MAX_ASSET),
            (self.max_total_asset_bytes, MAX_TOTAL_ASSETS),
            (self.max_assets, MAX_ASSETS),
            (self.max_response_bytes, MAX_TOTAL_PNG_PIXELS * 4 + 2 * 1024 * 1024),
        )
        if any(type(value) is not int or value < 1 or value > ceiling for value, ceiling in values):
            raise ValueError("raster decoder limits must be positive and cannot exceed tool maxima")


@dataclass(frozen=True)
class DecodedRaster:
    image_format: str
    width: int
    height: int
    rgba: bytes


def _safe_inputs(assets, asset_paths, limits):
    if not isinstance(assets, Mapping) or not isinstance(asset_paths, Mapping):
        raise TypeError("assets and asset_paths must be mappings")
    if set(assets) != set(asset_paths) or len(assets) > limits.max_assets:
        raise ValueError("asset bytes and paths must have the same bounded keys")
    total_bytes = 0
    total_pixels = 0
    unique = {}
    aliases = {}
    expected_dimensions = {}
    for asset_id, data in assets.items():
        if not isinstance(asset_id, str) or not asset_id or len(asset_id.encode("utf-8")) > MAX_ASSET_ID_BYTES:
            raise ValueError("invalid raster asset ID")
        path = asset_paths[asset_id]
        if not isinstance(path, str):
            raise ValueError("asset paths must be strings")
        pure = pathlib.PurePosixPath(path)
        parts = pure.parts
        if (pure.is_absolute() or not parts or ".." in parts
                or parts[0].casefold() == "source" or "\\" in path):
            raise ValueError("raster decoder requires a safe runtime asset path")
        path = pure.as_posix()
        if len(path.encode("utf-8")) > MAX_ASSET_ID_BYTES:
            raise ValueError("validated raster asset path exceeds protocol limit")
        extension = pure.suffix.lower()
        if extension not in RASTER_SUFFIXES:
            raise ValueError("raster decoder only accepts PNG, JPEG, and WebP assets")
        if not isinstance(data, bytes) or len(data) > limits.max_asset_bytes:
            raise RasterDecodeResourceLimit("raster input asset exceeds its byte limit")
        if path in unique:
            previous_data, previous_extension = unique[path]
            if data != previous_data or extension != previous_extension:
                raise ValueError("one asset path cannot refer to different raster bytes")
            aliases[asset_id] = path
            continue
        total_bytes += len(data)
        if total_bytes > limits.max_total_asset_bytes:
            raise RasterDecodeResourceLimit("raster input assets exceed aggregate byte limit")
        try:
            if extension == ".webp":
                width, height, cost = parse_webp_raster(
                    data, limits.max_dimension, limits.max_image_pixels,
                    limits.max_input_pixels - total_pixels,
                )
            else:
                width, height = parse_raster_dimensions(data, extension)
                cost = width * height
                if width > limits.max_dimension or height > limits.max_dimension:
                    raise RasterLimitError("raster dimension limit exceeded")
                if cost > limits.max_image_pixels or total_pixels + cost > limits.max_input_pixels:
                    raise RasterLimitError("raster pixel budget exceeded")
        except (RasterHeaderError, RasterLimitError) as exc:
            raise RasterDecodeError("raster header validation failed") from exc
        total_pixels += cost
        unique[path] = (data, extension)
        expected_dimensions[path] = (width, height)
        aliases[asset_id] = path
    return unique, aliases, expected_dimensions


def _make_request(unique, limits, memory_limit):
    metadata = json.dumps({
        "memory_limit_bytes": memory_limit,
        "max_assets": limits.max_assets,
        "max_asset_id_bytes": MAX_ASSET_ID_BYTES,
        "max_asset_bytes": limits.max_asset_bytes,
        "max_total_asset_bytes": limits.max_total_asset_bytes,
        "max_dimension": limits.max_dimension,
        "max_image_pixels": limits.max_image_pixels,
        "max_input_pixels": limits.max_input_pixels,
        "max_decoded_pixels": limits.max_decoded_pixels,
        "max_response_bytes": limits.max_response_bytes,
    }, separators=(",", ":"), allow_nan=False).encode("utf-8")
    chunks = [REQUEST_MAGIC, struct.pack("!I", len(metadata)), metadata,
              struct.pack("!I", len(unique))]
    for path, (data, extension) in unique.items():
        encoded_id = path.encode("utf-8")
        encoded_extension = extension.encode("ascii")
        chunks.extend((struct.pack("!H B Q", len(encoded_id), len(encoded_extension), len(data)),
                       encoded_id, encoded_extension, data))
    return b"".join(chunks)


def _decode_response(stream, unique, aliases, expected_dimensions, limits):
    def take(size):
        result = stream.read(size)
        if len(result) != size:
            raise RasterDecodeWorkerFailure("truncated raster worker response")
        return result

    magic_and_status = take(len(RESPONSE_MAGIC) + 1)
    if magic_and_status[:len(RESPONSE_MAGIC)] != RESPONSE_MAGIC:
        raise RasterDecodeWorkerFailure("invalid raster worker response")
    status = magic_and_status[-1]
    if status == 1:
        if stream.read(1):
            raise RasterDecodeWorkerFailure("invalid raster worker failure response")
        raise RasterDecodeError("raster decoder rejected the image")
    if status == 2:
        if stream.read(1):
            raise RasterDecodeWorkerFailure("invalid raster worker failure response")
        raise RasterDecodeResourceLimit("raster decoder worker exceeded its memory limit")
    if status != 0:
        raise RasterDecodeWorkerFailure("raster decoder worker failed")

    count = struct.unpack("!I", take(4))[0]
    if count != len(unique):
        raise RasterDecodeWorkerFailure("raster worker returned an unexpected asset count")
    decoded = {}
    total_pixels = 0
    expected_paths = set(unique)
    for _ in range(count):
        id_size = struct.unpack("!H", take(2))[0]
        if not 1 <= id_size <= MAX_ASSET_ID_BYTES:
            raise RasterDecodeWorkerFailure("invalid raster worker asset ID length")
        try:
            path = bytes(take(id_size)).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RasterDecodeWorkerFailure("invalid raster worker asset ID") from exc
        if path not in expected_paths or path in decoded:
            raise RasterDecodeWorkerFailure("unexpected or duplicate raster worker asset")
        format_code, width, height, frame_width, frame_height, byte_count = struct.unpack(
            "!BIIIIQ", take(25)
        )
        expected_format = {".png": 1, ".jpg": 2, ".jpeg": 2, ".webp": 3}[unique[path][1]]
        if (format_code != expected_format
                or (width, height) != expected_dimensions[path] or not all(
            1 <= value <= limits.max_dimension for value in (width, height, frame_width, frame_height)
        ) or frame_width * frame_height != width * height):
            raise RasterDecodeWorkerFailure("raster worker returned invalid format or dimensions")
        pixels = frame_width * frame_height
        if (pixels > limits.max_image_pixels or byte_count != pixels * 4
                or total_pixels + pixels > limits.max_decoded_pixels):
            raise RasterDecodeResourceLimit("raster worker returned pixels outside configured limits")
        total_pixels += pixels
        rgba = take(byte_count)
        decoded[path] = DecodedRaster(FORMAT_NAMES[format_code], frame_width, frame_height, rgba)
    if stream.read(1) or set(decoded) != expected_paths:
        raise RasterDecodeWorkerFailure("invalid raster worker response framing")
    return {asset_id: decoded[path] for asset_id, path in aliases.items()}


def decode_raster_assets_isolated(assets, asset_paths, *, limits=None, timeout=30.0,
                                  memory_limit_bytes=None):
    """Return RGBA assets from a separate worker; only static raster images are supported.

    ``assets`` maps manifest asset IDs to already bounded bytes. ``asset_paths``
    maps those IDs to their validated package paths. The worker receives bytes,
    never a package path. This is resource isolation, not a security sandbox.
    """
    limits = limits or RasterDecodeLimits()
    if not isinstance(limits, RasterDecodeLimits):
        raise TypeError("limits must be a RasterDecodeLimits instance")
    if (type(timeout) not in (int, float) or not math.isfinite(timeout)
            or timeout <= 0 or timeout > MAX_TIMEOUT_SECONDS):
        raise ValueError("timeout must be positive and at most 300 seconds")
    if memory_limit_bytes is not None and (type(memory_limit_bytes) is not int or memory_limit_bytes < 0):
        raise ValueError("memory_limit_bytes must be a non-negative integer or None")
    if memory_limit_bytes is None:
        memory_limit = DEFAULT_MEMORY_LIMIT_BYTES if os.name == "nt" or sys.platform.startswith("linux") else 0
    else:
        memory_limit = memory_limit_bytes
    if memory_limit and sys.platform == "darwin":
        raise UnsupportedMemoryLimit("a hard whole-process memory limit is unsupported on macOS")
    if memory_limit and os.name != "nt" and not sys.platform.startswith("linux"):
        raise UnsupportedMemoryLimit("memory limits are supported only on Linux and Windows")

    unique, aliases, expected_dimensions = _safe_inputs(assets, asset_paths, limits)
    if not unique:
        return {}
    request = _make_request(unique, limits, memory_limit)
    started = time.monotonic()
    temp_dir = tempfile.TemporaryDirectory(prefix="motionpack-raster-worker-")
    child_environment = {}
    for key in ("PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL", "LC_CTYPE"):
        if key in os.environ:
            child_environment[key] = os.environ[key]
    if os.name == "nt":
        child_environment.update({"TEMP": temp_dir.name, "TMP": temp_dir.name})
    else:
        child_environment["TMPDIR"] = temp_dir.name
    command = [sys.executable, "-I", str(pathlib.Path(WORKER_SCRIPT).resolve())]
    kwargs = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE,
              "stderr": subprocess.DEVNULL, "cwd": temp_dir.name,
              "close_fds": True, "env": child_environment}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        process = subprocess.Popen(command, **kwargs)
    except OSError as exc:
        temp_dir.cleanup()
        raise RasterDecodeWorkerFailure("unable to start raster decoder worker") from exc
    job = None
    output = tempfile.TemporaryFile(mode="w+b", dir=temp_dir.name)
    overflow = threading.Event()
    reader_stop = threading.Event()
    writer = None
    reader = threading.Thread(
        target=read_bounded_output,
        args=(
            process.stdout, output, overflow, process,
            limits.max_response_bytes, reader_stop,
        ),
        daemon=True,
    )
    def write_request():
        try:
            process.stdin.write(request)
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass

    try:
        if os.name == "nt":
            try:
                job = windows_job(process, memory_limit)
            except OSError as exc:
                raise RasterDecodeResourceLimit("unable to configure Windows decoder limits") from exc
        # Apply the Windows Job Object limits before the worker can read any
        # image bytes and enter a native decoder.
        reader.start()
        writer = threading.Thread(target=write_request, daemon=True)
        writer.start()
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise RasterDecodeTimeout("raster decoder timed out")
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise RasterDecodeTimeout("raster decoder timed out") from exc
        writer.join(max(0.0, timeout - (time.monotonic() - started)))
        reader.join(max(0.0, timeout - (time.monotonic() - started)))
        if writer.is_alive() or reader.is_alive():
            raise RasterDecodeTimeout("raster decoder protocol did not finish before deadline")
        if overflow.is_set():
            raise RasterDecodeResourceLimit("raster decoder response exceeded its byte limit")
        if process.returncode != 0:
            raise RasterDecodeWorkerFailure("raster decoder worker exited unexpectedly")
        output.flush()
        output.seek(0)
        return _decode_response(output, unique, aliases, expected_dimensions, limits)
    except BaseException:
        reader_stop.set()
        kill_worker(process, job)
        job = None
        raise
    finally:
        if job is not None or process.poll() is None or os.name != "nt":
            kill_worker(process, job)
        if writer is not None:
            writer.join(1.0)
        if reader.is_alive():
            reader_stop.set()
            reader.join(1.0)
        for stream in (process.stdin, process.stdout):
            if stream is not None and not stream.closed and (
                stream is not process.stdout or not reader.is_alive()
            ):
                stream.close()
        output.close()
        temp_dir.cleanup()
