# Experimental Rust native scene ABI and Unity C# bridge

The Rust library now exposes `mp_scene_sample_v1`, a versioned, synchronous C ABI (Application Binary Interface, binary calling agreement) that accepts **already validated numeric scene data** and writes per-node local and world transforms to a **caller-owned buffer**. This is a foundation for Unity and native runtime adapters, **not yet a complete `.motionpack` player**.

## Source files

- `core/include/motionpack_core.h` defines the C ABI structs, numeric property IDs, buffer ownership and status codes.
- `core/src/ffi.rs` implements bounds/reference validation and calls the integrated Rust scene pose evaluator.
- `adapters/unity/MotionPackNativePoseBridge.cs` is a **source-only** P/Invoke (Platform Invocation, C# native library calling) sample matching the header layouts.
- `tests/test_native_scene_abi.py` calls the actual compiled dynamic library from Python `ctypes` on Windows, macOS and Linux. It tests animated variant/parent transforms, IK, status codes and atomicity of output on failed requests.

## Build

```sh
cargo build --manifest-path core/Cargo.toml --locked --lib
python -m unittest tests.test_native_scene_abi -v
```

Expected native dynamic library artifacts under `core/target/debug/`: Windows `motionpack_core.dll`, macOS `libmotionpack_core.dylib`, Linux `libmotionpack_core.so`. Rust also emits a static library. Copy the target-specific native library into a Unity plugin directory appropriate to the platform and configure the Unity Plugin Inspector. The code is not a Unity package installer and does not package prebuilt binaries in the repository.

## Trust and memory limits

`mp_scene_sample_v1` borrows all caller-supplied input arrays for the duration of one synchronous call; it retains no pointers and allocates a temporary result internally. Output memory is allocated by the caller, and must have capacity at least the node count. On invalid input or failed pose evaluation, output buffers and the returned sampled time are unchanged. The host must pass valid, mapped, appropriately aligned, non-overlapping pointers with accurately declared lengths; Rust cannot validate raw pointer provenance. **Do not use this API to parse untrusted archive bytes.** Continue using the bounded isolated archive reader before constructing numeric arrays.

Variant replacement of image asset IDs, rendering SVG/PNG, effect drawing, Unity event binding, host-side semantic actions and automatic archive import are not implemented in this ABI. The Rust library exports only computational data. The C# source has **not** been compiled or play-tested inside Unity Editor, and no visual or performance guarantee is made.

## Next steps

Implement an importer from validated `.motionpack` archive metadata into the numeric buffer structs; add Unity Editor integration tests, sprite/material mapping, actual renderer binding, and lifecycle/performance evaluation. Only then assess Unity package distribution and self-contained native players.
