#!/usr/bin/env python3
"""Validate experimental MotionPack v0.1-v0.4 projects, including untrusted inputs.

Validation is intentionally conservative; a passing result is NOT a security certificate.
"""
import json
import math
import os
import pathlib
import re
import stat
import struct
import sys
import zlib
from decimal import Decimal, InvalidOperation, localcontext
import xml.etree.ElementTree as ET
from xml.parsers import expat

ALLOWED_PROPERTIES = {"x", "y", "rotation", "opacity", "scale"}
ALLOWED_EFFECTS = {"beam", "ring", "burst"}
SVG_CANONICAL_TAGS = {
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "defs", "linearGradient", "radialGradient", "stop",
}
SVG_PAINT_ATTRIBUTES = {
    "fill", "stroke", "stroke-width", "opacity",
}
SVG_ATTRIBUTES = {
    "svg": {"width", "height", "viewBox"},
    "g": set(),
    "path": {"d"} | SVG_PAINT_ATTRIBUTES,
    "rect": {"x", "y", "width", "height", "rx", "ry"} | SVG_PAINT_ATTRIBUTES,
    "circle": {"cx", "cy", "r"} | SVG_PAINT_ATTRIBUTES,
    "ellipse": {"cx", "cy", "rx", "ry"} | SVG_PAINT_ATTRIBUTES,
    "line": {"x1", "y1", "x2", "y2", "stroke", "stroke-width", "opacity"},
    "polyline": {"points"} | SVG_PAINT_ATTRIBUTES,
    "polygon": {"points"} | SVG_PAINT_ATTRIBUTES,
    "defs": set(),
    "lineargradient": {"id"},
    "radialgradient": {"id"},
    "stop": {"offset", "stop-color"},
}
MAX_MANIFEST = 1024 * 1024
MAX_ASSET = 12 * 1024 * 1024
MAX_TOTAL_ASSETS = 32 * 1024 * 1024
MAX_PNG_DIMENSION = 8192
MAX_PNG_PIXELS = 16_000_000
MAX_TOTAL_PNG_PIXELS = 64_000_000
MAX_SVG_DIMENSION = 8192
MAX_SVG_PIXELS = 16_000_000
PNG_SPEC_MAX_DIMENSION = 0x7FFFFFFF
MAX_NODES = 1000
MAX_ASSETS = 512
MAX_TRACKS = 2000
MAX_EFFECTS = 1000
MAX_JSON_DEPTH = 64
MAX_SVG_DEPTH = 128
MAX_SVG_ELEMENTS = 10000
MAX_SVG_ATTRIBUTES_PER_ELEMENT = 128
MAX_SVG_ATTRIBUTE = 64 * 1024
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
SUPPORTS_DIR_FD_OPEN = os.open in os.supports_dir_fd
SVG_URL = re.compile(r"url\s*\(", re.I)
SVG_LOCAL_URL = re.compile(r"url\(\s*(?:#([A-Za-z_][A-Za-z0-9_.:-]*)|(['\"])#([A-Za-z_][A-Za-z0-9_.:-]*)\2)\s*\)", re.I)


class RasterHeaderError(ValueError):
    """A malformed or unsupported raster header was rejected."""


class RasterLimitError(ValueError):
    """A raster header exceeds a configured dimension or per-image limit."""

def parse_png_dimensions(data):
    """Read and validate only the PNG signature and first IHDR chunk."""
    if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise RasterHeaderError("invalid PNG signature or truncated IHDR")
    if struct.unpack_from(">I", data, 8)[0] != 13 or data[12:16] != b"IHDR":
        raise RasterHeaderError("invalid PNG IHDR framing")
    ihdr = data[16:29]
    expected_crc = struct.unpack_from(">I", data, 29)[0]
    if zlib.crc32(data[12:29]) & 0xFFFFFFFF != expected_crc:
        raise RasterHeaderError("invalid PNG IHDR CRC")

    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
        ">IIBBBBB", ihdr
    )
    valid_depths = {
        0: {1, 2, 4, 8, 16},
        2: {8, 16},
        3: {1, 2, 4, 8},
        4: {8, 16},
        6: {8, 16},
    }
    if (width == 0 or height == 0 or width > PNG_SPEC_MAX_DIMENSION or height > PNG_SPEC_MAX_DIMENSION
            or bit_depth not in valid_depths.get(color_type, set())
            or compression != 0 or filter_method != 0 or interlace not in (0, 1)):
        raise RasterHeaderError("invalid PNG IHDR values")
    return width, height


