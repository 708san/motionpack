# Rust clip timeline milestone 1

**Status:** Experimental host-owned timeline kernel. This increment extends `core/` to evaluate arbitrary ordered scalar keyframe tracks, loop/clamp time, apply sparse per-node pose overrides and preserve the JavaScript evaluator's source-order track override semantics. No .motionpack schema changes.

## Implemented

- `core/src/timeline.rs`: `clip_time`, `sample_track`, `sample_clip` and typed `Pose`, `Keyframe`, `Track`, `VariantNode` inputs.
- Validates finite time, positive duration, strictly increasing key times and finite values; limits each track, node list, variant list and track list to 4096 entries. Invalid references and nonfinite poses fail with typed errors.
- `mp_clip_time` provides an additional stable numeric-only native/Wasm symbol for comparing loop and nonloop semantics.
- `motionpack_core_probe track` accepts validated argument data and samples a complete keyframe track natively (developer test tool only).
- On Windows, macOS and Linux, `tests/rust_timeline_parity_test.js` compares full scalar tracks from three bundled MotionPack examples against the existing JavaScript evaluator. WebAssembly clip-time exports are compared against JS modulo and clamp behavior on Linux.

## Limitations

The typed Rust library currently receives **already parsed and validated data** from its trusted host. It does not parse ZIP/JSON, load textures, support inverse kinematics (IK), effects, nested sprite rendering, semantic behavior or procedural motion in Rust. Existing JS evaluator and Python bounded archive reader remain canonical. Keyframe parity tests skip scalar properties overridden by the existing JS IK solver until IK is ported.

The Rust native and Wasm output remains an **engine implementation detail**, not a video file. Original editable .motionpack assets retain clip IDs, layers, keyframes, and host-triggered interactions.

## Next steps

Port IK, build Rust full-pose and effects parity, then expose an owned-memory stable native/C# and Wasm API and connect image loading + rendering to Unity and desktop environments. Repeat binary compatibility checks on actual Unity Editor and supported platforms before claiming SDK readiness.
