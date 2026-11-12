# v1 Contract Proposal (Non-Normative)

Status: discussion draft for Issue #120. This document is not a format specification, compatibility promise, implementation requirement, or maintainer decision. Nothing here freezes v1.0. Promote a decision into `FORMAT_SPEC.md` only after maintainer approval and Architect review.

## Goal and boundary

Issue #120 targets a stable v1 format, an integrated reader/validator, and a writer that reports conversion losses and requires explicit confirmation before a lossy save. GUI and AI authoring are outside this core scope.

The repository currently has experimental v0.1–v0.4 packages, a read-only legacy importer, and a manifest-only v1 capability preflight prototype. It has no v1 schema, integrated v1 package reader, or v1 writer. The importer’s normalized model is an experimental view, not a proposed final schema.

This proposal records evidence and decision points so the contract can be completed without silently changing legacy meaning.

## Constraints already approved

These directions were agreed before this draft:

- Keep the read-only importer for v0.1–v0.4 and preserve original manifest bytes, opaque source data, sparse field presence, and provenance.
- Keep authored sparse values distinct from effective values; every effective default carries its source and rule provenance.
- Preserve ambiguous data, including v0.1 IK, with a warning and without assigning it new meaning.
- A write that may lose information must report the loss before output. Confirmation is tied to the exact source and conversion plan; a changed source or plan invalidates it.
- Proposed capability declaration uses `capabilities.required[]` and `capabilities.optional[]`; extension keys use reverse-domain names. Unknown required capabilities and unknown core fields fail safely. Unknown optional capabilities may be ignored only under an explicit safe-ignore rule. Opaque extension data is retained.
- v1.0 core does not include a GUI or AI authoring service.

These are constraints for contract work, not evidence that the final schema or writer already exists.

## Maintainer decisions still open

### 1. v1 core data shapes

**Option A — retain v0.4-shaped core fields (recommended by the planning review).** Define v1 semantics precisely while reusing familiar concepts and field shapes. Migration can map only explicitly supported meanings; fields without a confirmed mapping remain preserved or are reported as unsupported/lossy. This reduces structural change but does not make every v0.x field automatically portable.

**Option B — redesign the core schema.** This permits a cleaner model but requires explicit mappings from each v0.x field, fixture updates, and more potentially lossy conversions. Existing readers and tools cannot infer the new semantics from shape similarity.

Either option needs a closed v1 core-field inventory, JSON types/ranges, reference rules, ordering, and unknown-field behavior.

### 2. SVG root dimensions

**Option A — require positive numeric px `width` and `height` in v1 (recommended by the planning review).** This aligns with the v0.3/v0.4 validation profile and permits bounded intrinsic sizing. Existing v0.1/v0.2 packages can contain dimensionless SVGs, so migration must not silently infer dimensions; each such asset needs an explicit repair or a loss/unsupported disposition.

**Option B — allow omitted dimensions.** This is more permissive for older content, but the contract must specify how a renderer obtains intrinsic size and how resource limits apply when dimensions are absent. Renderer-dependent interpretation should not be mistaken for deterministic sizing.

If dimensions are required, choose whether v1 adopts the existing v0.3 ceilings (8,192 px per edge and 16 MP) or a separately justified limit. Those ceilings currently describe a validation profile, not an engine-independent v1 guarantee.

### 3. Canonicalization and package reproducibility

**Option A — guarantee canonical manifest bytes only (recommended by the planning review).** Define UTF-8, JSON normalization, key ordering, number representation, and newline policy. ZIP files may differ in entry order, timestamps, permissions, compression implementation, comments, and extra fields. This is simpler to implement and test, but whole-package hashes are not stable across writers.

**Option B — guarantee deterministic ZIP bytes too.** In addition to canonical manifest bytes, define entry ordering, timestamps, permissions, compression method and parameters, comments, extra fields, directory entries, and all container metadata. Every conforming writer must reproduce these details; fixtures must pin byte-level output. This gives package-level stable hashes but constrains implementations and compression choices.

For either option, specify which files belong in the runtime package, how optional `source/` originals are handled, and whether unknown regular-file entries are rejected, retained opaquely, or reported as loss. The current importer preserves regular-file payload bytes, including opaque `source/`, but not ZIP metadata, directory-only entries, or container layout.

## Evidence-based legacy migration inventory

