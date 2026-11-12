# Candidate Example Asset Rights Inventory

**Status: incomplete; no artwork in this inventory is cleared for redistribution by this document.** This is a repository-side inventory of the current example candidates. It is not a license grant, rights warranty, or approval of the eventual v1.0 distribution set.

Re-audited against GitHub `main` at `10751177b1dc5966f61f1fd4e13d63141f992c37` on 2026-11-12. Compared with the prior audited tree `8ba125adf809c66ab69f4b0c9c3408249ade8f5d`, no tracked visual, package-fixture, screenshot-baseline, or fuzz-corpus paths were added or removed. The interactive seal manifest still references the same eight runtime assets; its source note now records the hand-drawn squash pose and confirms that the retained original remains unchanged. This inventory records repository candidates, not the final release set or any rights clearance. Recheck the frozen release tree and generated artifacts before distribution.

## Manifest-referenced example assets

The paths below come from each example's `manifest.json`. The robot examples store separate files in separate directories, but all ten corresponding SVGs are byte-for-byte identical across both examples and the v0.1/v0.2 package fixtures. This content match does not establish shared authorship, source history, or rights.

| Candidate example | Manifest version | Manifest-referenced runtime assets | Provenance evidence | Rights status |
|---|---:|---|---|---|
| `examples/robot_demo` | 0.1 | `assets/background.svg`, `assets/torso.svg`, `assets/torso_power.svg`, `assets/head.svg`, `assets/arm.svg`, `assets/upper_arm.svg`, `assets/forearm.svg`, `assets/gun.svg`, `assets/core.svg`, `assets/core_power.svg` | No per-example asset authorship or source note located in the audited files. | Author, license/permission, and attribution requirements are unverified. |
| `examples/robot_ik_demo` | 0.2 | `assets/background.svg`, `assets/torso.svg`, `assets/torso_power.svg`, `assets/head.svg`, `assets/arm.svg`, `assets/upper_arm.svg`, `assets/forearm.svg`, `assets/gun.svg`, `assets/core.svg`, `assets/core_power.svg` | [Source note](../examples/robot_ik_demo/source/README.md) describes hand-authored demonstration shapes, editable SVG layers, and the manifest as the authoring source; it says the art is not claimed to be AI-extracted. | Creator identity, license/permission, and attribution requirements remain unverified. |
| `examples/interaction_demo` | 0.4 | `assets/pill.svg` | No per-example asset authorship or source note located in the audited files. | Author, license/permission, and attribution requirements are unverified. |
| `examples/layered_plant_demo` | 0.3 | `assets/foliage.svg`, `assets/pot.svg` | [Source note](../examples/layered_plant_demo/source/README.md) says the original is hand-authored and the two layers were manually separated from it; no AI service or external reference was used. | Authorship method is documented, but creator identity, license/permission, and attribution requirements are unverified. |
| `examples/interactive_seal_demo` | 0.4 | `assets/background.svg`, `assets/shadow.svg`, `assets/flippers.svg`, `assets/body.svg`, `assets/body_squash.svg`, `assets/face.svg`, `assets/face_rest.svg`, `assets/seal_hit.svg` | [Source note](../examples/interactive_seal_demo/source/README.md) says the original is hand-authored, runtime layers are manually separated/derived, and no AI or automated segmentation was used. | Authorship method is documented, but creator identity, license/permission, and attribution requirements are unverified. |

## Related visual files outside the manifests

