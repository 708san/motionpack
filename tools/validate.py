#!/usr/bin/env python3
"""Validate experimental MotionPack v0.1/v0.2 projects, including untrusted inputs.

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
import xml.etree.ElementTree as ET
from xml.parsers import expat

ALLOWED_PROPERTIES = {"x", "y", "rotation", "opacity", "scale"}
ALLOWED_EFFECTS = {"beam", "ring", "burst"}
SVG_TAGS = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "defs", "lineargradient", "radialgradient", "stop"}
MAX_MANIFEST = 1024 * 1024
MAX_ASSET = 12 * 1024 * 1024
MAX_TOTAL_ASSETS = 32 * 1024 * 1024
MAX_PNG_DIMENSION = 8192
MAX_PNG_PIXELS = 16_000_000
MAX_TOTAL_PNG_PIXELS = 64_000_000
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

def parse_png_dimensions(data):
    """Read and validate only the PNG signature and first IHDR chunk."""
    if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("invalid PNG signature or truncated IHDR")
    if struct.unpack_from(">I", data, 8)[0] != 13 or data[12:16] != b"IHDR":
        raise ValueError("invalid PNG IHDR framing")
    ihdr = data[16:29]
    expected_crc = struct.unpack_from(">I", data, 29)[0]
    if zlib.crc32(data[12:29]) & 0xFFFFFFFF != expected_crc:
        raise ValueError("invalid PNG IHDR CRC")

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
        raise ValueError("invalid PNG IHDR values")
    return width, height

def file_identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

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
        raise ValueError("asset changed during validation")
    if _has_symlink_component(root, path):
        raise ValueError("symlink in asset path")
    if before.st_size > limit:
        raise ValueError("asset exceeds snapshot size limit")

    descriptor = _open_asset_beneath(root, path)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or file_identity(opened) != file_identity(before):
            raise ValueError("asset changed during validation")
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
                raise ValueError("asset changed during validation")
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

def validate_svg(data):
    """Return SVG subset errors; this is validation, not a sanitizer."""
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
    check(root_name.lower() == "svg", "root element must be svg")
    check(root_namespace in ("", SVG_NAMESPACE), "unsupported SVG namespace")
    ids = {}
    references = []
    for element in svg.iter():
        namespace, tag = split_name(element.tag)
        tag = tag.lower()
        check(namespace == root_namespace, "mixed SVG element namespaces are forbidden")
        check(tag in SVG_TAGS, "forbidden SVG element " + tag)
        check(not (element.text and element.text.strip()), "SVG text content is forbidden")
        for raw_attr, value in element.attrib.items():
            attr_namespace, attr = split_name(raw_attr)
            attr = attr.lower()
            check(attr_namespace == "", "namespaced SVG attributes are forbidden")
            check(not attr.startswith("on") and attr not in ("href", "src", "style", "base"),
                  "unsafe SVG attribute " + attr)
            check("@import" not in value.lower(), "SVG import forbidden")
            check("\\" not in value and "/*" not in value and "*/" not in value,
                  "SVG CSS escapes and comments are forbidden")
            if attr == "id":
                check(value not in ids, "duplicate SVG id " + value)
                ids[value] = tag
            if SVG_URL.search(value):
                match = SVG_LOCAL_URL.fullmatch(value.strip())
                check(match is not None and attr in ("fill", "stroke"),
                      "unsafe SVG URL reference")
                if match is not None and attr in ("fill", "stroke"):
                    references.append((match.group(1) or match.group(3), attr))
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
             max_png_pixels=MAX_PNG_PIXELS, max_total_png_pixels=MAX_TOTAL_PNG_PIXELS):
    png_limits = (max_png_dimension, max_png_pixels, max_total_png_pixels)
    if any(type(value) is not int or value <= 0 for value in png_limits):
        raise ValueError("PNG integer limits must be positive")
    try:
        root = pathlib.Path(folder).resolve()
    except RuntimeError as exc:
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
    check(m.get("version") in ("0.1", "0.2"), "unsupported format version")
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
    checked_pngs = set()
    total_png_pixels = 0
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
                for svg_error in validate_svg(svg_bytes):
                    check(False, "SVG " + raw_path + ": " + svg_error)
            except (ET.ParseError, expat.ExpatError, ValueError) as exc:
                check(False, "invalid SVG " + raw_path + ": " + str(exc))
        elif real.suffix.lower() == ".png" and size <= MAX_ASSET and real not in checked_pngs:
            checked_pngs.add(real)
            png_bytes = asset_bytes
            if png_bytes is None:
                try:
                    png_bytes = read_stable_asset(root, real, MAX_ASSET, file_identity(asset_info))
                except (OSError, ValueError) as exc:
                    check(False, "unable to read PNG header " + raw_path + ": " + str(exc))
                    continue
            try:
                width, height = parse_png_dimensions(png_bytes)
            except (ValueError, struct.error) as exc:
                check(False, "invalid PNG header " + raw_path + ": " + str(exc))
                continue
            if not check(width <= max_png_dimension and height <= max_png_dimension,
                         "PNG dimension limit exceeded for " + raw_path):
                continue
            pixels = width * height
            if not check(pixels <= max_png_pixels, "PNG pixel limit exceeded for " + raw_path):
                continue
            total_png_pixels += pixels
            check(total_png_pixels <= max_total_png_pixels, "total PNG pixel budget exceeded")
    check(total_size <= MAX_TOTAL_ASSETS, "total asset budget exceeded")
    ids = [n.get("id") for n in nodes if isinstance(n, dict)]
    check(len(ids) == len(nodes) and all(isinstance(x, str) and x for x in ids) and len(set(ids)) == len(ids),
          "invalid or duplicate node IDs")
    lookup = {n["id"]: n for n in nodes if isinstance(n, dict) and isinstance(n.get("id"), str)}
    for nid, n in lookup.items():
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
    check(len(ikids) == len(set(map(str, ikids))), "duplicate IK ID")
    tracks_total, effects_total = 0, 0
    for name, clip in clips.items():
        if not isinstance(clip, dict):
            check(False, "invalid clip " + str(name))
            continue
        duration = clip.get("duration_ms")
        if not check(type(duration) is int and 0 < duration <= 3600000, "invalid clip duration " + str(name)):
            continue
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
