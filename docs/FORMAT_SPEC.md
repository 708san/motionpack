# MotionPack format (pre-alpha)

MotionPack is a generic **editable visual-animation format**, independent of game rules and AI vendors. This is an experimental specification, not a finalized standard.

## Editable package

A `.motionpack` is a ZIP archive containing `manifest.json`, referenced runtime images and optional opaque `source/` originals. Generated `preview.html` is an offline browser playback artifact. The repository packager writes only the manifest and its referenced runtime assets; it does not walk the project tree or automatically include unreferenced files or `source/` entries. Runtime asset paths whose first component is `source` (case-insensitive) are reserved and rejected. When validating a local project, the validator and packager reject an asset path containing a filesystem symlink component; this is a local project tree rule, not a ZIP path feature. The packager uses the same bounded asset bytes for validation, the ZIP, and the preview.

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

### Experimental SVG subset

The v0.1/v0.2 validator accepts only static SVG elements in its documented allowlist and either the standard SVG namespace or no namespace. It rejects XML DTDs, entity declarations, processing instructions, foreign namespaces, scripts/event attributes, CSS style attributes, external references and CSS escape/comment syntax. XML nesting (128), element count (10,000), attributes per element (128) and attribute-value size (64 KiB) are bounded by the validator. A `url(#id)` reference is accepted only as the complete value of `fill` or `stroke`, and only when `id` names a gradient in that same SVG document. External URLs and references to other element types are rejected. This narrows some SVGs that older validator versions may have accepted; existing v0.1/v0.2 examples remain supported. These checks do not sanitize SVG for arbitrary renderers or provide a production security boundary.

## Limitations and trust boundary

The sample robot uses rigid SVG pieces. No mesh skinning, automatic background removal, full-body physics, native engine adapters or editor UI are implemented.
The experimental `tools/archive_reader.py` provides bounded, read-only inspection for v0.1/v0.2 ZIP packages. It checks ZIP metadata, reads the manifest and referenced image assets under configured limits, and does not extract arbitrary members. It does not read optional `source/` entries. For paths ending in `.png`, `.jpg`, `.jpeg`, or `.webp` (case-insensitively), the validator and reader inspect only headers for dimensions before decoding. Default tool limits are 8,192 px per edge, 16,000,000 px per raster canvas/image or animation frame, and 64,000,000 px across distinct referenced PNG/JPEG/WebP assets. Animated WebP accounting includes the canvas area plus the width×height area of each frame; each frame header and nested bitstream dimensions are checked, but frame image data is not decoded. Reader limits can be adjusted with `max_raster_*`; existing `max_png_*` settings remain aliases when the corresponding generic setting is omitted. The PNG specification maximum edge of 2^31−1 is always enforced. PNG inspection checks its signature and first IHDR chunk/CRC; JPEG scanning stops at its first frame header and does not support DNL-defined height; WebP uses VP8/VP8L image dimensions or VP8X canvas dimensions. Format selection is based on filename extension; the parsers do not identify content under another supported extension. These checks do not verify full image data or protect a later decoder. Existing v0.1/v0.2 packages above the default tool ceilings may be rejected despite no schema or format-version change. ZIP64 and multi-disk archives are not supported by this reader. This is not a hardened production reader: do not treat untrusted packs as production-safe. The reader limits are tool defaults, not format-wide guarantees.
See `docs/SECURITY_POLICY.md` and `docs/QUALITY_POLICY.md` for follow-up tasks.
