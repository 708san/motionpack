# Interactive Seal demo

A small offline example for inspecting editable art layers and host-driven interaction in a 91:55 frame. The seal idles gently. Touching or clicking the seal cross-fades into a soft flattened pose, rebounds, and returns to idle. The background is not interactive.

The manifest uses existing v0.4 node interaction notifications. It contains no script, callback name, URL or action. The generated HTML includes a trusted, example-only host wrapper that maps notifications to the sample clips and provides a keyboard activation button.

Run from the repository root:

```sh
python3 tools/validate.py examples/interactive_seal_demo
python3 tools/package.py examples/interactive_seal_demo --out /tmp/motionpack_interactive_seal
python3 examples/interactive_seal_demo/build_preview.py --out /tmp/motionpack_interactive_seal
```

Open `/tmp/motionpack_interactive_seal/interactive_seal_demo.html`. The HTML is self-contained and works offline. Its embedded static image remains available when JavaScript is disabled.

The artwork is manually authored and layered. See `source/README.md` for the unchanged original, layer mapping and editing notes. The preview uses the experimental Canvas 2D renderer. Playwright device emulation is reported separately from real iOS, Android and desktop browser tests; this demo does not claim physical-device support.