def parse_jpeg_dimensions(data):
    """Read JPEG dimensions from a bounded marker scan before the first scan."""
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise RasterHeaderError("invalid JPEG signature")

    sof_markers = set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0))
    position = 2
    while position < len(data):
        if data[position] != 0xFF:
            raise RasterHeaderError("invalid JPEG marker framing")
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            raise RasterHeaderError("truncated JPEG marker")
        marker = data[position]
        position += 1
        if marker == 0x00:
            raise RasterHeaderError("unexpected stuffed JPEG marker")
        if marker == 0xD8:
            raise RasterHeaderError("unexpected nested JPEG start marker")
        if marker == 0xD9:
            raise RasterHeaderError("JPEG dimensions are missing")
        if 0xD0 <= marker <= 0xD7:
            raise RasterHeaderError("unexpected JPEG restart marker")
        if marker == 0x01:
            continue
        if marker == 0xDA:
            raise RasterHeaderError("JPEG dimensions are missing before scan data")
        if position + 2 > len(data):
            raise RasterHeaderError("truncated JPEG segment length")
        segment_length = struct.unpack_from(">H", data, position)[0]
        if segment_length < 2 or position + segment_length > len(data):
            raise RasterHeaderError("invalid or truncated JPEG segment")
        segment_start = position + 2
        segment_end = position + segment_length
        if marker in sof_markers:
            if segment_length < 8:
                raise RasterHeaderError("invalid JPEG frame header")
            precision = data[segment_start]
            height, width = struct.unpack_from(">HH", data, segment_start + 1)
            components = data[segment_start + 5]
            if segment_length != 8 + 3 * components or components == 0:
                raise RasterHeaderError("invalid JPEG frame header length")
            if precision == 0 or width == 0 or height == 0:
                raise RasterHeaderError("invalid JPEG frame dimensions")
            return width, height
        position = segment_end
    raise RasterHeaderError("JPEG dimensions are missing")


