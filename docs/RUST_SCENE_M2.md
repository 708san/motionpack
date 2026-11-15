# Rust integrated pose evaluation — milestone 2

**Experimental:** The Rust kernel now combines clip timeline sampling, numeric variant overrides, hierarchical 2D transforms and sequential two-bone inverse kinematics (IK) into a **numeric node pose** for a selected clip/time. It is not yet a standalone `.motionpack` archive reader or renderer.

## Implemented

- `core/src/pose.rs` provides a typed, host-owned `sample_scene` entrypoint returning every node's local transform and world affine matrix.
- Applies numeric variant overrides, scalar animation tracks and parent transforms, then animated IK targets and optional host target overrides. IK chains are processed in order, respecting previous changes.
- Validates numeric inputs, node and chain indices, parenting cycles and non-invertible transformations. The input is already validated structured data, not arbitrary executable content.
- `core/src/bin/scene_probe.rs` is a bounded, fixed-protocol developer fixture tool reading numeric inputs from standard input. It does not decode `.motionpack` archives.
- `tests/rust_scene_parity_test.js` compares integrated Rust output against the JavaScript headless reference across official samples, clips, variants, IK target overrides and loop boundaries, on Windows/macOS/Linux.

## Not implemented yet

Image assets, asset IDs and variants that replace images, SVG/PNG decoding, effects, motion overlays, behavior scheduling and host triggers remain outside Rust. The runtime does not load ZIP/JSON archives, render sprites, or provide a production native/Unity API. The host must continue to use the bounded isolated archive reader for untrusted data.

## Next step

Implement a stable caller-owned-buffer/native C and Wasm interface for compiled, validated scenes; verify lifecycle/memory safety and end-to-end parity before integrating Unity asset loading and actual rendering. Do not infer real-time performance or cross-platform visual parity from numerical comparisons alone.