This is a preliminary planning matrix, not a v1 mapping. “Confirmed view” means the current experimental importer exposes the source fact; it does not mean v1 accepts or interprets it. “Open” means no target disposition is approved.

| Source | Confirmed source evidence | v1 disposition |
|---|---|---|
| v0.1 | Canvas, assets, nodes, clips, tracks, declarative effects, variants/defaults; SVG dimensions may be omitted. | Map only fields whose v1 semantics are approved. Preserve source bytes and sparse presence. Unknown nested fields are not fully classified. SVG dimensionless assets depend on the pending dimensions choice. |
| v0.2 | Adds two-bone IK; missing IK `weight` is specified as 1. Runtime also observes omitted `bend` as 1, but the format does not specify this. | IK mapping and default provenance need explicit v1 semantics. The observed bend default must not become normative by inference. |
| v0.3 | Adds the SVG dimension validation profile: positive numeric px dimensions, edge up to 8,192 px, area up to 16 MP. | Apply only if the v1 dimensions decision adopts these rules; the existing tool ceiling is not yet a v1 guarantee. |
| v0.4 | Adds per-node `hover`, `tap`, and `click` booleans; omitted flags are disabled; notifications are data-only. | Define whether v1 adopts the current preview’s detailed pointer, hit-test, occlusion, and event semantics or only stores declarations. Cross-renderer behavior is not established. |

Across all versions, the importer currently keeps original manifest bytes and retained regular-file payloads, while its normalized projection only reports confirmed mappings. Unrecognized top-level fields are reported unsupported by that projection; nested unknown fields are generally preserved but unclassified. v0.1 IK is preserved and warned as a specification/implementation mismatch, not interpreted as a v1 capability. These importer behaviors do not decide the future writer’s output policy.

The experimental effective-default view currently reports: clip `loop=false` for v0.1–v0.4; IK `weight=1` for v0.2–v0.4; IK `bend=1` as an implementation observation for v0.2–v0.4; burst `count=28` as an implementation observation for v0.1–v0.4 when absent; and v0.4 interaction flags as disabled when absent. These are source-version facts with provenance. They are not automatically v1 defaults, and authored values remain distinct from omitted values.

## Contract decisions required beyond the three choices

Before implementation is called conformant, the normative contract still needs decisions for:

- Complete v1 core fields, types, ranges, reference integrity, collection ordering, and which objects have closed field sets.
- Time units, keyframe ordering/boundaries/interpolation, clip looping, transform/anchor/Z behavior, variants, and declarative-effect parameters.
- Whether interaction is only stored data or includes any cross-renderer event/hit-test guarantee.
- Capability identifier grammar, required/optional declaration rules, capability registry ownership, and the exact safe-ignore rule for each optional capability.
- Extension value shape and byte-preserving representation.
- Runtime asset versus opaque source payload boundaries, unknown archive-entry policy, and reader validation/resource-limit profile.
- Stable error categories and which validation failures occur before any asset payload is read.
- Loss report schema, source pointer/payload identity, conversion action, confirmation token inputs, and no-output behavior on unconfirmed loss.

Do not classify permissively accepted v0 nested fields as invalid merely because their v1 mapping is not yet known.

## Proposed work sequence

1. Record maintainer choices for the three decisions above and any additional semantic decisions.
2. Have the Architect review the resulting normative schema and migration rules.
3. Update `FORMAT_SPEC.md` and add normative fixtures/conformance cases for v1, including unknown required/core fields, explicitly safe optional capabilities, opaque extensions, canonicalization, loss confirmation, and round trips.
4. Implement manifest-first v1 validation/reading and integrate the capability preflight before referenced asset reads.
5. Implement the writer only against the frozen reader/schema. Produce a deterministic loss report before output and invalidate confirmation when source or plan identity changes.
6. Demonstrate v0.1–v0.4 regression coverage, v1 round trips, and that unconfirmed lossy saves produce no output and do not mutate input.

### Acceptance criteria for this proposal milestone

- This draft remains explicitly non-normative and keeps pending maintainer choices visible.
- The migration inventory distinguishes importer observations from v1 decisions.
- No legacy package acceptance or interpretation changes.
- Issue #120 remains open until its contract and implementation acceptance criteria are met.

### Rollback

Revert this proposal document if its recommendations are rejected. No source package, format rule, reader, or writer is changed by this draft.
