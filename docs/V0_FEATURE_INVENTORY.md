# Experimental v0.1–v0.4 feature inventory

Status: implementation inventory for v1.0 migration planning. This document records the experimental behavior represented by the repository at PR #61 merge commit `7fb362bfe9cf2b4f763898b5ff0669b23f8cb42a`. PR #61 adds an experimental normalized read-only view over the earlier PR #59 snapshot. This inventory is evidence for planning, not a new normative format specification or a backward-compatibility guarantee.

Use [FORMAT_SPEC.md](FORMAT_SPEC.md) for the current stated format rules, [LEGACY_IMPORT_SNAPSHOT.md](LEGACY_IMPORT_SNAPSHOT.md) for the first read-only import API, and the cited validators/tests/fixtures for implementation evidence. “Format rule” below means explicitly documented behavior; “implementation” means current repository behavior; “gap” means the two should not be conflated.

## Version deltas

| Version | Documented addition or rule | Current implementation | Evidence and compatibility note |
|---|---|---|---|
| **v0.1 — base package** | ZIP package with root `manifest.json`; local image assets; canvas; drawable node/layer graph; clips, keyframe tracks, declarative effects, sparse variants and defaults. SVG roots may omit intrinsic dimensions. | Validator and browser Canvas 2D preview implement the shared surface. Tracks support `x`, `y`, `rotation`, `opacity`, and uniform `scale`. Effects are `beam`, `ring`, and `burst`. | Frozen seed: `tests/fuzz_corpus/archive_reader/valid_v01.motionpack`; its SHA-256 is pinned in `tests/test_archive_reader.py`. No claim of a stable v0.1 contract. |
| **v0.2 — two-bone IK** | Adds optional two-bone IK chains and clip IK tracks. A missing IK weight means 1; finite weights are clamped to [0, 1]. SVG roots may still omit dimensions. | Validator, solver, evaluator and browser preview handle two-bone chains and axis tracks. The implementation uses rigid image parts; it does not provide mesh skinning. | Historical seed: `tests/fuzz_corpus/archive_reader/valid_v02.motionpack`; SHA-256 `ffc5bc6c3a4d4531c41c925a70e943dcd111b17b7f674527247079fdd626fbad` is pinned by `tests/test_isolated_archive_reader.py`. IK behavior is also exercised by `tests/ik_test.js`, `tests/runtime_ik_smoke.js`, and the `robot_ik_demo`. |
| **v0.3 — SVG dimension validation profile** | Every referenced SVG root must have positive `width` and `height` in the documented unsigned decimal px syntax; each edge is at most 8,192 px and area at most 16,000,000 px. The requirement does not apply to v0.1/v0.2. This is a validation profile, not a playback capability. | Validator and archive reader require dimensions for v0.3/v0.4. Reader callers can lower the limits but cannot raise the documented maxima. The layered-plant example demonstrates separated source and runtime layers, but source provenance is not a formal v0.3 manifest schema. | Frozen fixture `tests/fixtures/compatibility_archive_reader/valid_v03.motionpack`, SHA-256 `06ad0b8b4b05e8212573784cbdda00a6c8dee9cfe8a9840888feb50cbf6611ea`. Positive/negative dimension cases are in `tests/test_archive_reader.py`. |
| **v0.4 — node interaction** | Adds optional per-node `interaction` booleans `hover`, `tap`, and `click`. Omitted settings/flags are disabled. Events are data-only host notifications; a manifest cannot select an action. | Validator requires interaction settings to use version 0.4. The adapter and generated preview implement mouse/pen hover, primary-touch tap, native mouse/pen click, and a host keyboard activation hook. Hit tests use transformed rectangles, include transparent pixels, omit zero-opacity nodes, and let the top drawable node block input even when interaction is disabled. | Frozen fixture `tests/fixtures/compatibility_archive_reader/valid_v04.motionpack`, SHA-256 `c98a270b566a6792748fc479a63af484fc1c9378d3a4e7c638db96704943bcb8`. Adapter/preview evidence: `tests/interaction_adapter_test.js`, `tests/interaction_preview_smoke.js`, and `docs/FORMAT_SPEC.md`. This does not authenticate user intent or authorize host actions. |

The validator and archive reader recognize versions 0.1–0.4. The generated preview is a browser Canvas 2D implementation; this does not establish cross-browser or engine-renderer conformance.

## Shared behavior and defaults

