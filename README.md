# MotionPack

**Experimental pre-alpha**: portable, editable 2D visual-motion format, offline browser player, two-bone inverse kinematics (IK) and bounded visual effects.

MotionPack is intentionally **not** a card-game format. The runtime does not require AI services or network access. The current preview is a reference demo, not a production SDK.

## Quick start

```sh
python3 tools/validate.py examples/robot_ik_demo
python3 tools/validate.py examples/robot_demo
python3 tools/package.py examples/robot_ik_demo --out dist
node tests/ik_test.js
node tests/runtime_smoke.js
node tests/runtime_ik_smoke.js
python3 -m unittest discover -s tests -v
```

Open `dist/preview.html` in a browser. Buttons demonstrate idle motion, beam firing, form switching and optional pointer aiming.

## Project layout

- `runtime/`: experimental Canvas2D player and IK solver
- `tools/`: editable package validator and builder
- `examples/`: demonstration layered assets and manifests for versions 0.1–0.3
- `tests/`: functional and basic malicious-input regression tests
- `.codex/agents/`: eleven development subagent definitions (not consumer asset-authoring agents)
- `docs/`: format specification, architecture and development governance

## Security, compatibility and licensing

See [format specification](docs/FORMAT_SPEC.md), [security policy](docs/SECURITY_POLICY.md) and [development governance](docs/DEVELOPMENT_GOVERNANCE_V1.md).
`tools/archive_reader.py` adds a bounded, read-only ZIP inspection path for v0.1/v0.2/v0.3 packages. v0.3 requires bounded numeric-px dimensions on SVG roots; older versions continue accepting dimensionless SVG. `read_package_isolated()` is an opt-in subprocess wrapper with a wall-clock deadline and bounded result protocol; memory enforcement is platform-specific (Linux address space, Windows committed memory, none on macOS). Neither reader extracts arbitrary entries or reads optional `source/` entries. The packager emits only manifest-referenced runtime assets, uses the bytes validated for both the ZIP and preview, and rejects runtime references into `source/`. It scans serialized manifest metadata, including asset paths, and referenced-asset bytes for a small set of private-key and credential-like patterns. By default it warns and continues; pass `--fail-on-secret-like` to stop before writing outputs on a match. The heuristic can miss secrets or produce false positives. The validator checks a limited static SVG subset and header dimensions for PNG/JPEG/WebP assets by filename extension, with raster pixel ceilings; neither makes the reader a production security boundary. Bounded Atheris targets exercise ZIP reading, SVG validation, and PNG/JPEG/WebP header parsers (15 seconds per target on PRs, 300 seconds per target weekly/manual); this is smoke coverage, not sustained fuzzing or a security guarantee. Raster decoders remain untested and unisolated. See [SECURITY.md](SECURITY.md).

Public repository visibility does not grant software reuse rights. **No software license has been selected yet.**

## v0.3 layered source example

`examples/layered_plant_demo` keeps a complete source illustration under `source/` and assembles its manually separated parts as editable runtime layers. The source note maps each layer to the original and records the overlap used to preserve the composition. The package builder excludes `source/` by default.

```sh
python3 tools/validate.py examples/layered_plant_demo
python3 tools/package.py examples/layered_plant_demo --out /tmp/motionpack_layered_plant
```

Open `/tmp/motionpack_layered_plant/preview.html` locally. This example demonstrates a manual separation workflow; it does not perform automatic segmentation, recover occluded pixels, or define a formal provenance schema.

## Browser visual regression pilot

The Issue #5 pilot uses Playwright 1.65.0 with its matching Chromium build to compare five fixed states from the offline v0.2 preview: idle/fire at 800 ms, transform at 1,008 ms, form change after 800 ms in the new form, and pointer IK at 800 ms. The demo uses a 1000 × 1000 canvas so the character and effects fit in all five reference images. Five maintainer-reviewed Linux Chromium baselines are checked in under `tests/visual.spec.js-snapshots/`. Install with `npm ci` and `npx playwright install chromium`, then run `npm run test:visual`; pixel comparisons run on the pinned Linux reference platform, while other platforms run the capture and behavior checks without comparing pixels. CI compares against the references in the matching Playwright 1.65.0 Ubuntu 24.04 container pinned by digest. Update a baseline only for an intentional visual change, review the new Linux PNGs, and record the reason in the PR; `npm run test:visual -- --update-snapshots=all` writes updated snapshots on Linux. This pilot covers one Chromium/Linux environment and does not add a frozen v0.1 fixture, establish cross-browser parity, or assess natural motion. Performance measurements remain a separate follow-up.
