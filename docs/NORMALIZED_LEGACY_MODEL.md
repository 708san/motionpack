# Normalized read-only legacy model (experimental)

Status: implemented experimental internal importer API, merged in PR #61 (2026-11-09). This remains a read-only migration aid, not a stable public contract. This is not the v1.0 manifest schema, a renderer API, or a serialization contract.

## Decision and purpose

The importer returns the existing immutable `LegacyImportSnapshot` and adds an immutable `normalized` view for v0.1–v0.4. The snapshot remains the source of truth: exact manifest bytes and every retained regular-file payload are preserved alongside the normalized view.

A normalized view gives tools stable access to shared package concepts without rewriting or completing the legacy manifest. It does not write, convert, render, execute, or decode package contents.

## Model shape

The normalized package exposes:

- Source format/version, identifier, and a canvas view with a pointer when present. Defaults likewise retain presence and the `/defaults` source pointer when present.
- Runtime assets keyed by legacy asset ID, retaining original path and immutable bytes.
- Nodes in manifest declaration order. Each node exposes ID, optional asset/parent references, its source manifest pointer, the original field-presence set, and an immutable mapping of remaining authored fields.
- Clips keyed by name. Each clip exposes duration, whether `loop` was present and its value when present, tracks, IK tracks, effects, the source pointer, and authored fields.
- Variants and defaults as immutable sparse views with source pointers. Omitted fields stay omitted.
- IK chains and per-node interaction data only when present in source content.
- Capability facts and diagnostics distinct from package payloads.
- The snapshot report's experimental `migration_findings` record only confirmed source-to-normalized-view mappings. v0.1 IK mismatches are marked `preserved_uninterpreted`; unrecognized top-level fields are separately `unsupported` by this normalized view and remain in the original manifest. These categories do not claim v1 semantics, runtime support, or a stable public API. Unclassified nested fields remain preserved and reported by the existing diagnostic.
- The snapshot report's immutable `source_facts`, which record source-version facts, observed IK or interaction declarations, version/spec mismatches, and validation-profile facts with source JSON Pointers. These are not target-v1 capability or runtime-support claims.

Field-presence information is preserved so explicit values remain distinguishable from absent fields. Defaults are not materialized into the original manifest or sparse normalized source view. The separate immutable `effective_defaults` view exposes provenance-bearing values keyed by JSON Pointer: omitted clip `loop` is `false` for v0.1–v0.4 under `motionpack.v0.clip.loop.default-false`; omitted IK chain `weight` is `1` for v0.2–v0.4 under `motionpack.v0.2.ik.weight.default-one`; omitted IK chain `bend` is observed as `1` for v0.2–v0.4 under `motionpack.v0.2.ik.bend.default-one`; omitted burst effect `count` is observed as `28` across v0.1–v0.4 under `motionpack.v0.effect.burst.count.default-28`; and omitted v0.4 node interaction flags (`hover`, `tap`, `click`) are `false` under `motionpack.v0.4.interaction.flag.default-disabled`. Each record includes source version and pointer and confirms the source field was absent. The loop, weight, and interaction rules originate in `FORMAT_SPEC.md`; bend and burst count are observed implementation defaults and are not format-spec or v1 semantic guarantees. The burst projection applies only when `count` is absent; authored values, including zero, remain sparse. The current browser preview defaults the burst count only when the field is absent (`fx.count ?? 28`); authored `count: 0` draws no particles, covered by `tests/runtime_smoke.js`. This is observed renderer behavior, not a v1 semantic guarantee. Explicit interaction and IK fields remain authored and are not duplicated. Interaction defaults are not inferred for v0.1–v0.3; v0.1 IK remains preserved and reported with its version/spec mismatch diagnostic, without an inferred weight or bend. No other defaults are inferred. These are experimental importer projections, not a v1 schema or serializer contract.

Unknown or unclassified fields remain recoverable from the immutable original parsed manifest and raw manifest bytes. The normalized view may report them as preserved and uninterpreted; it must not drop them.

## Current v0.1 IK importer behavior (observed; not v1 migration semantics)

This section documents the current experimental importer API only. The maintainer-approved v1 migration policy (2026-11-10) preserves v0.1 IK records, warns about the v0.2 specification mismatch, and leaves the construct uninterpreted for v1. It does not alter this importer or runtime.

If a v0.1 manifest contains IK declarations or IK tracks, normalize and report them according to the current validator/runtime behavior. Also attach a diagnostic that the format specification introduces IK in v0.2 while the current implementation does not gate those fields by version. Do not change the source version, rewrite the manifest, or claim this implementation quirk is a stable v0.1 format guarantee.

Capabilities remain facts inferred from observed content, not claims that every runtime supports the feature. The existing identifier `org.motionpack.ik.two-bone` is reported when IK declarations/tracks exist, including the v0.1 mismatch case, with the source location and compatibility diagnostic.

## Resource and preservation boundary

The normalized view references the payload bytes already retained by the isolated reader; it does not decompress or parse payloads a second time. Entry, archive, expanded-size, compression-ratio and isolated-response limits remain unchanged. Source payloads stay opaque and separate from runtime assets. ZIP compression representation, timestamps, comments, extra fields, directory-only entries and container ordering remain unavailable.

If normalization fails, no partial result is returned. The input archive remains unchanged. All normalized mappings and nested values are immutable.

## Acceptance criteria

- Normalize all v0.1–v0.4 regression fixtures and preserve declaration order, source locations, sparse presence, ID references, capabilities and validation profiles.
- In v0.1 IK-bearing test input, preserve and normalize IK according to current implementation behavior, report the v0.2-spec mismatch as `preserved_uninterpreted` for v1, and retain the original manifest bytes unchanged.
- Verify v0.2 and later IK facts, v0.4 interaction views, and v0.3/v0.4 SVG validation profile facts.
- Verify opaque source and unreferenced payloads remain byte-identical and separate from runtime assets.
- Verify deep immutability, deterministic views, successful and failed import input integrity, and existing reader compatibility.
- Run the full repository checks and report exact results.

## Scope exclusions

No v1 manifest/schema, writer, converter, renderer, automatic default materialization, SVG/raster decoding, external asset inventory, or change to legacy package acceptance is included.

## Rollback

Revert the normalized view, documentation and tests. The existing `LegacyImportSnapshot` remains available and no files or packages are migrated.
