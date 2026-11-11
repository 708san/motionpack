#!/usr/bin/env python3
"""Build the editable package and trusted, example-only offline HTML preview."""
from pathlib import Path
import argparse
import base64
import sys

ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from package import build  # noqa: E402
from validate import MAX_ASSET, validate_svg  # noqa: E402


def replace_once(document, old, new):
    if old not in document:
        raise ValueError("preview template no longer contains expected marker: " + old[:80])
    return document.replace(old, new, 1)


def load_fallback(path):
    data = Path(path).read_bytes()
    if len(data) > MAX_ASSET:
        raise ValueError("static fallback SVG exceeds the asset size limit")
    errors = validate_svg(data, require_dimensions=True)
    if errors:
        raise ValueError("invalid static fallback SVG: " + "; ".join(errors))
    return data


def build_demo(out, fallback_path=None):
    out = Path(out).resolve()
    fallback_path = Path(fallback_path) if fallback_path else PROJECT / "assets" / "static_fallback.svg"
    fallback_data = load_fallback(fallback_path)
    package, preview = build(PROJECT, out, fail_on_secret_like=True)
    html = preview.read_text(encoding="utf-8")
    fallback = base64.b64encode(fallback_data).decode("ascii")

    html = replace_once(html, "<title>MotionPack Preview</title>",
                        "<title>Interactive Seal — MotionPack example</title>")
    html = replace_once(html, "<h2>MotionPack experimental preview</h2>",
                        "<h2>Interactive Seal</h2>")
    html = replace_once(html, "<canvas id=\"stage\"></canvas>",
                        '<img id="static-fallback" class="static-fallback" alt="Static illustration of a seal resting by the sea" src="data:image/svg+xml;base64,'
                        + fallback + '"><canvas id="stage"></canvas>')
    html = replace_once(html, '<p id="asset-error"',
                        '<div class="demo-controls"><button id="seal-activate" type="button" aria-label="Activate the seal">Tap or click the seal</button></div><p id="asset-error"')

    styles = """
#viewport{position:relative;aspect-ratio:91 / 55!important;max-height:none!important;background:#d9efea}
#stage{position:absolute;inset:0;width:100%;height:100%;z-index:1}
.static-fallback{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;z-index:2}
.static-fallback[hidden]{display:none}
#idle,#fire,#transform,#reset,#aim{display:none}
.demo-controls{display:flex;justify-content:center;padding:8px}
#seal-activate{font-size:1rem;padding:12px 22px}
"""
    html = replace_once(html, "</style>", styles + "</style>")

    host_script = """
<script>
(function(){
  'use strict';
  var fallback=document.getElementById('static-fallback');
  var canvas=document.getElementById('stage');
  var status=document.getElementById('status');
  var button=document.getElementById('seal-activate');
  var locked=false;
  window.__sealActivations=0;
  function activate(kind){
    if(locked||!window.MotionPackPlayer)return;
    locked=true;
    window.__sealActivations+=1;
    document.body.setAttribute('data-seal-input',kind);
    window.MotionPackPlayer.playClip('squish','rest');
    window.setTimeout(function(){locked=false;},650);
  }
  window.addEventListener('motionpack:interaction',function(event){
    var detail=event.detail||{};
    if(detail.nodeId!=='seal_hit')return;
    if(detail.type==='hoverenter')document.body.setAttribute('data-seal-hover','true');
    if(detail.type==='hoverleave')document.body.setAttribute('data-seal-hover','false');
    if(detail.type==='tap'||detail.type==='click')activate(detail.type);
  });
  button.addEventListener('click',function(){
    if(window.MotionPackInteractions)window.MotionPackInteractions.activate('seal_hit');
  });
  var attempts=0;
  var reveal=setInterval(function(){
    attempts+=1;
    try{
      var context=canvas.getContext('2d');
      var x=Math.max(0,Math.floor(canvas.width*.5));
      var y=Math.max(0,Math.floor(canvas.height*.73));
      var pixel=context.getImageData(x,y,1,1).data;
      if(Math.abs(pixel[0]-217)+Math.abs(pixel[1]-239)+Math.abs(pixel[2]-234)>12){
        fallback.hidden=true;
        clearInterval(reveal);
      }
    }catch(_){}
    if(attempts>100)clearInterval(reveal);
  },40);
})();
</script>
"""
    html = replace_once(html, "</body></html>", host_script + "</body></html>")
    output = out / "interactive_seal_demo.html"
    output.write_text(html, encoding="utf-8")
    return package, output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="dist")
    parser.add_argument("--fallback", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        package, html = build_demo(args.out, args.fallback)
    except (OSError, ValueError, TypeError) as exc:
        print("Build failed:", exc, file=sys.stderr)
        raise SystemExit(1)
    print("Built:", package, package.stat().st_size, "bytes")
    print("Built:", html, html.stat().st_size, "bytes")
