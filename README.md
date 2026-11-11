# MotionPack

**Experimental pre-alpha**: portable, editable 2D visual-motion format, offline browser player, two-bone inverse kinematics (IK), bounded visual effects, and opt-in v0.4 node interaction events.

MotionPack is intentionally **not** a card-game format. The runtime does not require AI services or network access. The current preview is a reference demo, not a production SDK.

## Quick start

```sh
python3 tools/validate.py examples/robot_ik_demo
python3 tools/validate.py examples/robot_demo
python3 tools/package.py examples/robot_ik_demo --out dist
# Optional: isolate static PNG/JPEG/WebP preview decoding (requires Pillow)
python3 tools/package.py examples/robot_ik_demo --out dist-isolated --isolated-raster-decode
node tests/ik_test.js
node tests/evaluator_test.js
node tests/player_controller_test.js
node tests/hit_test_test.js
node tests/interaction_adapter_test.js
node tests/interaction_preview_smoke.js
node tests/pointer_ik_adapter_test.js
node tests/preview_facade_test.js
node tests/viewport_adapter_test.js
node tests/runtime_smoke.js
node tests/runtime_ik_smoke.js
python3 -m unittest discover -s tests -v
```

Open `dist/preview.html` in a browser. Buttons demonstrate idle motion, beam firing, form switching and optional pointer aiming. The optional `--isolated-raster-decode` mode accepts only projects whose referenced runtime assets are static PNG/JPEG/WebP, decodes them in the resource-limited Pillow worker, and embeds canonical PNG data in the preview. The `.motionpack` archive keeps original asset bytes. Assets are decoded one at a time under the shared 64 MP pixel budget; canonical preview PNG output is capped at 64 MiB total. SVG, animated and unsupported assets fail closed. The default packaging path does not require Pillow and is unchanged.

## Project layout

- `runtime/`: experimental Canvas2D preview, stateless pose evaluator, host-driven player controller, hit-test and node-interaction helpers, pointer-to-IK adapter and IK solver
- `tools/`: editable package validator and builder
- `examples/`: demonstration layered assets and manifests for versions 0.1–0.4
- `tests/`: functional and basic malicious-input regression tests
- `.codex/agents/`: eleven development subagent definitions (not consumer asset-authoring agents)
- `docs/`: format specification, architecture and development governance

## Security, compatibility and licensing

See [format specification](docs/FORMAT_SPEC.md), [security policy](docs/SECURITY_POLICY.md) and [development governance](docs/DEVELOPMENT_GOVERNANCE_V1.md).
`tools/archive_reader.py` adds a bounded, read-only ZIP inspection path for v0.1–v0.4 packages. v0.3 and v0.4 require bounded numeric-px dimensions on SVG roots; older versions continue accepting dimensionless SVG. v0.4 adds per-node opt-in `hover`, `tap` and `click` booleans. The generated preview emits host-facing `motionpack:interaction` events only; host applications choose any resulting behavior. Its separate `MotionPackInteractions.activate(nodeId)` hook lets accessible host controls map keyboard activation to an opted-in click event. `read_package()` uses the isolated subprocess reader by default; `read_package_in_process()` is available for trusted local inputs when callers explicitly accept in-process parsing. The default adds subprocess startup and uses a 40 MiB input snapshot, a 40 MiB response cap, a 30-second deadline (maximum 300 seconds), and a 512 MiB memory limit on Linux/Windows; macOS has no hard whole-process memory limit. This is defense in depth, not a sandbox. The default reader calls neither decompress nor return optional `source/` entries; the explicit `tools.legacy_importer.import_legacy_package()` API retains every validated regular-file payload, including opaque `source/` bytes, in a read-only in-memory snapshot under the same ZIP limits and isolated 40 MiB response ceiling. It supports experimental v0.1–v0.4 and does not serialize a v1 package. See [legacy import snapshot](docs/LEGACY_IMPORT_SNAPSHOT.md). The packager emits only manifest-referenced runtime assets, uses the bytes validated for both the ZIP and preview, and rejects runtime references into `source/`. It scans serialized manifest metadata, including asset paths, and referenced-asset bytes for a small set of private-key and credential-like patterns. By default it warns and continues; pass `--fail-on-secret-like` to stop before writing outputs on a match. The heuristic can miss secrets or produce false positives. The validator checks a limited static SVG subset and header dimensions for PNG/JPEG/WebP assets by filename extension, with raster pixel ceilings; neither makes the reader a production security boundary. Bounded Atheris targets exercise ZIP reading, SVG validation, and PNG/JPEG/WebP header parsers (15 seconds per target on PRs, 300 seconds per target weekly/manual); this is smoke coverage, not sustained fuzzing or a security guarantee. `decode_raster_assets_isolated()` is a separate opt-in adapter for static PNG/JPEG/WebP assets; it returns RGBA pixels from an optional Pillow subprocess, rejects animated WebP, and does not replace the browser decoder used by offline preview. Install Pillow with `python -m pip install -r requirements-image.txt`. Neither process is an OS permission sandbox. See [SECURITY.md](SECURITY.md).

