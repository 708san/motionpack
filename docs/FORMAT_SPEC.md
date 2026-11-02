# MotionPack format (pre-alpha)

MotionPack is a generic **editable visual-animation format**, independent of game rules and AI vendors. This is an experimental specification, not a finalized standard.

## Editable package

A `.motionpack` is a ZIP archive containing `manifest.json`, referenced `assets/` images and optional `source/` originals. Generated `preview.html` is an offline browser playback artifact.

## Manifest and runtime surface

- `format` must equal `motionpack`; `version` is `0.1` or `0.2`.
- `canvas` has logical pixel width, height and optional background.
- `assets` maps IDs to local SVG/PNG/JPEG/WebP image paths; no executable scripts or remote images.
- `nodes` describe image layers, parent IDs, anchor, transform, dimensions, opacity and Z-order.
- `clips` supply duration, looping, keyframe tracks, timed declarative effects and optional IK tracks.
- `variants` store sparse visual node overrides; `defaults` choose initial clip and variant.
- Version `0.2` adds optional `iks`: two-bone chains with lengths, target, bend and blend weight.
- Effect primitives supported: beam, ring and burst. Track properties: x, y, scale, rotation, opacity.

Timeline values are in milliseconds. Rendering uses timestamp sampling. Visual effects do not define gameplay effects or results.

## Limitations and trust boundary

The sample robot uses rigid SVG pieces. No mesh skinning, automatic background removal, full-body physics, native engine adapters or editor UI are implemented.
The validator provides basic defensive checks, but no hardened reader for arbitrary downloaded `.motionpack` archives exists. Do not treat untrusted packs as production-safe or automatically extract arbitrary ZIP members.
See `docs/SECURITY_POLICY.md` and `docs/QUALITY_POLICY.md` for follow-up tasks.
