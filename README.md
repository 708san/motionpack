# MotionPack — repository bootstrap / development governance v1.0

**Public pre-alpha source repository. No software license has been selected; public visibility does not grant general reuse rights. This is not a stable software release.**

Start with [the public repository onboarding guide](docs/REPOSITORY_CREATION.md), [governance policy](docs/DEVELOPMENT_GOVERNANCE_V1.md), [11 agent roles](docs/AGENT_ROLES.md), and [root instructions](AGENTS.md).

---

# MotionPack — engine-independent, editable motion illustration (v0.2-alpha)

**Goal:** an engine-agnostic image-layer + motion + visual effects + variant asset package that an AI authoring skill can edit, independent of any specific game.

## Distribution layers

See [docs/ARCHITECTURE_AND_DISTRIBUTION.md](docs/ARCHITECTURE_AND_DISTRIBUTION.md) for proposed spec/runtime/tools/skill/optional agent packages. **This is not a published standard, plugin, or finished SDK.**

## What actually works

- `.motionpack` ZIP with editable layers, JSON manifest, clips, effects, two visual variants (existing v0.1).
- v0.2-alpha: 2-bone inverse kinematics (IK) with local parent transforms and animated target, plus interactive pointer targeting in browser preview.
- Original beam, particles, glow rings, clip/variant switch; controls available in single-file HTML preview.
- Static format checks, deterministic IK tests, JavaScript runtime smoke tests, browser visual smoke check.
- Basic authoring skill instructions. AI auto-rigging, accurate background removal and generation are **not** implemented.

## Quick start

```bash
python tools/validate.py examples/robot_ik_demo
python tools/package.py examples/robot_ik_demo --out dist
node tests/ik_test.js
node tests/runtime_ik_smoke.js
python -m unittest discover -s tests -v
```

Open `dist/preview.html` in a browser; it is offline and self-contained. The **Pointer IK** button lets the arm track cursor movement on canvas. **Fire beam** plays a scripted aiming and particle effect. **Switch form** shows sparse visual variants. No game rules or action results are stored in the asset.

For the older example (format 0.1), use `examples/robot_demo`.

## Folder overview

- `docs/`: spec, design decisions, distribution roadmap, limitations.
- `examples/robot_ik_demo`: rigged robot example, 10 SVG layers, v0.2 manifest.
- `examples/robot_demo`: backwards-compatible v0.1 example.
- `runtime/rig.js`: deterministic two-bone IK calculations; Node/browser-compatible.
- `runtime/viewer.js`: offline Canvas 2D reference viewer (not polished SDK).
- `tools/`: Python validator and packager.
- `skills/motionpack-authoring`: Agent Skills-compatible authoring instructions.
- `tests/`: unit and smoke tests.
- `dist/`: generated `.motionpack`, `preview.html` and browser screenshots.

### Limitations

- Only two-segment IK; no weighted deformable mesh or skinning.
- Current player coupled to a browser Canvas/HTML shell; `window.MotionPackPlayer` is a provisional host API.
- Standalone preview uses inlined asset data, therefore repeated large image layers may make it heavier than the editable archive.
- Native Unity, Unreal, Godot adapters do not exist yet.
- Actual costs depend on art resolution and complexity; demo uses tiny hand-crafted SVG illustrations.