# Rust two-bone IK milestone

**Status:** An opt-in, numerical inverse kinematics primitive compiled to native and WebAssembly. This is not yet the production animation renderer nor a complete Rust pose evaluator.

## What is implemented

- `core/src/ik.rs` mirrors JavaScript `runtime/rig.js`'s two-bone IK solver: clamped reachable range, bend sign, upper/lower rotations, elbow/hand coordinates, reached flag and a separate finite-weight rotation blend.
- Numeric-only exports `mp_ik_upper_deg` and `mp_ik_lower_deg` are callable from native hosts and WebAssembly. They return NaN on invalid parameters. There is no pointer ownership or memory sharing required for these primitives.
- `motionpack_core_probe ik` exposes the full solution for developer tests; it is a **trusted test program**, not a .motionpack player.
- Parity tests compare Rust output against JavaScript over reachable, unreachable, zero-offset and both bend directions, plus robot-like origin/targets. CI runs native on Windows/macOS/Linux and Wasm on Linux.

## Scope and limitations

The host still resolves parent/world matrices, translates target points into a chain's parent-local coordinates, chooses the IK profile, and applies transforms. The current Rust clip evaluator and Rust IK solver are separate components: full-pose evaluation and the image renderer remain in the JavaScript reference implementation. This PR does **not** parse .motionpack archives, execute scripts, support arbitrary physics or prove real-time Unity rendering.

The source format stays unchanged. Next: connect typed Rust clip outputs and IK chain definitions, then compare full node poses, dynamic targets, effects and runtime overhead against the reference before changing the default playback engine.
