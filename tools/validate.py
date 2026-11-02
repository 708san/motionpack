#!/usr/bin/env python3
"""Validate experimental MotionPack v0.1/v0.2 projects, including untrusted inputs.

Validation is intentionally conservative; a passing result is NOT a security certificate.
"""
import json
import math
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

ALLOWED_PROPERTIES = {"x", "y", "rotation", "opacity", "scale"}
ALLOWED_EFFECTS = {"beam", "ring", "burst"}
SVG_TAGS = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "defs", "lineargradient", "radialgradient", "stop"}
MAX_MANIFEST = 1024 * 1024
MAX_ASSET = 12 * 1024 * 1024
MAX_TOTAL_ASSETS = 32 * 1024 * 1024
MAX_NODES = 1000
MAX_ASSETS = 512
MAX_TRACKS = 2000
MAX_EFFECTS = 1000

def num(value):
    return type(value) in (int, float) and math.isfinite(value)

def validate(folder):
    root = pathlib.Path(folder).resolve()
    errors = []
    def check(ok, message):
        if not ok:
            errors.append(message)
        return ok
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file() or manifest_path.stat().st_size > MAX_MANIFEST:
        raise ValueError("missing or oversized manifest")
    m = json.loads(manifest_path.read_text(encoding="utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError("non-finite constant")))
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
    for aid, raw_path in assets.items():
        if not isinstance(aid, str) or not isinstance(raw_path, str):
            check(False, "invalid asset key or path")
            continue
        p = pathlib.PurePosixPath(raw_path)
        if not check(raw_path and "\\" not in raw_path and not p.is_absolute() and ".." not in p.parts and len(raw_path) <= 256,
                     "unsafe path for " + str(aid)):
            continue
        dest = root.joinpath(*p.parts)
        real = dest.resolve()
        if not check(real.is_relative_to(root) and real.is_file() and not dest.is_symlink(), "missing/escaping asset " + raw_path):
            continue
        if not check(real.suffix.lower() in (".svg", ".png", ".webp", ".jpg", ".jpeg"), "unsupported asset " + raw_path):
            continue
        size = real.stat().st_size
        total_size += size
        check(size <= MAX_ASSET, "oversized asset " + raw_path)
        if real.suffix.lower() == ".svg" and size <= MAX_ASSET:
            try:
                svg = ET.fromstring(real.read_bytes())
                for el in svg.iter():
                    tag = el.tag.rsplit("}", 1)[-1].lower()
                    check(tag in SVG_TAGS, "forbidden SVG element " + tag)
                    if el.text:
                        check("@import" not in el.text.lower(), "SVG embedded import forbidden")
                    for k, v in el.attrib.items():
                        attr = k.rsplit("}", 1)[-1].lower()
                        check(not attr.startswith("on") and attr not in ("href", "src", "style"),
                              "unsafe SVG attribute " + attr)
                        if isinstance(v, str):
                            check("@import" not in v.lower(), "SVG import forbidden")
                            for hit in re.findall(r"url\((.*?)\)", v, flags=re.I):
                                check(hit.strip().strip("\"'").startswith("#"), "SVG external resource forbidden")
            except ET.ParseError:
                check(False, "invalid SVG " + raw_path)
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
                check(num(n[field]), "invalid " + field + " for " + nid)
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
