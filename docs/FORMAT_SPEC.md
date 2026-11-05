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

The v0.1/v0.2 validator accepts only static SVG elements in its documented allowlist and either the standard SVG namespace or no namespace. Attribute names are case-sensitive and restricted by element as follows; attributes not listed here are rejected:

| Element | Accepted attributes |
|---|---|
| `svg` | `width`, `height`, `viewBox` |
| `g` | none |
| `path` | `d`, plus the paint attributes below |
| `rect` | `x`, `y`, `width`, `height`, `rx`, `ry`, plus the paint attributes below |
| `circle` | `cx`, `cy`, `r`, plus the paint attributes below |
| `ellipse` | `cx`, `cy`, `rx`, `ry`, plus the paint attributes below |
| `line` | `x1`, `y1`, `x2`, `y2`, `stroke`, `stroke-width`, `opacity` |
| `polyline`, `polygon` | `points`, plus the paint attributes below |
| `defs` | none |
| `linearGradient`, `radialGradient` | `id` |
| `stop` | `offset`, `stop-color` |

The paint attributes are `fill`, `stroke`, `stroke-width`, and `opacity`. `id` is accepted only on gradient elements. Attribute values are not comprehensively validated against every SVG value grammar; the existing size and URL checks still apply. XML DTDs, entity declarations, processing instructions, foreign namespaces, scripts/event attributes, CSS style attributes, external references and CSS escape/comment syntax are rejected. XML nesting (128), element count (10,000), attributes per element (128) and attribute-value size (64 KiB) are bounded by the validator. A `url(#id)` reference is accepted only as the complete value of `fill` or `stroke`, and only when `id` names a gradient in that same SVG document. External URLs and references to other element types are rejected. This validator update narrows some SVGs that earlier validator versions may have accepted, without changing the v0.1/v0.2 manifest versions; existing repository fixtures remain supported. A v0.1/v0.2 asset using an attribute outside this table must be revalidated and have that attribute removed or converted to a supported form. Preserve the original SVG and its provenance when making such edits; external legacy assets have not been inventoried. These checks do not sanitize SVG for arbitrary renderers or provide a production security boundary.

The current SVG rendering profile is the generated offline `preview.html`: it embeds each referenced asset as a data URL, loads it through the browser's `HTMLImageElement` (`new Image()`), and draws it with the Canvas 2D API. This describes the implementation path, not a certified browser or version support matrix. The project has no browser conformance matrix, does not promise pixel-identical output across browsers, and does not guarantee that every SVG accepted by the validator renders identically in every browser. Other MotionPack runtimes may support different SVG subsets. Loading SVG as an image does not sanitize or isolate the browser's SVG parser, bound rendering CPU or memory, or make the validator's acceptance a security approval for another renderer.

## Limitations and trust boundary

The sample robot uses rigid SVG pieces. No mesh skinning, automatic background removal, full-body physics, native engine adapters or editor UI are implemented.
The experimental `tools/archive_reader.py` provides bounded, read-only inspection for v0.1/v0.2 ZIP packages. It checks ZIP metadata, reads the manifest and referenced image assets under configured limits, and does not extract arbitrary members. It does not read optional `source/` entries. Before opening its input path, it checks that the path resolves to a regular file and verifies the opened descriptor; it uses `O_NONBLOCK` where the operating system exposes that flag. The path check and open are not atomic. A concurrent replacement can still open a special file before descriptor rejection. On platforms without `O_NONBLOCK` that support blocking special-file types, a replaced path may block during open. Windows behavior has not been tested. The reader is not a safe boundary for attacker-mutable input paths. For paths ending in `.png`, `.jpg`, `.jpeg`, or `.webp` (case-insensitively), the validator and reader inspect only headers for dimensions before decoding. Default tool limits are 8,192 px per edge, 16,000,000 px per raster canvas/image or animation frame, and 64,000,000 px across distinct referenced PNG/JPEG/WebP assets. Animated WebP accounting includes the canvas area plus the width×height area of each frame; each frame header and nested bitstream dimensions are checked, but frame image data is not decoded. Reader limits can be adjusted with `max_raster_*`; existing `max_png_*` settings remain aliases when the corresponding generic setting is omitted. The PNG specification maximum edge of 2^31−1 is always enforced. PNG inspection checks its signature and first IHDR chunk/CRC; JPEG scanning stops at its first frame header and does not support DNL-defined height; WebP uses VP8/VP8L image dimensions or VP8X canvas dimensions. Format selection is based on filename extension; the parsers do not identify content under another supported extension. These checks do not verify full image data or protect a later decoder. Existing v0.1/v0.2 packages above the default tool ceilings may be rejected despite no schema or format-version change. ZIP64 and multi-disk archives are not supported by this reader. This is not a hardened production reader: do not treat untrusted packs as production-safe. The reader limits are tool defaults, not format-wide guarantees.

The separate opt-in `tools/isolated_archive_reader.py` API does not change the `.motionpack` contract or `read_package()` behavior. It snapshots an input up to 40 MiB inside a fresh worker, applies a caller-selected deadline (maximum 300 seconds) to worker completion, bounds its binary response to 40 MiB, and terminates/reaps the worker on timeout or protocol failure. Process creation and OS job setup are synchronous and cannot themselves be interrupted by the deadline; their elapsed time is deducted before waiting for worker completion. Linux defaults to a 512 MiB address-space ceiling, Windows to a 512 MiB committed-memory Job Object limit, and macOS has no hard whole-process memory cap in this implementation. The worker is not a sandbox and keeps the caller account's OS permissions. See `SECURITY.md` for details.
See `docs/SECURITY_POLICY.md` and `docs/QUALITY_POLICY.md` for follow-up tasks.
