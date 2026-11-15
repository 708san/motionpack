# WebAssembly full-scene pose bridge (experimental)

MotionPack assets (`.motionpack`) remain ZIP packages of **data**: images, layers, clips and keys. A `.wasm` file is the **shared calculation engine**, not an animation asset and not an OS-executable viewer. One compiled Wasm module can evaluate multiple validated MotionPack manifests.

## This implementation

- `core/src/wasm_scene.rs` exposes bounded `Float64` input/output buffers and a full scene evaluator based on the same Rust logic used by native hosts. It provides host-owned allocate/release functions.
- `runtime/wasm_scene_host.js` converts trusted validated manifests to the numeric Wasm input. It returns the existing `motionpack-pose` JSON frame contract, preserving visual asset IDs and declarative effects for the host renderer.
- `tests/wasm_scene_parity_test.js` uses the actual Wasm binary with robot, IK and plant fixture assets, comparing poses with the existing JavaScript reference player.
- The numeric engine is dependency-free; the JS bridge uses only WebAssembly built-ins and no third-party packages.

## Build and verify

```sh
rustup target add wasm32-unknown-unknown
cargo build --manifest-path core/Cargo.toml --locked --release --lib --target wasm32-unknown-unknown
node tests/wasm_scene_parity_test.js
```

## Important boundaries

The Wasm engine does **not** decode ZIP archives or images, run scripts from packages, render sprites, handle mouse/touch/keyboard events, or access the network. The JS bridge is **not** an untrusted ZIP validator: callers must first validate packages using the isolated bounded archive reader. Inputs are packed numeric arrays in module-owned memory; the trusted host is responsible for calling allocate/release with matching pointers and counts.

This is an engine milestone toward the [portable delivery contract](PORTABLE_DISTRIBUTION_SECURITY.md), **not** yet a single-file Wasm-powered HTML export, OS-native standalone player, or Unity package. The existing offline HTML exporter currently uses the JavaScript reference runtime; embedding this new Wasm module and testing real offline `file://` interaction are future work.

Do not embed independently executable Wasm bytecode into arbitrary imported `.motionpack` packages. Package assets remain data only; the distributable engine must be release-pinned, trusted and verified separately.
