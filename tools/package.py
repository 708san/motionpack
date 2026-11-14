#!/usr/bin/env python3
"""Package editable .motionpack ZIP and offline browser preview. No runtime network required."""
from pathlib import Path, PurePosixPath
import argparse
import base64
import json
import mimetypes
import re
import sys
import struct
import zlib
import tempfile
import time
import unicodedata
import zipfile
try:
    from .isolated_raster_decoder import (
        RasterDecodeError, RasterDecodeLimits, decode_raster_assets_isolated,
    )
    from .validate import validate
except ImportError:  # Support direct execution from the tools directory.
    from isolated_raster_decoder import (
        RasterDecodeError, RasterDecodeLimits, decode_raster_assets_isolated,
    )
    from validate import validate

RASTER_PREVIEW_TOTAL_TIMEOUT_SECONDS = 300.0
RASTER_PREVIEW_PER_ASSET_TIMEOUT_SECONDS = 30.0

_SECRET_MARKERS = (
    ("private-key header", re.compile(rb"-----BEGIN (?:(?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY|ENCRYPTED PRIVATE KEY|PGP PRIVATE KEY BLOCK)-----")),
    ("GitHub token-like value", re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("OpenAI key-like value", re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("Slack token-like value", re.compile(rb"(?:xox[a-z]|xapp|xwfp)-[A-Za-z0-9-]{20,}")),
    ("AWS access-key ID-like value", re.compile(rb"(?:AKIA|ASIA)[A-Z0-9]{16}")),
)

def _redact_secret_like_text(text):
    message = str(text).encode("utf-8", errors="replace")
    for _name, pattern in _SECRET_MARKERS:
        message = pattern.sub(b"[redacted secret-like value]", message)
    return message.decode("utf-8", errors="replace")


def _check_secret_like_assets(asset_data, *, fail_on_secret_like=False):
    for ordinal, data in enumerate(asset_data.values(), start=1):
        categories = [name for name, pattern in _SECRET_MARKERS if pattern.search(data)]
        if categories:
            diagnostic = (
                "MotionPack secret-like content in referenced asset #"
                + str(ordinal) + " (" + ", ".join(categories) + ")"
            )
            if fail_on_secret_like:
                raise ValueError(diagnostic + "; strict scan rejected package")
            print(diagnostic + "; packaging continues and the asset bytes are included", file=sys.stderr)

def _check_secret_like_metadata(manifest_payload, *, fail_on_secret_like=False):
    payload = manifest_payload.encode("utf-8")
    categories = [name for name, pattern in _SECRET_MARKERS if pattern.search(payload)]
    if not categories:
        return
    diagnostic = "MotionPack secret-like content in package metadata (" + ", ".join(categories) + ")"
    if fail_on_secret_like:
        raise ValueError(diagnostic + "; strict scan rejected package")
    print(diagnostic + "; packaging continues and the manifest is included", file=sys.stderr)

def canonicalize_manifest(manifest):
    canonical_manifest = json.loads(json.dumps(manifest))
    canonical_paths = {}
    portable_components = {}
    for aid, raw_path in manifest["assets"].items():
        canonical_path = PurePosixPath(raw_path).as_posix()
        folded_path = unicodedata.normalize("NFC", canonical_path).casefold()
        previous_path = canonical_paths.get(folded_path)
        if previous_path is not None and previous_path != canonical_path:
            raise ValueError("casefold collision for asset path " + _redact_secret_like_text(canonical_path))
        canonical_paths[folded_path] = canonical_path
        parts = PurePosixPath(canonical_path).parts
        for index in range(len(parts)):
            prefix_key = tuple(unicodedata.normalize("NFC", part).casefold() for part in parts[:index + 1])
            prefix_spelling = tuple(unicodedata.normalize("NFC", part) for part in parts[:index + 1])
            previous_spelling = portable_components.get(prefix_key)
            if previous_spelling is not None and previous_spelling != prefix_spelling:
                raise ValueError("path component collision for asset path " + _redact_secret_like_text(canonical_path))
            portable_components[prefix_key] = prefix_spelling
        canonical_manifest["assets"][aid] = canonical_path
    return canonical_manifest

def _png_chunk(kind, payload):
    return (
        struct.pack(">I", len(payload)) + kind + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
    )


def _encode_rgba_png(decoded, *, max_output_bytes):
    width, height, rgba = decoded.width, decoded.height, decoded.rgba
    if (type(width) is not int or type(height) is not int
            or width < 1 or height < 1 or width > 8192 or height > 8192
            or width * height > 16_000_000
            or not isinstance(rgba, bytes) or len(rgba) != width * height * 4
            or type(max_output_bytes) is not int or max_output_bytes < 1):
        raise ValueError("isolated raster decoder returned invalid RGBA dimensions")
    output = bytearray(b"\x89PNG\r\n\x1a\n")
    if len(output) + 25 + 12 > max_output_bytes:
        raise ValueError("isolated raster preview exceeds its encoded output limit")

    def append_chunk(kind, payload):
        chunk_size = 12 + len(payload)
        if len(output) + chunk_size > max_output_bytes:
            raise ValueError("isolated raster preview exceeds its encoded output limit")
        output.extend(_png_chunk(kind, payload))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    append_chunk(b"IHDR", ihdr)
    compressor = zlib.compressobj(level=6)
    stride = width * 4
    for row in range(height):
        start = row * stride
        encoded = compressor.compress(b"\0" + rgba[start:start + stride])
        if encoded:
            append_chunk(b"IDAT", encoded)
    tail = compressor.flush()
    if tail:
        append_chunk(b"IDAT", tail)
    append_chunk(b"IEND", b"")
    return bytes(output)



def render_preview_html(embedded):
    """Render the existing offline reference player from pre-validated embedded asset URLs."""
    runtime = Path(__file__).resolve().parent.parent / "runtime"
    rig = (runtime / "rig.js").read_text(encoding="utf-8")
    evaluator = (runtime / "evaluator.js").read_text(encoding="utf-8")
    player_controller = (runtime / "player_controller.js").read_text(encoding="utf-8")
    motion_director = (runtime / "motion_director.js").read_text(encoding="utf-8")
    viewport_adapter = (runtime / "viewport_adapter.js").read_text(encoding="utf-8")
    pointer_ik_adapter = (runtime / "pointer_ik_adapter.js").read_text(encoding="utf-8")
    hit_test = (runtime / "hit_test.js").read_text(encoding="utf-8")
    interaction_adapter = (runtime / "interaction_adapter.js").read_text(encoding="utf-8")
    viewer = (runtime / "viewer.js").read_text(encoding="utf-8")
    payload = json.dumps(embedded, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    # No untrusted source code or arbitrary scripts are allowed inside the bundle.
    page = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MotionPack Preview</title><style>
*{box-sizing:border-box}body{margin:0;background:#111c2d;color:#edf6ff;font:15px system-ui;display:flex;justify-content:center}
.shell{width:min(100%,750px);padding:20px}.panel{background:#1b2940;border:1px solid #3b597c;border-radius:12px;padding:12px}
.viewport{width:100%;aspect-ratio:1 / 1;max-height:75vh;overflow:hidden;background:#081324}
canvas{display:block;width:100%;height:100%;background:#081324}
button{padding:10px;background:#345f8e;color:white;border:1px solid #78a2c9;border-radius:8px;margin:4px;cursor:pointer}
</style></head><body><div class="shell"><h2>MotionPack experimental preview</h2><div class="panel">
<div class="viewport" id="viewport"><canvas id="stage"></canvas></div><div><button id="idle">Idle</button><button id="fire">Fire beam</button>
<button id="transform">Switch form</button><button id="reset">Reset</button><button id="aim">Pointer IK: OFF</button></div>
<p id="asset-error" role="status" aria-live="polite" hidden></p><p id="status"></p></div></div><script>window.__MOTIONPACK__=""" + payload + ";</script><script>" + rig + "</script><script>" + evaluator + "</script><script>" + player_controller + "</script><script>" + motion_director + "</script><script>" + viewport_adapter + "</script><script>" + pointer_ik_adapter + "</script><script>" + hit_test + "</script><script>" + interaction_adapter + "</script><script>" + viewer + "</script></body></html>"
    return page


def build(folder, out, *, fail_on_secret_like=False, isolated_raster_decode=False):
    try:
        root = Path(folder).resolve(strict=True)
    except (RuntimeError, OSError) as exc:
        raise ValueError("unable to resolve project root") from exc
    out = Path(out).resolve()
    asset_data_by_manifest_path = {}
    errors, manifest = validate(root, asset_data_sink=asset_data_by_manifest_path)
    if errors:
        raise ValueError(_redact_secret_like_text("; ".join(errors)))
    canonicalization_error = None
    try:
        canonical_manifest = canonicalize_manifest(manifest)
    except ValueError as exc:
        canonicalization_error = _redact_secret_like_text(exc)
    if canonicalization_error is not None:
        raise ValueError(canonicalization_error)
    manifest_payload = json.dumps(canonical_manifest, ensure_ascii=False, indent=2)
    asset_data = {}
    for asset_id, raw_path in manifest["assets"].items():
        rel = canonical_manifest["assets"][asset_id]
        asset_data.setdefault(rel, asset_data_by_manifest_path[raw_path])

    _check_secret_like_metadata(manifest_payload, fail_on_secret_like=fail_on_secret_like)
    _check_secret_like_assets(asset_data, fail_on_secret_like=fail_on_secret_like)

    preview_png_by_path = None
    if isolated_raster_decode:
        preview_png_by_path = {}
        remaining_pixels = RasterDecodeLimits().max_input_pixels
        total_preview_png_bytes = 0
        decode_deadline = time.monotonic() + RASTER_PREVIEW_TOTAL_TIMEOUT_SECONDS
        for rel, source_bytes in asset_data.items():
            if remaining_pixels < 1:
                raise ValueError("isolated raster preview exceeds aggregate pixel limit")
            remaining_time = decode_deadline - time.monotonic()
            if remaining_time <= 0:
                raise ValueError("isolated raster preview exceeded its total decode deadline")
            try:
                decoded = decode_raster_assets_isolated(
                    {"asset": source_bytes}, {"asset": rel},
                    limits=RasterDecodeLimits(
                        max_input_pixels=remaining_pixels,
                        max_decoded_pixels=remaining_pixels,
                    ),
                    timeout=min(RASTER_PREVIEW_PER_ASSET_TIMEOUT_SECONDS, remaining_time),
                )
            except RasterDecodeError as exc:
                raise ValueError("isolated raster preview decoding failed") from exc
            if set(decoded) != {"asset"}:
                raise ValueError("isolated raster decoder returned unexpected assets")
            raster = decoded["asset"]
            preview_png = _encode_rgba_png(
                raster, max_output_bytes=64 * 1024 * 1024 - total_preview_png_bytes
            )
            total_preview_png_bytes += len(preview_png)
            preview_png_by_path[rel] = preview_png
            remaining_pixels -= raster.width * raster.height
        total_embedded_png_bytes = 0
        for rel in canonical_manifest["assets"].values():
            total_embedded_png_bytes += len(preview_png_by_path[rel])
            if total_embedded_png_bytes > 64 * 1024 * 1024:
                raise ValueError("isolated raster preview exceeds its 64 MiB encoded output limit")

    with tempfile.TemporaryDirectory(prefix="motionpack-build-") as snapshot_name:
        snapshot_root = Path(snapshot_name)
        (snapshot_root / "manifest.json").write_text(manifest_payload, encoding="utf-8")
        for rel, data in asset_data.items():
            destination = snapshot_root.joinpath(*PurePosixPath(rel).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        snapshot_errors, _ = validate(snapshot_root)
        if snapshot_errors:
            raise ValueError(_redact_secret_like_text(
                "asset snapshot failed validation: " + "; ".join(snapshot_errors)
            ))

        out.mkdir(parents=True, exist_ok=True)
        package = out / (root.name + ".motionpack")
        with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
            archive.writestr("manifest.json", manifest_payload)
            for rel, data in asset_data.items():
                archive.writestr(rel, data)
        embedded = json.loads(json.dumps(canonical_manifest))
        for key, rel in canonical_manifest["assets"].items():
            if preview_png_by_path is None:
                data = asset_data[rel]
                mime = mimetypes.guess_type(rel)[0] or "application/octet-stream"
            else:
                data = preview_png_by_path[rel]
                mime = "image/png"
            embedded["assets"][key] = "data:" + mime + ";base64," + base64.b64encode(data).decode("ascii")
        page = render_preview_html(embedded)
        preview = out / "preview.html"
        preview.write_text(page, encoding="utf-8")
    return package, preview

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("project")
    p.add_argument("--out", default="dist")
    p.add_argument(
        "--isolated-raster-decode",
        action="store_true",
        help="decode referenced static PNG/JPEG/WebP assets in the isolated worker and embed canonical PNGs in the preview",
    )
    p.add_argument(
        "--fail-on-secret-like",
        action="store_true",
        help="fail before writing outputs when package metadata or a referenced asset matches a known secret-like pattern",
    )
    args = p.parse_args()
    try:
        a, b = build(args.project, args.out, fail_on_secret_like=args.fail_on_secret_like, isolated_raster_decode=args.isolated_raster_decode)
        print("Built:", a, a.stat().st_size, "bytes")
        print("Built:", b, b.stat().st_size, "bytes")
    except (OSError, ValueError, TypeError) as e:
        print("Build failed:", _redact_secret_like_text(e), file=sys.stderr)
        sys.exit(1)