def _parse_webp_bitstream_dimensions(chunk_type, data, payload_start, payload_end):
    if chunk_type == b"VP8 ":
        if payload_end - payload_start < 10:
            raise RasterHeaderError("truncated WebP VP8 frame header")
        frame = data[payload_start:payload_start + 10]
        if frame[0] & 1 or frame[3:6] != b"\x9d\x01\x2a":
            raise RasterHeaderError("invalid WebP VP8 frame signature")
        width = int.from_bytes(frame[6:8], "little") & 0x3FFF
        height = int.from_bytes(frame[8:10], "little") & 0x3FFF
        if not width or not height:
            raise RasterHeaderError("invalid WebP VP8 dimensions")
        return width, height
    if chunk_type == b"VP8L":
        if payload_end - payload_start < 5:
            raise RasterHeaderError("truncated WebP VP8L header")
        header = data[payload_start:payload_start + 5]
        if header[0] != 0x2F or header[4] & 0xE0:
            raise RasterHeaderError("invalid WebP VP8L header")
        bits = int.from_bytes(header[1:5], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    raise RasterHeaderError("unsupported WebP bitstream chunk")


def _parse_webp_frame(data, payload_start, payload_end, canvas_width, canvas_height,
                      max_dimension, max_pixels):
    if payload_end - payload_start < 16:
        raise RasterHeaderError("truncated WebP animation frame header")
    frame_x = int.from_bytes(data[payload_start:payload_start + 3], "little") * 2
    frame_y = int.from_bytes(data[payload_start + 3:payload_start + 6], "little") * 2
    frame_width = 1 + int.from_bytes(data[payload_start + 6:payload_start + 9], "little")
    frame_height = 1 + int.from_bytes(data[payload_start + 9:payload_start + 12], "little")
    flags = data[payload_start + 15]
    if flags & 0xFC:
        raise RasterHeaderError("invalid WebP animation frame reserved bits")
    if frame_x + frame_width > canvas_width or frame_y + frame_height > canvas_height:
        raise RasterHeaderError("WebP animation frame exceeds canvas bounds")
    if max_dimension is not None and (frame_width > max_dimension or frame_height > max_dimension):
        raise RasterLimitError("WebP frame dimension limit exceeded")
    frame_pixels = frame_width * frame_height
    if max_pixels is not None and frame_pixels > max_pixels:
        raise RasterLimitError("WebP frame pixel limit exceeded")

    position = payload_start + 16
    found_alpha = False
    found_bitstream = False
    while position < payload_end:
        if position + 8 > payload_end:
            raise RasterHeaderError("truncated WebP animation frame subchunk")
        chunk_type = data[position:position + 4]
        chunk_size = struct.unpack_from("<I", data, position + 4)[0]
        subchunk_start = position + 8
        subchunk_end = subchunk_start + chunk_size
        subchunk_next = subchunk_end + (chunk_size & 1)
        if subchunk_end > payload_end or subchunk_next > payload_end:
            raise RasterHeaderError("WebP animation frame subchunk exceeds frame bounds")
        if chunk_size & 1 and data[subchunk_end] != 0:
            raise RasterHeaderError("invalid WebP animation frame subchunk padding")
        if chunk_type == b"ALPH":
            if found_alpha or found_bitstream or chunk_size < 1:
                raise RasterHeaderError("invalid WebP animation alpha subchunk")
            found_alpha = True
        elif chunk_type in (b"VP8 ", b"VP8L"):
            if found_bitstream:
                raise RasterHeaderError("duplicate WebP animation bitstream")
            if found_alpha and chunk_type == b"VP8L":
                raise RasterHeaderError("WebP alpha subchunk cannot precede VP8L")
            if _parse_webp_bitstream_dimensions(chunk_type, data, subchunk_start, subchunk_end) != (frame_width, frame_height):
                raise RasterHeaderError("WebP animation frame dimensions disagree with bitstream")
            found_bitstream = True
        elif found_bitstream:
            # Unknown subchunks may follow the bitstream.
            pass
        else:
            raise RasterHeaderError("unsupported WebP animation frame subchunk order")
        position = subchunk_next
    if not found_bitstream:
        raise RasterHeaderError("WebP animation frame bitstream is missing")
    return frame_pixels


def parse_webp_raster(data, max_dimension=None, max_pixels=None, max_total_pixels=None):
    """Read dimensions and bounded canvas-plus-frame pixel cost from WebP headers."""
    if len(data) < 20 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise RasterHeaderError("invalid WebP RIFF signature")
    riff_end = 8 + struct.unpack_from("<I", data, 4)[0]
    if riff_end < 12 or riff_end > len(data):
        raise RasterHeaderError("invalid or truncated WebP RIFF size")

    position = 12
    canvas = None
    animation = False
    animation_control_seen = False
    frame_count = 0
    image_bitstream_seen = False
    simple_dimensions = None
    work_pixels = 0
    while position + 8 <= riff_end:
        if canvas is None and simple_dimensions is not None:
            raise RasterHeaderError("unexpected chunk after simple WebP image bitstream")
        chunk_type = data[position:position + 4]
        chunk_size = struct.unpack_from("<I", data, position + 4)[0]
        payload_start = position + 8
        payload_end = payload_start + chunk_size
        chunk_end = payload_end + (chunk_size & 1)
        if payload_end > riff_end or chunk_end > riff_end:
            raise RasterHeaderError("WebP chunk exceeds RIFF bounds")
        if chunk_size & 1 and data[payload_end] != 0:
            raise RasterHeaderError("invalid WebP RIFF chunk padding")
        if chunk_type == b"VP8X":
            if canvas is not None or position != 12:
                raise RasterHeaderError("invalid WebP VP8X chunk position")
            if chunk_size < 10:
                raise RasterHeaderError("truncated WebP VP8X header")
            # The current dimension fields occupy the first 10 bytes; later
            # specification revisions may extend this header.
            if data[payload_start] & 0xC1 or any(data[payload_start + 1:payload_start + 4]):
                raise RasterHeaderError("invalid WebP VP8X reserved bits")
            width = 1 + int.from_bytes(data[payload_start + 4:payload_start + 7], "little")
            height = 1 + int.from_bytes(data[payload_start + 7:payload_start + 10], "little")
            if width * height > 0xFFFFFFFF:
                raise RasterHeaderError("WebP canvas dimensions exceed format maximum")
            if max_dimension is not None and (width > max_dimension or height > max_dimension):
                raise RasterLimitError("WebP dimension limit exceeded")
            if max_pixels is not None and width * height > max_pixels:
                raise RasterLimitError("WebP pixel limit exceeded")
            canvas = (width, height)
            animation = bool(data[payload_start] & 0x02)
            work_pixels = width * height
            if max_total_pixels is not None and work_pixels > max_total_pixels:
                raise RasterLimitError("total raster pixel budget exceeded")
        elif chunk_type == b"ANIM":
            if canvas is None or not animation or animation_control_seen or chunk_size != 6:
                raise RasterHeaderError("invalid WebP animation control chunk")
            animation_control_seen = True
        elif chunk_type == b"ANMF":
            if canvas is None or not animation or not animation_control_seen:
                raise RasterHeaderError("WebP animation frame appears before animation control")
            frame_pixels = _parse_webp_frame(
                data, payload_start, payload_end, canvas[0], canvas[1], max_dimension, max_pixels
            )
            frame_count += 1
            work_pixels += frame_pixels
            if max_total_pixels is not None and work_pixels > max_total_pixels:
                raise RasterLimitError("total raster pixel budget exceeded")
            position = chunk_end
            continue
        if chunk_type == b"VP8 ":
            if canvas is not None:
                if animation or image_bitstream_seen:
                    raise RasterHeaderError("unexpected WebP image chunk after VP8X")
                image_width, image_height = _parse_webp_bitstream_dimensions(chunk_type, data, payload_start, payload_end)
                if (image_width, image_height) != canvas:
                    raise RasterHeaderError("WebP image dimensions disagree with VP8X canvas")
                image_bitstream_seen = True
            else:
                if position != 12:
                    raise RasterHeaderError("simple WebP image bitstream is not the first chunk")
                simple_dimensions = _parse_webp_bitstream_dimensions(chunk_type, data, payload_start, payload_end)
        elif chunk_type == b"VP8L":
            if canvas is not None:
                if animation or image_bitstream_seen:
                    raise RasterHeaderError("unexpected WebP image chunk after VP8X")
                image_width, image_height = _parse_webp_bitstream_dimensions(chunk_type, data, payload_start, payload_end)
                if (image_width, image_height) != canvas:
                    raise RasterHeaderError("WebP image dimensions disagree with VP8X canvas")
                image_bitstream_seen = True
            else:
                if position != 12:
                    raise RasterHeaderError("simple WebP image bitstream is not the first chunk")
                simple_dimensions = _parse_webp_bitstream_dimensions(chunk_type, data, payload_start, payload_end)
        position = chunk_end
    if position != riff_end:
        raise RasterHeaderError("truncated WebP chunk header")
    if canvas is not None and animation:
        if not animation_control_seen or not frame_count:
            raise RasterHeaderError("WebP animation is missing control or frame chunks")
        return canvas[0], canvas[1], work_pixels
    if canvas is not None and not animation and image_bitstream_seen:
        return canvas[0], canvas[1], work_pixels
    if simple_dimensions is not None:
        width, height = simple_dimensions
        if max_dimension is not None and (width > max_dimension or height > max_dimension):
            raise RasterLimitError("WebP dimension limit exceeded")
        pixels = width * height
        if max_pixels is not None and pixels > max_pixels:
            raise RasterLimitError("WebP pixel limit exceeded")
        if max_total_pixels is not None and pixels > max_total_pixels:
            raise RasterLimitError("total raster pixel budget exceeded")
        return width, height, pixels
    raise RasterHeaderError("WebP image dimensions are missing")


def parse_webp_dimensions(data):
    """Compatibility helper returning only the declared WebP canvas dimensions."""
    width, height, _pixel_cost = parse_webp_raster(data)
    return width, height


def parse_raster_dimensions(data, suffix):
    """Dispatch dimension inspection by the already-classified filename suffix."""
    extension = suffix.lower()
    if extension == ".png":
        return parse_png_dimensions(data)
    if extension in (".jpg", ".jpeg"):
        return parse_jpeg_dimensions(data)
    if extension == ".webp":
        return parse_webp_dimensions(data)
    raise RasterHeaderError("unsupported raster extension")

def file_identity(info):
    identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    # Windows reports creation time as st_ctime_ns, and stat()/fstat() can
    # disagree for the same open file. Keep the stable file ID, size and
    # modification-time checks there; ctime remains useful on POSIX.
    if os.name != "nt":
        identity += (info.st_ctime_ns,)
    return identity

def _has_symlink_component(root, path):
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            return True
    return False

def _open_asset_beneath(root, path):
    """Open a file beneath a pinned directory, refusing symlinks where supported."""
    parts = path.relative_to(root).parts
    if not parts:
        raise ValueError("asset path must name a file")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if nofollow and directory and SUPPORTS_DIR_FD_OPEN:
        dir_fd = os.open(root, os.O_RDONLY | directory | nofollow)
        try:
            for part in parts[:-1]:
                next_fd = os.open(part, os.O_RDONLY | directory | nofollow, dir_fd=dir_fd)
                os.close(dir_fd)
                dir_fd = next_fd
            return os.open(parts[-1], os.O_RDONLY | nofollow | nonblock, dir_fd=dir_fd)
        finally:
            os.close(dir_fd)
    return os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | nofollow | nonblock)