| Area | Documented/current behavior | Qualification |
|---|---|---|
| Canvas | Logical width/height; validator requires integer dimensions from 1 to 8,192. Background is optional. | Validator ceilings are tool behavior unless the format specification explicitly makes a limit normative. |
| Assets | IDs map to local SVG, PNG, JPEG, or WebP paths. Remote URLs and runtime references into reserved `source/` are rejected. | Raster format selection is extension-based. Header checks do not validate or decode complete image data. |
| Nodes | Parent transforms, optional position, rotation, opacity, scale, width/height, anchor, and Z order. Missing image dimensions use intrinsic size in the preview. | Tool checks cover parent references/cycles and selected finite numeric fields. The full field-level schema and renderer semantics are not fully specified. |
| Clips/tracks | Millisecond timestamps; clip duration is positive and at most 3,600,000 ms in the validator. Track properties are `x`, `y`, `rotation`, `opacity`, and `scale`; key times are ordered, unique, and inside clip duration. Missing `loop` is false; a present value must be boolean. | Interpolation and boundary behavior are implementation details beyond the current brief format description. Independent X/Y scale is not supported. |
| Effects | `beam`, `ring`, `burst`; timed declarative effects attached to nodes. Burst count defaults to 28 in current validation/runtime. | Not executable actions. Several visual effect parameters have implementation defaults that are not exhaustively specified as format rules. |
| IK | Optional two-bone chain declarations and IK axis tracks. Missing weight and bend behave as 1 in current validator/runtime; weight is clamped by the runtime. | The format spec introduces IK in v0.2, but validator/runtime do not gate `iks` or `ik_tracks` by version. Therefore a v0.1 manifest can currently contain IK constructs. This is an implementation/spec mismatch; do not silently reinterpret or discard such data during migration. A maintainer decision is required before changing acceptance. |
| Interaction | A node’s omitted interaction flags are disabled; host receives events and chooses any action. | Runtime hit testing is rectangular, not alpha-aware. Events are not proof of trusted activation. |
| Sparse data/unknown fields | The v1 read-only importer retains original manifest bytes and parsed data; it reports unrecognized top-level fields. | Current validation is generally permissive for unrecognized manifest/node fields (with explicit checks such as interaction flags). Nested unknown fields are preserved but not semantically classified. This is not a forward-compatibility guarantee. |

## Cross-version validation and tool limits

These checks are shared tooling behavior, not version deltas unless stated above:

- **SVG subset:** the current static element/attribute allowlist, standard SVG namespace or no namespace, same-document gradient references, and bounded XML structure apply across v0.1–v0.4. The allowlist can reject SVG content earlier validator revisions accepted; this is a cross-version compatibility restriction. It does not certify behavior for arbitrary renderers.
- **Raster headers:** PNG/JPEG/WebP dimensions are inspected by filename extension. Default limits are 8,192 px per edge, 16 MP per image/frame and 64 MP across referenced raster assets; animated WebP accounting includes canvas and frame areas. Complete pixel decoding is outside the validator/ZIP reader.
- **Reader resource limits:** defaults include 40 MiB archive size, 1,024 entries, 40 MiB aggregate uncompressed data, 100:1 compression ratio, 1 MiB manifest, 12 MiB per asset and 32 MiB aggregate referenced assets. These are reader/validator operating limits, not a format-wide compatibility promise.
- **Source/provenance:** the package format permits optional opaque `source/` originals, but the packager does not automatically include them. The normal readers do not return them. The explicit v1 read-only legacy import snapshot and normalized model retain regular-file payloads including `source/` as opaque bytes; they do not decode, scan, execute or restore ZIP container metadata. No formal source-provenance manifest schema is defined.

## Fixture and test map

| Version | Regression artifact | Direct/isolated import evidence |
|---|---|---|
| v0.1 | `tests/fuzz_corpus/archive_reader/valid_v01.motionpack` (SHA-pinned) | `tests/test_archive_reader.py`, `tests/test_isolated_archive_reader.py`, `tests/test_legacy_importer.py` |
| v0.2 | `tests/fuzz_corpus/archive_reader/valid_v02.motionpack` (SHA-pinned in `tests/test_isolated_archive_reader.py`) | `tests/test_isolated_archive_reader.py`, `tests/test_legacy_importer.py`; IK runtime: `tests/ik_test.js`, `tests/runtime_ik_smoke.js` |
| v0.3 | `tests/fixtures/compatibility_archive_reader/valid_v03.motionpack` (SHA-pinned) | `tests/test_archive_reader.py`, `tests/test_isolated_archive_reader.py`, `tests/test_legacy_importer.py` |
| v0.4 | `tests/fixtures/compatibility_archive_reader/valid_v04.motionpack` (SHA-pinned) | `tests/test_archive_reader.py`, `tests/test_isolated_archive_reader.py`, `tests/test_legacy_importer.py`; interactions: `tests/interaction_adapter_test.js`, `tests/interaction_preview_smoke.js` |

The repository-wide Python suite and isolated-reader OS matrix establish regression evidence for the current implementation. They do not establish naturally convincing motion, full SVG safety, broad renderer parity, or compatibility with external packages not represented by these artifacts.

## Open v1.0 work informed by this inventory

1. Define a complete v1 schema and decide which legacy implementation quirks are preserved, rejected with migration guidance, or reported as unsupported.
2. Specify the immutable read-only snapshot’s mapping into a v1 normalized model before adding any v1 serializer.
3. Expand fixture coverage for version-specific defaults, malformed inputs, unknown core data, and semantic round trips. Keep all four fixture checksums pinned and update them only after explicit compatibility review.
4. Define the reader conformance/resource profiles, supported renderer/device matrix, and release gates separately from the experimental v0.x format rules.

Do not treat this inventory as a v1 schema decision or as evidence that the experimental v0.x formats are stable.