Public repository visibility does not grant software reuse rights. **No software license has been selected yet.**

## v0.3 layered source example

`examples/layered_plant_demo` keeps a complete source illustration under `source/` and assembles its manually separated parts as editable runtime layers. The source note maps each layer to the original and records the overlap used to preserve the composition. The package builder excludes `source/` by default.

```sh
python3 tools/validate.py examples/layered_plant_demo
python3 tools/package.py examples/layered_plant_demo --out /tmp/motionpack_layered_plant
```

Open `/tmp/motionpack_layered_plant/preview.html` locally. This example demonstrates a manual separation workflow; it does not perform automatic segmentation, recover occluded pixels, or define a formal provenance schema.

## v0.4 node interaction example

`examples/interaction_demo` reuses one image on four nodes: hover-only, tap-only, click-only, and disabled by default. Validate and package it with:

```sh
python3 tools/validate.py examples/interaction_demo
python3 tools/package.py examples/interaction_demo --out /tmp/motionpack_interaction_demo
```

Open `/tmp/motionpack_interaction_demo/preview.html`, then run this host-side listener in its browser console to inspect notifications:

```js
window.addEventListener('motionpack:interaction', event => console.log(event.detail));
```

The host chooses what the events do. To map a host-provided keyboard control to the `click_only` node, call `window.MotionPackInteractions.activate('click_only')`.

## Experimental viewport sizing

The preview keeps the manifest canvas as logical coordinates and defaults to centered `contain` fitting. Hosts may resize the preview viewport in CSS, then call `window.MotionPackViewport.configure({fit, alignX, alignY})` with `contain`, `cover`, or `stretch`; alignment values range from 0 (start) to 1 (end). The logical-to-screen mapping is shared by drawing, pointer IK and v0.4 interactions. The backing bitmap is capped at device-pixel ratio (DPR) 2, 16 megapixels and 8,192 pixels per edge. The format manifest remains unchanged.

The viewport adapter tests include a generic 91:55 canvas ratio, letterboxing, cropping, alignment, CSS-to-logical input mapping and bitmap limits.

## Browser visual regression pilot

The Issue #5 pilot uses Playwright 1.65.0 with its matching Chromium build to compare five fixed states from the offline v0.2 preview: idle/fire at 800 ms, transform at 1,008 ms, form change after 800 ms in the new form, and pointer IK at 800 ms. The demo uses a 1000 × 1000 canvas so the character and effects fit in all five reference images. Five maintainer-reviewed Linux Chromium baselines are checked in under `tests/visual.spec.js-snapshots/`. Install with `npm ci` and `npx playwright install chromium`, then run `npm run test:visual`; pixel comparisons run on the pinned Linux reference platform, while other platforms run the capture and behavior checks without comparing pixels. CI compares against the references in the matching Playwright 1.65.0 Ubuntu 24.04 container pinned by digest. Update a baseline only for an intentional visual change, review the new Linux PNGs, and record the reason in the PR; `npm run test:visual -- --update-snapshots=all` writes updated snapshots on Linux. The same CI run records report-only package build/size, archive-reader load time and peak resident memory for the frozen v0.1 archive and current v0.2 example, plus browser image-readiness time and real frame intervals for the v0.2 preview. Each reader process takes one warm-up and 30 timed reads per fixture; browser timing uses 30 warm-up and 180 measured frames. The JSON report is uploaded with the screenshots. Values have no performance thresholds; each reader subprocess is limited to 20 seconds, the collector subprocess to 60 seconds, and the whole browser test to 120 seconds. Results remain single-runner observations with host scheduling noise; resident-memory counters differ by OS and are not directly comparable. The pilot covers one Chromium/Linux environment and does not establish cross-browser parity or assess natural motion.