def read_stable_asset(root, path, limit, expected_identity):
    """Read a bounded regular asset and reject a file changed since stat."""
    if _has_symlink_component(root, path):
        raise ValueError("symlink in asset path")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or file_identity(before) != expected_identity:
        raise ValueError("asset changed since initial stat")
    if _has_symlink_component(root, path):
        raise ValueError("symlink in asset path")
    if before.st_size > limit:
        raise ValueError("asset exceeds snapshot size limit")

    descriptor = _open_asset_beneath(root, path)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or file_identity(opened) != file_identity(before):
            raise ValueError("asset changed between stat and open")
        chunks = []
        total = 0
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            while True:
                chunk = stream.read(min(64 * 1024, limit + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise ValueError("asset exceeds snapshot size limit")
                chunks.append(chunk)
            after = os.fstat(stream.fileno())
            if file_identity(after) != file_identity(opened):
                raise ValueError("asset changed while reading")
        return b"".join(chunks)
    finally:
        if descriptor is not None:
            os.close(descriptor)

def parse_svg(data):
    """Parse the supported static SVG subset with explicit XML resource limits."""
    builder = ET.TreeBuilder()
    parser = expat.ParserCreate(namespace_separator="|")
    parser.buffer_text = True
    depth = 0
    elements = 0

    def tree_name(name):
        if "|" not in name:
            return name
        namespace, local = name.split("|", 1)
        return "{" + namespace + "}" + local

    def reject_doctype(*_args):
        raise ValueError("DOCTYPE is forbidden")

    def reject_entity(*_args):
        raise ValueError("entity declarations are forbidden")

    def reject_processing_instruction(*_args):
        raise ValueError("processing instructions are forbidden")

    def start(name, attrs):
        nonlocal depth, elements
        depth += 1
        elements += 1
        if depth > MAX_SVG_DEPTH:
            raise ValueError("nesting exceeds maximum depth")
        if elements > MAX_SVG_ELEMENTS:
            raise ValueError("element count exceeds maximum")
        if len(attrs) > MAX_SVG_ATTRIBUTES_PER_ELEMENT:
            raise ValueError("attribute count exceeds maximum")
        if any(len(value) > MAX_SVG_ATTRIBUTE for value in attrs.values()):
            raise ValueError("attribute value exceeds maximum size")
        builder.start(tree_name(name), {tree_name(k): v for k, v in attrs.items()})

    def end(name):
        nonlocal depth
        builder.end(tree_name(name))
        depth -= 1

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = builder.data
    parser.StartDoctypeDeclHandler = reject_doctype
    parser.EntityDeclHandler = reject_entity
    parser.UnparsedEntityDeclHandler = reject_entity
    parser.ExternalEntityRefHandler = lambda *_args: 0
    parser.ProcessingInstructionHandler = reject_processing_instruction
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.Parse(data, True)
    root = builder.close()
    if root is None:
        raise ValueError("SVG document is empty")
    return root

def validate_svg(data, *, require_dimensions=False, max_dimension=MAX_SVG_DIMENSION,
                 max_pixels=MAX_SVG_PIXELS):
    """Return SVG subset errors; this is validation, not a sanitizer."""
    if (type(max_dimension) is not int or type(max_pixels) is not int or
            max_dimension <= 0 or max_pixels <= 0 or
            max_dimension > MAX_SVG_DIMENSION or max_pixels > MAX_SVG_PIXELS):
        raise ValueError("SVG validation limits must be positive and cannot exceed v0.3 maxima")
    svg = parse_svg(data)
    errors = []
    def check(ok, message):
        if not ok:
            errors.append(message)

    def split_name(name):
        if name.startswith("{") and "}" in name:
            namespace, local = name[1:].split("}", 1)
            return namespace, local
        return "", name

    root_namespace, root_name = split_name(svg.tag)
    check(root_name == "svg", "root element must be svg")
    check(root_namespace in ("", SVG_NAMESPACE), "unsupported SVG namespace")
    if require_dimensions:
        dimensions = []
        for axis in ("width", "height"):
            value = svg.attrib.get(axis)
            if value is None:
                check(False, "SVG " + axis + " is required")
                dimensions.append(None)
                continue
            if len(value) > 64 or re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?:px)?", value) is None:
                check(False, "SVG " + axis + " must be a positive numeric px value")
                dimensions.append(None)
                continue
            try:
                number = Decimal(value[:-2] if value.endswith("px") else value)
            except InvalidOperation:
                number = Decimal(0)
            if number <= 0:
                check(False, "SVG " + axis + " must be a positive numeric px value")
                dimensions.append(None)
                continue
            if number > max_dimension:
                check(False, "SVG dimension limit exceeded for " + axis)
            dimensions.append(number)
        if all(number is not None for number in dimensions):
            with localcontext() as context:
                context.prec = 128
                if dimensions[0] * dimensions[1] > max_pixels:
                    check(False, "SVG pixel limit exceeded")
    ids = {}
    references = []
    for element in svg.iter():
        namespace, tag = split_name(element.tag)
        tag_key = tag.lower()
        check(namespace == root_namespace, "mixed SVG element namespaces are forbidden")
        check(tag in SVG_CANONICAL_TAGS, "forbidden SVG element " + tag)
        check(not (element.text and element.text.strip()), "SVG text content is forbidden")
        check(not (element.tail and element.tail.strip()), "SVG text content is forbidden")
        for raw_attr, value in element.attrib.items():
            attr_namespace, attr = split_name(raw_attr)
            normalized_attr = attr.lower()
            check(attr_namespace == "", "namespaced SVG attributes are forbidden")
            check(attr in SVG_ATTRIBUTES.get(tag_key, set()), "unsupported SVG attribute " + attr)
            check(not normalized_attr.startswith("on") and normalized_attr not in ("href", "src", "style", "base"),
                  "unsafe SVG attribute " + attr)
            check("@import" not in value.lower(), "SVG import forbidden")
            check("\\" not in value and "/*" not in value and "*/" not in value,
                  "SVG CSS escapes and comments are forbidden")
            if normalized_attr == "id":
                check(value not in ids, "duplicate SVG id " + value)
                ids[value] = tag_key
            if SVG_URL.search(value):
                match = SVG_LOCAL_URL.fullmatch(value.strip())
                check(match is not None and normalized_attr in ("fill", "stroke"),
                      "unsafe SVG URL reference")
                if match is not None and normalized_attr in ("fill", "stroke"):
                    references.append((match.group(1) or match.group(3), normalized_attr))
    for target, _attribute in references:
        check(ids.get(target) in ("lineargradient", "radialgradient"),
              "SVG URL reference must target a local gradient id")
    return errors

def num(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False

def check_json_nesting(text):
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError("manifest nesting exceeds maximum depth")
        elif char in "]}" and depth:
            depth -= 1

def validate(folder, *, asset_data_sink=None, max_png_dimension=MAX_PNG_DIMENSION,
             max_png_pixels=MAX_PNG_PIXELS, max_total_png_pixels=MAX_TOTAL_PNG_PIXELS,
             max_raster_dimension=None, max_raster_pixels=None, max_total_raster_pixels=None,
             max_svg_dimension=MAX_SVG_DIMENSION, max_svg_pixels=MAX_SVG_PIXELS):
    # The max_png_* names remain as compatibility aliases for existing callers.
    max_raster_dimension = max_png_dimension if max_raster_dimension is None else max_raster_dimension
    max_raster_pixels = max_png_pixels if max_raster_pixels is None else max_raster_pixels
    max_total_raster_pixels = max_total_png_pixels if max_total_raster_pixels is None else max_total_raster_pixels
    raster_limits = (max_raster_dimension, max_raster_pixels, max_total_raster_pixels)
    if any(type(value) is not int or value <= 0 for value in raster_limits):
        raise ValueError("raster integer limits must be positive")
    if any(type(value) is not int or value <= 0 or value > maximum
           for value, maximum in ((max_svg_dimension, MAX_SVG_DIMENSION),
                                  (max_svg_pixels, MAX_SVG_PIXELS))):
        raise ValueError("SVG limits must be positive and cannot exceed v0.3 maxima")
    try:
        root = pathlib.Path(folder).resolve(strict=True)
    except (RuntimeError, OSError) as exc:
        raise ValueError("unable to resolve project root") from exc
    errors = []
    def check(ok, message):
        if not ok:
            errors.append(message)
        return ok
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file() or manifest_path.stat().st_size > MAX_MANIFEST:
        raise ValueError("missing or oversized manifest")
    manifest_text = manifest_path.read_text(encoding="utf-8")
    check_json_nesting(manifest_text)
    try:
        m = json.loads(manifest_text, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("non-finite constant")))
    except RecursionError as exc:
        raise ValueError("manifest nesting exceeds parser limit") from exc
    if not isinstance(m, dict):
        raise ValueError("manifest must be an object")
    check(m.get("format") == "motionpack", "format must be motionpack")
    version = m.get("version")
    check(version in ("0.1", "0.2", "0.3", "0.4"), "unsupported format version")
    canvas = m.get("canvas", {})
    if not isinstance(canvas, dict):
        canvas = {}
    for axis in ("width", "height"):
        v = canvas.get(axis)
        check(type(v) is int and 0 < v <= 8192, "invalid canvas " + axis)
    assets = m.get("assets", {})
    nodes = m.get("nodes", [])
    clips = m.get("clips", {})
    variants = m.get("variants", {})
    iks = m.get("iks", [])
    if not all([isinstance(assets, dict), isinstance(nodes, list), isinstance(clips, dict), isinstance(variants, dict), isinstance(iks, list)]):
        raise ValueError("invalid manifest collection types")
    check(len(assets) <= MAX_ASSETS, "too many assets")
    check(len(nodes) <= MAX_NODES, "too many nodes")
    check(len(iks) <= MAX_NODES, "too many inverse-kinematics chains")
    total_size = 0
    checked_svgs = set()
    checked_rasters = set()
    total_raster_pixels = 0
    captured_assets = {}
    for aid, raw_path in assets.items():
        if not isinstance(aid, str) or not isinstance(raw_path, str):
            check(False, "invalid asset key or path")
            continue
        p = pathlib.PurePosixPath(raw_path)
        if not check(raw_path and "\\" not in raw_path and not p.is_absolute()
                     and not re.match(r"^[A-Za-z]:", raw_path) and ".." not in p.parts and len(raw_path) <= 256,
                     "unsafe path for " + str(aid)):
            continue
        if p.parts and p.parts[0].casefold() == "source":
            check(False, "source directory cannot be a runtime asset: " + raw_path)
            continue
        dest = root.joinpath(*p.parts)
        try:
            real = dest.resolve()
        except RuntimeError:
            check(False, "unable to resolve asset " + raw_path)
            continue
        current = root
        symlink_in_path = False
        for part in p.parts:
            current = current / part
            if current.is_symlink():
                symlink_in_path = True
                break
        if symlink_in_path:
            check(False, "symlink in asset path " + raw_path)
            continue
        if not check(real.is_relative_to(root) and real.is_file(), "missing/escaping asset " + raw_path):
            continue
        if not check(real.suffix.lower() in (".svg", ".png", ".webp", ".jpg", ".jpeg"), "unsupported asset " + raw_path):
            continue
        try:
            asset_info = real.stat()
        except OSError:
            check(False, "unable to stat asset " + raw_path)
            continue
        size = asset_info.st_size
        total_size += size
        check(size <= MAX_ASSET, "oversized asset " + raw_path)
        if total_size > MAX_TOTAL_ASSETS:
            continue
        asset_bytes = None
        if asset_data_sink is not None:
            if real not in captured_assets:
                try:
                    captured_assets[real] = read_stable_asset(
                        root, real, MAX_ASSET, file_identity(asset_info)
                    )
                except (OSError, ValueError) as exc:
                    check(False, "unable to snapshot asset " + raw_path + ": " + str(exc))
                    continue
            asset_bytes = captured_assets[real]
            asset_data_sink[raw_path] = asset_bytes
        if real.suffix.lower() == ".svg" and size <= MAX_ASSET and real not in checked_svgs:
            checked_svgs.add(real)
            svg_bytes = asset_bytes
            if svg_bytes is None:
                try:
                    svg_bytes = read_stable_asset(root, real, MAX_ASSET, file_identity(asset_info))
                except (OSError, ValueError) as exc:
                    check(False, "unable to read SVG " + raw_path + ": " + str(exc))
                    continue
            try:
                for svg_error in validate_svg(
                    svg_bytes, require_dimensions=version in ("0.3", "0.4"),
                    max_dimension=max_svg_dimension, max_pixels=max_svg_pixels,
                ):
                    check(False, "SVG " + raw_path + ": " + svg_error)
            except (ET.ParseError, expat.ExpatError, ValueError) as exc:
                check(False, "invalid SVG " + raw_path + ": " + str(exc))
        elif real.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") and size <= MAX_ASSET and real not in checked_rasters:
            checked_rasters.add(real)
            raster_bytes = asset_bytes
            if raster_bytes is None:
                try:
                    raster_bytes = read_stable_asset(root, real, MAX_ASSET, file_identity(asset_info))
                except (OSError, ValueError) as exc:
                    check(False, "unable to read raster header " + raw_path + ": " + str(exc))
                    continue
            extension = real.suffix.lower()
            image_format = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WebP"}[extension]
            raster_cost = None
            try:
                if extension == ".webp":
                    width, height, raster_cost = parse_webp_raster(
                        raster_bytes, max_raster_dimension, max_raster_pixels,
                        max_total_raster_pixels - total_raster_pixels,
                    )
                else:
                    width, height = parse_raster_dimensions(raster_bytes, extension)
            except (ValueError, struct.error) as exc:
                if isinstance(exc, RasterLimitError):
                    check(False, str(exc) + " for " + raw_path)
                    continue
                check(False, "invalid " + image_format + " header " + raw_path + ": " + str(exc))
                continue
            if not check(width <= max_raster_dimension and height <= max_raster_dimension,
                         image_format + " dimension limit exceeded for " + raw_path):
                continue
            pixels = width * height
            if not check(pixels <= max_raster_pixels, image_format + " pixel limit exceeded for " + raw_path):
                continue
            total_raster_pixels += pixels if raster_cost is None else raster_cost
            check(total_raster_pixels <= max_total_raster_pixels, "total raster pixel budget exceeded")
    check(total_size <= MAX_TOTAL_ASSETS, "total asset budget exceeded")
    ids = [n.get("id") for n in nodes if isinstance(n, dict)]
    check(len(ids) == len(nodes) and all(isinstance(x, str) and x for x in ids) and len(set(ids)) == len(ids),
          "invalid or duplicate node IDs")
    lookup = {n["id"]: n for n in nodes if isinstance(n, dict) and isinstance(n.get("id"), str)}
    for nid, n in lookup.items():
        if "interaction" in n:
            interaction = n["interaction"]
            if version != "0.4":
                check(False, "interaction requires format version 0.4 for " + nid)
            if not isinstance(interaction, dict):
                check(False, "invalid interaction for " + nid)
            else:
                for flag, enabled in interaction.items():
                    if flag not in ("hover", "tap", "click"):
                        check(False, "unknown interaction flag " + str(flag) + " for " + nid)
                    elif type(enabled) is not bool:
                        check(False, "invalid interaction " + flag + " for " + nid)
        parent = n.get("parent")
        check(parent is None or parent in lookup, "missing parent " + nid)
        check(n.get("asset") is None or n["asset"] in assets, "missing asset for " + nid)
        for field in ("x", "y", "rotation", "opacity", "scale", "width", "height"):
            if field in n:
                valid = num(n[field])
                if field in ("width", "height"):
                    valid = valid and n[field] > 0
                check(valid, "invalid " + field + " for " + nid)
        visited = set()
        cur = nid
        while cur in lookup and lookup[cur].get("parent"):
            if cur in visited:
                check(False, "parent cycle at " + nid)
                break
            visited.add(cur)
            cur = lookup[cur]["parent"]
    ikids = []
    for ik in iks:
        if not isinstance(ik, dict):
            check(False, "malformed IK")
            continue
        ikids.append(ik.get("id"))
        upper = lookup.get(ik.get("upper"))
        lower = lookup.get(ik.get("lower"))
        check(upper is not None and lower is not None and lower.get("parent") == ik.get("upper"), "invalid IK chain")
        lengths = ik.get("lengths")
        target = ik.get("target")
        check(isinstance(lengths, list) and len(lengths) == 2 and all(num(v) and v > 0 for v in lengths), "invalid IK lengths")
        check(isinstance(target, list) and len(target) == 2 and all(num(v) for v in target), "invalid IK target")
        check(ik.get("bend", 1) in (-1, 1), "invalid IK bend")
        check(num(ik.get("weight", 1)), "invalid IK weight")
    check(len(ikids) == len(set(map(str, ikids))), "duplicate IK ID")
    tracks_total, effects_total = 0, 0
    for name, clip in clips.items():
        if not isinstance(clip, dict):
            check(False, "invalid clip " + str(name))
            continue
        duration = clip.get("duration_ms")
        if not check(type(duration) is int and 0 < duration <= 3600000, "invalid clip duration " + str(name)):
            continue
        if "loop" in clip:
            check(type(clip["loop"]) is bool, "invalid loop flag in " + str(name))
        for track in clip.get("tracks", []) + clip.get("ik_tracks", []):
            tracks_total += 1
            if "node" in track:
                check(track["node"] in lookup and track.get("property") in ALLOWED_PROPERTIES, "invalid track in " + name)
            else:
                check(track.get("ik") in ikids and track.get("axis") in ("x", "y"), "invalid IK track in " + name)
            keys = track.get("keys", [])
            times = [k.get("time_ms") for k in keys]
            check(bool(keys) and all(num(t) and 0 <= t <= duration for t in times)
                  and times == sorted(set(times)) and all(num(k.get("value")) for k in keys),
                  "invalid timeline in " + name)
        for fx in clip.get("effects", []):
            effects_total += 1
            check(fx.get("kind") in ALLOWED_EFFECTS and fx.get("node") in lookup, "invalid effect in " + name)
            start, length = fx.get("start_ms"), fx.get("duration_ms")
            check(type(start) is int and type(length) is int and 0 <= start and 0 < length and start + length <= duration, "invalid effect time")
            if fx.get("kind") == "burst":
                check(type(fx.get("count", 28)) is int and 0 <= fx.get("count", 28) <= 200, "invalid particle count")
    check(tracks_total <= MAX_TRACKS and effects_total <= MAX_EFFECTS, "timeline complexity exceeded")
    for vn, var in variants.items():
        for nid, overlay in var.get("nodes", {}).items():
            check(nid in lookup and isinstance(overlay, dict), "bad variant override")
            if isinstance(overlay, dict):
                check(overlay.get("asset") is None or overlay["asset"] in assets, "missing variant asset")
                for field in ("width", "height"):
                    if field in overlay:
                        check(num(overlay[field]) and overlay[field] > 0,
                              "invalid " + field + " for variant " + str(vn) + " node " + str(nid))
    check(m.get("defaults", {}).get("clip") in clips, "invalid default clip")
    check(m.get("defaults", {}).get("variant") in variants, "invalid default variant")
    return errors, m

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python tools/validate.py PROJECT")
    try:
        errors, manifest = validate(sys.argv[1])
        if errors:
            sys.exit("INVALID\n" + "\n".join("- " + e for e in errors))
        print("VALID:", len(manifest["nodes"]), "nodes,", len(manifest["clips"]), "clips")
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as e:
        sys.exit("INVALID: " + str(e))
