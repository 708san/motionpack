"""Private bounded-stdio worker for isolated_raster_decoder."""
import json
import os
import pathlib
import shutil
import struct
import sys
import tempfile
import warnings

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from isolated_process import apply_linux_memory_limit  # noqa: E402

REQUEST_MAGIC = b"MPRQ\x01"
RESPONSE_MAGIC = b"MPRS\x01"
MAX_REQUEST_METADATA = 128 * 1024
MAX_WORKER_RESPONSE_BYTES = 64_000_000 * 4 + 2 * 1024 * 1024
FORMAT_CODES = {"PNG": 1, "JPEG": 2, "WEBP": 3}
EXTENSION_FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}


def _read_exact(stream, size):
    chunks = []
    remaining = size
    while remaining:
        chunk = stream.read(min(64 * 1024, remaining))
        if not chunk:
            raise ValueError("truncated worker request")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_request(stream):
    if _read_exact(stream, len(REQUEST_MAGIC)) != REQUEST_MAGIC:
        raise ValueError("invalid worker request")
    metadata_size = struct.unpack("!I", _read_exact(stream, 4))[0]
    if metadata_size > MAX_REQUEST_METADATA:
        raise ValueError("worker request metadata exceeds limit")
    metadata = json.loads(_read_exact(stream, metadata_size).decode("utf-8"))
    if (not isinstance(metadata, dict)
            or type(metadata.get("max_response_bytes")) is not int
            or not 1 <= metadata["max_response_bytes"] <= MAX_WORKER_RESPONSE_BYTES):
        raise ValueError("invalid worker response byte limit")
    if os.name != "nt":
        apply_linux_memory_limit(metadata["memory_limit_bytes"])

    count = struct.unpack("!I", _read_exact(stream, 4))[0]
    if count > metadata["max_assets"]:
        raise ValueError("worker asset count exceeds limit")
    entries = []
    total_bytes = 0
    seen_ids = set()
    for _ in range(count):
        id_size, extension_size, data_size = struct.unpack("!H B Q", _read_exact(stream, 11))
        if not id_size or id_size > metadata["max_asset_id_bytes"] or extension_size > 8:
            raise ValueError("invalid worker asset header")
        if data_size > metadata["max_asset_bytes"]:
            raise ValueError("worker input asset exceeds limit")
        total_bytes += data_size
        if total_bytes > metadata["max_total_asset_bytes"]:
            raise ValueError("worker input assets exceed aggregate limit")
        asset_id = _read_exact(stream, id_size).decode("utf-8")
        if asset_id in seen_ids:
            raise ValueError("duplicate worker asset ID")
        seen_ids.add(asset_id)
        extension = _read_exact(stream, extension_size).decode("ascii").lower()
        entries.append((asset_id, extension, _read_exact(stream, data_size)))
    return metadata, entries


class InvalidRasterInput(Exception):
    """The bounded static-raster decoder rejected input image data."""


class RasterResourceLimit(Exception):
    """The worker exhausted or exceeded a configured resource bound."""


def _decode_one(asset_id, extension, data, metadata):
    from io import BytesIO
    from PIL import Image, ImageOps, UnidentifiedImageError
    from validate import parse_raster_dimensions, parse_webp_raster, RasterHeaderError, RasterLimitError

    expected_format = EXTENSION_FORMATS.get(extension)
    if expected_format is None:
        raise InvalidRasterInput("unsupported raster extension")
    try:
        if extension == ".webp":
            width, height, _header_pixels = parse_webp_raster(
                data, metadata["max_dimension"], metadata["max_image_pixels"],
                metadata["max_input_pixels"],
            )
        else:
            width, height = parse_raster_dimensions(data, extension)
            header_pixels = width * height
            if width > metadata["max_dimension"] or height > metadata["max_dimension"]:
                raise RasterLimitError("raster dimension limit exceeded")
            if header_pixels > metadata["max_image_pixels"]:
                raise RasterLimitError("raster pixel limit exceeded")
            if header_pixels > metadata["max_input_pixels"]:
                raise RasterLimitError("total raster pixel budget exceeded")
    except (RasterHeaderError, RasterLimitError) as exc:
        raise InvalidRasterInput("raster header validation failed") from exc

    Image.MAX_IMAGE_PIXELS = metadata["max_image_pixels"]
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            opened = Image.open(BytesIO(data), formats=(expected_format,))
        except (UnidentifiedImageError, OSError, SyntaxError,
                Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise InvalidRasterInput("raster decoder rejected the image") from exc

        with opened as image:
            if image.format != expected_format:
                raise InvalidRasterInput("decoded format does not match extension")
            if image.size != (width, height):
                raise InvalidRasterInput("decoded dimensions disagree with header")
            if getattr(image, "n_frames", 1) != 1:
                raise InvalidRasterInput("animated raster is not supported by this decoder")
            try:
                image.load()
            except (OSError, SyntaxError,
                    Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
                raise InvalidRasterInput("raster decoder rejected the image") from exc
            frame = ImageOps.exif_transpose(image).convert("RGBA")
            frame_width, frame_height = frame.size
            pixels = frame_width * frame_height
            if (frame_width < 1 or frame_height < 1
                    or frame_width > metadata["max_dimension"]
                    or frame_height > metadata["max_dimension"]
                    or pixels > metadata["max_image_pixels"]
                    or pixels > metadata["max_decoded_pixels"]):
                raise InvalidRasterInput("decoded raster exceeds limits")
            rgba = frame.tobytes("raw", "RGBA")
            if len(rgba) != pixels * 4:
                raise RuntimeError("decoded RGBA length is inconsistent")
            return asset_id, FORMAT_CODES[expected_format], width, height, frame_width, frame_height, rgba


def _write_response(output, entries, metadata):
    # Do not publish a success prefix until every image has decoded. If a later
    # entry is rejected, main() can then return one clean failure frame.
    with tempfile.TemporaryFile(mode="w+b") as response:
        response_bytes = 0

        def write_bounded(chunk):
            nonlocal response_bytes
            if len(chunk) > metadata["max_response_bytes"] - response_bytes:
                raise RasterResourceLimit("raster worker response exceeds byte limit")
            response.write(chunk)
            response_bytes += len(chunk)

        write_bounded(RESPONSE_MAGIC + b"\x00" + struct.pack("!I", len(entries)))
        total_decoded_pixels = 0
        for asset_id, extension, data in entries:
            result = _decode_one(asset_id, extension, data, metadata)
            _asset_id, format_code, width, height, frame_width, frame_height, rgba = result
            total_decoded_pixels += frame_width * frame_height
            if total_decoded_pixels > metadata["max_decoded_pixels"]:
                raise RasterResourceLimit("decoded image aggregate exceeds limit")
            encoded_id = asset_id.encode("utf-8")
            write_bounded(struct.pack("!H", len(encoded_id)) + encoded_id)
            write_bounded(struct.pack("!BIIIIQ", format_code, width, height, frame_width, frame_height, len(rgba)))
            write_bounded(rgba)
            del rgba
        response.flush()
        response.seek(0)
        shutil.copyfileobj(response, output, length=64 * 1024)


def main():
    output = sys.stdout.buffer
    try:
        metadata, entries = _read_request(sys.stdin.buffer)
        _write_response(output, entries, metadata)
        return 0
    except (MemoryError, RasterResourceLimit):
        output.write(RESPONSE_MAGIC + b"\x02")
    except InvalidRasterInput:
        output.write(RESPONSE_MAGIC + b"\x01")
    except BaseException:
        output.write(RESPONSE_MAGIC + b"\x03")
    output.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
