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
- `examples/`: demonstration layered assets and manifests for versions 0.1 and 0.2
- `tests/`: functional and basic malicious-input regression tests
- `.codex/agents/`: eleven development subagent definitions (not consumer asset-authoring agents)
- `docs/`: format specification, architecture and development governance

## Security, compatibility and licensing

See [format specification](docs/FORMAT_SPEC.md), [security policy](docs/SECURITY_POLICY.md) and [development governance](docs/DEVELOPMENT_GOVERNANCE_V1.md).
**Do not treat current tools as safe for arbitrary untrusted `.motionpack` files.** The ZIP archive import/extraction pathway and full SVG sanitization remain future work.

Public repository visibility does not grant software reuse rights. **No software license has been selected yet.**
