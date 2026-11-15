# MotionPack Rust shared core — milestone 0

Status: **experimental mathematical kernel**, not a replacement for the existing JavaScript runtime or a complete MotionPack loader. This preserves the `.motionpack` data format and existing integrations.

## Architecture and scope

The dependency-free Rust crate in `core/` compiles to a native library or WebAssembly (`wasm32-unknown-unknown`). It does not load archives, render images, execute scripts or read from network or filesystem.

The exported numeric functions are `mp_sample_segment(t,t0,v0,t1,v1)` for smoothstep keyframe interpolation, and `mp_point_x` / `mp_point_y` for a 2D position, rotation in degrees, uniform scale and point transform. A Rust `Affine` type supports parent/child composition. Invalid scalar inputs yield NaN in the exported functions and `None` in typed Rust functions.

These functions implement a **small mathematical slice only**. Actual MotionPack pose evaluation, loop/variant selection, two-bone inverse kinematics (IK), effects, host-side procedural motion and all rendering remain in JavaScript and platform adapters.

## Build and verify

```sh
cargo test --manifest-path core/Cargo.toml --locked
cargo build --manifest-path core/Cargo.toml --locked --bin motionpack_core_probe
node tests/rust_core_parity_test.js native
rustup target add wasm32-unknown-unknown
cargo build --manifest-path core/Cargo.toml --locked --target wasm32-unknown-unknown --release --lib
node tests/rust_core_parity_test.js wasm
```

Rust's native probe calls the same exported primitives as the native library. The WebAssembly test instantiates exported functions directly. Both compare against the existing JavaScript evaluator/rig with an explicit 1e-8 numeric tolerance. CI runs native parity on Windows/macOS/Linux and Wasm parity on Linux. No third-party Rust crates are added.

The module is an **engine component**, not a replacement for the editable `.motionpack` asset. Build outputs under `core/target/` are not packaged inside archives. A WebAssembly binary is not automatically executable in every Unity or mobile application; host runtime support is required.

## Next milestones

1. Port full validated track iteration, clip looping, variants and node pose evaluation, retaining reference parity.
2. Port hierarchical transforms, two-bone IK, effects and optional procedural overlays.
3. Define a safe owned-buffer application binary interface (ABI, binary calling convention), expose pose-frame output to C#/Unity and Wasm, and verify lifecycle and fault handling.
4. Integrate asset import, rendering and packaging in Unity and separate OS-specific native desktop applications.

No production-level MotionPack playback, native Unity player, trusted archive sandbox or fully optimized 60-fps runtime is claimed in this milestone.
