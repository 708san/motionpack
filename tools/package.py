#!/usr/bin/env python3
"""Package editable .motionpack ZIP and offline browser preview. No runtime network required."""
from pathlib import Path, PurePosixPath
import argparse
import base64
import json
import mimetypes
import sys
import tempfile
import unicodedata
import zipfile
from validate import validate

def canonicalize_manifest(manifest):
    canonical_manifest = json.loads(json.dumps(manifest))
    canonical_paths = {}
    portable_components = {}
    for aid, raw_path in manifest["assets"].items():
        canonical_path = PurePosixPath(raw_path).as_posix()
        folded_path = unicodedata.normalize("NFC", canonical_path).casefold()
        previous_path = canonical_paths.get(folded_path)
        if previous_path is not None and previous_path != canonical_path:
            raise ValueError("casefold collision for asset path " + canonical_path)
        canonical_paths[folded_path] = canonical_path
        parts = PurePosixPath(canonical_path).parts
        for index in range(len(parts)):
            prefix_key = tuple(unicodedata.normalize("NFC", part).casefold() for part in parts[:index + 1])
            prefix_spelling = tuple(unicodedata.normalize("NFC", part) for part in parts[:index + 1])
            previous_spelling = portable_components.get(prefix_key)
            if previous_spelling is not None and previous_spelling != prefix_spelling:
                raise ValueError("path component collision for asset path " + canonical_path)
            portable_components[prefix_key] = prefix_spelling
        canonical_manifest["assets"][aid] = canonical_path
    return canonical_manifest

def build(folder, out):
    try:
        root = Path(folder).resolve()
    except RuntimeError as exc:
        raise ValueError("unable to resolve project root") from exc
    out = Path(out).resolve()
    asset_data_by_manifest_path = {}
    errors, manifest = validate(root, asset_data_sink=asset_data_by_manifest_path)
    if errors:
        raise ValueError("; ".join(errors))
    canonical_manifest = canonicalize_manifest(manifest)
    manifest_payload = json.dumps(canonical_manifest, ensure_ascii=False, indent=2)
    asset_data = {}
    for asset_id, raw_path in manifest["assets"].items():
        rel = canonical_manifest["assets"][asset_id]
        asset_data.setdefault(rel, asset_data_by_manifest_path[raw_path])

    with tempfile.TemporaryDirectory(prefix="motionpack-build-") as snapshot_name:
        snapshot_root = Path(snapshot_name)
        (snapshot_root / "manifest.json").write_text(manifest_payload, encoding="utf-8")
        for rel, data in asset_data.items():
            destination = snapshot_root.joinpath(*PurePosixPath(rel).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        snapshot_errors, _ = validate(snapshot_root)
        if snapshot_errors:
            raise ValueError("asset snapshot failed validation: " + "; ".join(snapshot_errors))

        out.mkdir(parents=True, exist_ok=True)
        package = out / (root.name + ".motionpack")
        with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
            archive.writestr("manifest.json", manifest_payload)
            for rel, data in asset_data.items():
                archive.writestr(rel, data)
        embedded = json.loads(json.dumps(canonical_manifest))
        for key, rel in canonical_manifest["assets"].items():
            data = asset_data[rel]
            mime = mimetypes.guess_type(rel)[0] or "application/octet-stream"
            embedded["assets"][key] = "data:" + mime + ";base64," + base64.b64encode(data).decode("ascii")
        runtime = Path(__file__).resolve().parent.parent / "runtime"
        rig = (runtime / "rig.js").read_text(encoding="utf-8")
        viewer = (runtime / "viewer.js").read_text(encoding="utf-8")
        payload = json.dumps(embedded, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        # No untrusted source code or arbitrary scripts are allowed inside the bundle.
        page = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MotionPack Preview</title><style>
*{box-sizing:border-box}body{margin:0;background:#111c2d;color:#edf6ff;font:15px system-ui;display:flex;justify-content:center}
.shell{width:min(100%,750px);padding:20px}.panel{background:#1b2940;border:1px solid #3b597c;border-radius:12px;padding:12px}
canvas{width:100%;height:auto;max-height:75vh;object-fit:contain;background:#081324}
button{padding:10px;background:#345f8e;color:white;border:1px solid #78a2c9;border-radius:8px;margin:4px;cursor:pointer}
</style></head><body><div class="shell"><h2>MotionPack experimental preview</h2><div class="panel">
<canvas id="stage"></canvas><div><button id="idle">Idle</button><button id="fire">Fire beam</button>
<button id="transform">Switch form</button><button id="reset">Reset</button><button id="aim">Pointer IK: OFF</button></div>
<p id="status"></p></div></div><script>window.__MOTIONPACK__=""" + payload + ";</script><script>" + rig + "</script><script>" + viewer + "</script></body></html>"
        preview = out / "preview.html"
        preview.write_text(page, encoding="utf-8")
    return package, preview

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("project")
    p.add_argument("--out", default="dist")
    args = p.parse_args()
    try:
        a, b = build(args.project, args.out)
        print("Built:", a, a.stat().st_size, "bytes")
        print("Built:", b, b.stat().st_size, "bytes")
    except (OSError, ValueError, TypeError) as e:
        print("Build failed:", str(e), file=sys.stderr)
        sys.exit(1)
