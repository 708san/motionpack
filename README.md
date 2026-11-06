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
- `examples/`: demonstration layered assets and manifests for versions 0.1 and 0.2; generated tests also cover 0.3
- `tests/`: functional and basic malicious-input regression tests
- `.codex/agents/`: eleven development subagent definitions (not consumer asset-authoring agents)
- `docs/`: format specification, architecture and development governance

## Security, compatibility and licensing

See [format specification](docs/FORMAT_SPEC.md), [security policy](docs/SECURITY_POLICY.md) and [development governance](docs/DEVELOPMENT_GOVERNANCE_V1.md).
`tools/archive_reader.py` adds a bounded, read-only ZIP inspection path for v0.1/v0.2/v0.3 packages. v0.3 requires bounded numeric-px dimensions on SVG roots; older versions continue accepting dimensionless SVG. `read_package_isolated()` is an opt-in subprocess wrapper with a wall-clock deadline and bounded result protocol; memory enforcement is platform-specific (Linux address space, Windows committed memory, none on macOS). Neither reader extracts arbitrary entries or reads optional `source/` entries. The packager emits only manifest-referenced runtime assets, uses the bytes validated for both the ZIP and preview, and rejects runtime references into `source/`. It scans serialized manifest metadata, including asset paths, and referenced-asset bytes for a small set of private-key and credential-like patterns. By default it warns and continues; pass `--fail-on-secret-like` to stop before writing outputs on a match. The heuristic can miss secrets or produce false positives. The validator checks a limited static SVG subset and header dimensions for PNG/JPEG/WebP assets by filename extension, with raster pixel ceilings; neither makes the reader a production security boundary. Bounded Atheris targets exercise ZIP reading, SVG validation, and PNG/JPEG/WebP header parsers (15 seconds per target on PRs, 300 seconds per target weekly/manual); this is smoke coverage, not sustained fuzzing or a security guarantee. Raster decoders remain untested and unisolated. See [SECURITY.md](SECURITY.md).

Public repository visibility does not grant software reuse rights. **No software license has been selected yet.**