- `examples/layered_plant_demo/source/plant_original.svg` and `examples/interactive_seal_demo/source/interactive_seal_original.svg` are preserved source illustrations. The normal example packager excludes `source/`; repository/source archive distribution still requires rights review.
- `examples/interactive_seal_demo/assets/static_fallback.svg` is read by the preview generator and embedded in its generated HTML fallback. It is excluded from the `.motionpack` runtime archive by the example's package check, but requires separate rights confirmation if the preview or repository is distributed.
- Four tracked package fixtures contain embedded runtime assets: `tests/fixtures/compatibility_archive_reader/valid_v03.motionpack`, `valid_v04.motionpack`, and `tests/fuzz_corpus/archive_reader/valid_v01.motionpack`, `valid_v02.motionpack`. ZIP member inspection found `manifest.json` plus `assets/background.svg`, `torso.svg`, `torso_power.svg`, `head.svg`, `arm.svg`, `upper_arm.svg`, `forearm.svg`, `gun.svg`, `core.svg`, and `core_power.svg` in each v0.1/v0.2 historical fuzz seed. The ten embedded SVGs are byte-for-byte identical to the matching files in both `examples/robot_demo` and `examples/robot_ik_demo`; the fixtures' generation history and all redistribution rights remain undocumented. The v0.3 fixture contains `manifest.json`, `assets/foliage.svg`, and `assets/pot.svg` from `examples/layered_plant_demo`; the v0.4 fixture contains `manifest.json` and `assets/pill.svg` from `examples/interaction_demo`. Include these embedded assets in rights review if the fixtures ship in a source archive or release.
- Five tracked Playwright screenshot baselines are in `tests/visual.spec.js-snapshots/`: `fire-linux.png`, `form-change-linux.png`, `idle-linux.png`, `pointer-ik-linux.png`, and `transform-linux.png`. They depict captures of robot preview states. Screenshot authorship, license/permission, attribution requirements, and whether the baselines will ship are unverified; the underlying artwork also requires separate clearance.
- Eight tracked SVG fuzz inputs are in `tests/fuzz_corpus/svg_validator/`: `invalid_css_url.svg`, `invalid_doctype.svg`, `invalid_external_reference.svg`, `invalid_missing_dimensions.svg`, `invalid_unknown_attribute.svg`, `malformed_xml.svg`, `valid_gradient.svg`, and `valid_minimal.svg`. These are parser test inputs; their author and reuse status are undocumented. Review them if tests or corpora are distributed.
- Four tracked archive-reader binary fuzz seeds are in `tests/fuzz_corpus/archive_reader/`: `duplicate_asset.seed`, `invalid_manifest.seed`, `not_zip.seed`, and `truncated_eocd.seed`.
- Sixteen tracked raster-header binary fuzz seeds are in `tests/fuzz_corpus/raster_headers/`: `jpeg_bad_segment.seed`, `jpeg_baseline.seed`, `jpeg_progressive.seed`, `jpeg_without_frame.seed`, `png_bad_crc.seed`, `png_truncated.seed`, `png_valid.seed`, `png_zero_dimension.seed`, `webp_animated.seed`, `webp_bad_bounds.seed`, `webp_simple_vp8_over_limit.seed`, `webp_truncated_riff.seed`, `webp_vp8.seed`, `webp_vp8l.seed`, `webp_vp8l_over_dimension_limit.seed`, and `webp_vp8x.seed`.
- The SVG and binary fuzz seeds are parser test inputs, not example artwork. Their creation source and reuse/license status are not separately recorded. If the test corpora ship in a source archive or release, retain them in the rights/provenance review as test data.
- CI screenshot artifacts are generated per workflow run and are not tracked repository files. The visual workflow uploads candidate PNGs, capture metadata, and performance data on every run and retains the artifact for 14 days. The interactive seal review generated 11 candidate captures, including idle/rest, hover, motion states, and a 390×844 viewport. Include this temporary CI hosting in rights review; decide whether to retain or distribute artifacts beyond the workflow's 14-day retention. The example packager does not include them.

## What is not established

- A note saying “hand-authored” or “manually separated” records a provenance claim; by itself it does not identify the rights holder or grant permission to redistribute.
- A repository software license, when selected, must not be assumed to cover artwork, source originals, screenshots, or third-party assets unless the rights holder and license scope explicitly support that treatment.
- The current manifest asset list does not define the final release contents. This inventory covers the five current example candidates only.
- Asset hashes, complete source lineage, contributor declarations, and required attribution notices have not been recorded.

## Closeout requirements

Before including any candidate in a release:

1. Freeze the exact release asset set, including whether repository examples, source originals, fallbacks, screenshots, or test corpora are distributed.
2. For every included file, confirm the creator/rightsholder and the authority to distribute it; record its license or explicit permission and any attribution/notice requirement.
3. Resolve unknown rights by obtaining permission, replacing the asset, or excluding it from the release artifact. Do not infer permission from public repository visibility.
4. Record software license and artwork licensing as separate decisions. Link the selected notices from the release notes and artifact.
5. Re-run the audit against the release-candidate tree and generated `.motionpack`/preview artifacts.

The v1 release gate is tracked in [V1_RELEASE_READINESS.md](V1_RELEASE_READINESS.md). This inventory is evidence of an audit in progress, not evidence that the rights gate has passed.
