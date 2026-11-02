#!/usr/bin/env python3
"""Package editable .motionpack ZIP and offline browser preview. No runtime network required."""
from pathlib import Path
import argparse
import base64
import json
import mimetypes
import sys
import zipfile
from validate import validate

def build(folder, out):
    root = Path(folder).resolve()
    out = Path(out).resolve()
    errors, manifest = validate(root)
    if errors:
        raise ValueError("; ".join(errors))
    out.mkdir(parents=True, exist_ok=True)
    package = out / (root.name + ".motionpack")
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
        for rel in ["manifest.json", *manifest["assets"].values()]:
            archive.write(root / rel, arcname=rel)
        source = root / "source"
        if source.is_dir():
            for p in sorted(source.rglob("*")):
                if p.is_file() and not p.is_symlink() and p.stat().st_size <= 12_000_000 and p.resolve().is_relative_to(root):
                    archive.write(p, arcname=p.relative_to(root).as_posix())
    embedded = json.loads(json.dumps(manifest))
    for key, rel in manifest["assets"].items():
        data = (root / rel).read_bytes()
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
