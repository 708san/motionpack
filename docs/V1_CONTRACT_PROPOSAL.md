# v1 Contract Proposal (Non-Normative)

Status: non-normative discussion draft for Issue #120. This document is not a format specification, compatibility promise, or implementation requirement. It records maintainer-approved directions D1–D3 and the additional package, feature-scope, extension, error, and compatibility choices below, but does not freeze v1.0. Promote normative rules into `FORMAT_SPEC.md` only after the remaining maintainer decisions and Architect review.

## Goal and boundary

Issue #120 targets a stable v1 format, an integrated reader/validator, and a writer that reports conversion losses and requires explicit confirmation before a lossy save. GUI and AI authoring are outside this core scope.

The repository currently has experimental v0.1–v0.4 packages, a read-only legacy importer, and a manifest-only v1 capability preflight prototype. It has no v1 schema, integrated v1 package reader, or v1 writer. The importer’s normalized model is an experimental view, not a proposed final schema.

This proposal records evidence and decision points so the contract can be completed without silently changing legacy meaning.

## Constraints already approved

These directions were agreed before this draft:

- Keep the read-only importer for v0.1–v0.4 and preserve original manifest bytes, opaque source data, sparse field presence, and provenance.
- Keep authored sparse values distinct from effective values; every effective default carries its source and rule provenance.
- Preserve ambiguous data, including v0.1 IK, with a warning and without assigning it new meaning.
- A write that may lose information must report the loss before output. Per the maintainer decision recorded during v1 migration planning (2026-11-10), confirmation is tied to the exact source and conversion plan; a changed source or plan invalidates it.
- Proposed capability declaration uses `capabilities.required[]` and `capabilities.optional[]`; extension keys use reverse-domain names. The maintainer selected the identifier strings `org.motionpack.ik.two-bone` and `org.motionpack.interaction` for the IK and interaction capability families. Unknown required capabilities and unknown core fields fail safely. Unknown optional capabilities may be ignored only under an explicit safe-ignore rule. Opaque extension data is retained. The selected names do not settle capability grammar, registry/ownership, declaration/derivation rules, or imply that the v1 runtime implements these features.
- v1.0 core does not include a GUI or AI authoring service.

These are constraints for contract work, not evidence that the final schema or writer already exists.

## Contract-freeze and implementation blockers

The maintainer has recorded D1–D3 and the additional directions below. Normative field semantics, precise limits, canonicalization rules, and conformance details listed later still block freezing the v1 contract and starting conformant reader/writer implementation. See [Issue #120](https://github.com/708san/motionpack/issues/120) for the authoritative acceptance criteria, including loss reporting, no output on unconfirmed loss, canonicalization, and v0.1–v0.4 regression coverage.

## Maintainer decisions recorded

### 1. v1 core data shapes

**Approved option A — retain v0.4-shaped core fields.** Define v1 semantics precisely while reusing familiar concepts and field shapes. Migration can map only explicitly supported meanings; fields without a confirmed mapping remain preserved or are reported as unsupported/lossy. This reduces structural change but does not make every v0.x field automatically portable.

**Option B — redesign the core schema.** This permits a cleaner model but requires explicit mappings from each v0.x field, fixture updates, and more potentially lossy conversions. Existing readers and tools cannot infer the new semantics from shape similarity.

The chosen direction still needs a closed v1 core-field inventory, JSON types/ranges, reference rules, ordering, and unknown-field behavior.

### 2. SVG root dimensions

**Approved option A — require positive numeric px `width` and `height`, with a maximum edge of 8,192 px and an area of 16 MP per SVG.** This adopts the v0.3/v0.4 dimension profile for v1 and permits bounded intrinsic sizing. Existing v0.1/v0.2 packages can contain dimensionless SVGs, so migration must not silently infer dimensions; each such asset needs an explicit repair or a loss/unsupported disposition.

**Option B — allow omitted dimensions.** This is more permissive for older content, but the contract must specify how a renderer obtains intrinsic size and how resource limits apply when dimensions are absent. Renderer-dependent interpretation should not be mistaken for deterministic sizing.

The maintainer explicitly adopted the existing 8,192 px per-edge and 16 MP per-SVG ceilings as v1 format limits. Any lower host/tool resource limit remains a separate implementation profile and cannot relax the v1 validity rule.

### 3. Canonicalization and package reproducibility

**Option A — guarantee canonical manifest bytes only.** Define UTF-8, JSON normalization, key ordering, number representation, and newline policy. ZIP files may differ in entry order, timestamps, permissions, compression implementation, comments, and extra fields. Whole-package hashes are not stable across writers.

**Approved option B — guarantee canonical manifest bytes and deterministic complete ZIP bytes.** In addition to canonical manifest bytes, the normative profile must define entry ordering, timestamps, permissions, compression method and parameters, comments, extra fields, directory entries, and all container metadata. Every conforming writer must reproduce these details; fixtures must pin byte-level output. This gives package-level stable hashes and constrains implementations and compression choices.

The maintainer selected package-envelope direction A: allow manifest-referenced runtime assets and preserve bounded opaque payload bytes under `source/` and for unknown regular-file entries. Input ZIP metadata is not part of the preservation promise. This is distinct from D3: a conforming writer must still emit deterministic ZIP metadata according to a yet-to-be-frozen profile. Exact per-entry and aggregate bounds, entry-name/path rules, and how preserved opaque entries interact with canonical output remain to be specified.


The maintainer also approved these directions for Issue #120. They guide the proposal but are not yet normative contract text:

- **Package envelope:** allow manifest-referenced runtime assets; preserve bounded opaque payloads in `source/` and unknown regular-file entries. Input ZIP metadata is not preserved. Exact size/count/path bounds and how opaque entries are deterministically emitted remain open.
- **Feature scope:** define v1 meanings for the full v0.4 feature surface. This approves the scope, not the individual field rules or cross-renderer behavior; those remain subject to specification and Architect review.
- **Extensions:** represent extension values as JSON values, preserve their semantic values, and canonicalize them. Exact canonical JSON rules and extension-key/schema constraints remain to be frozen.
- **Reader/writer failures:** use staged validation, stable error categories, and produce no output on failure. The stage order and exact public category identifiers remain open.
- **Compatibility lifecycle:** support stable v1 and keep the v0.x importer read-only, with no time-based support-duration promise. This does not promise legacy write-back or define platform/API support windows.


## S3 approved node evaluation directions (planning record)

The maintainer approved these v1 directions, reusing current preview behavior where stated. They are planning decisions and require normative rules, fixtures, and Architect review before they become part of `FORMAT_SPEC.md`:

- Apply each node's transform in its parent-local coordinate system and compose parent transforms from the root toward the node.
- Preserve sparse authored fields while exposing effective defaults with provenance. Effective defaults: `x=0`, `y=0`, `rotation=0` degrees, `scale=1`, `opacity=1`, and normalized `anchor=[0.5,0.5]`. If drawable-node `width` or `height` is omitted, use the referenced image's intrinsic dimension for that axis.
- Draw all drawable nodes in ascending global `z`; omitted `z` is effective `0`. For equal `z`, preserve manifest declaration order, so later-declared nodes draw in front.
- A drawable node's opacity applies to that node only; parent opacity is not inherited by descendants.

Still open: numeric domains and invalid-value behavior for transforms, opacity and `z`; whether negative scale is supported; reference/graph boundary rules beyond the existing acyclic-parent checks; and cross-renderer pixel equivalence. Existing runtime behavior is evidence, not a promise of identical pixels.


## S4 approved timeline and track directions (planning record)

The maintainer approved these v1 sampling rules. They do not define host scheduling APIs or claim pixel-identical rendering:

- Use milliseconds for clip duration and key times. Duration is a positive integer; key times are finite numbers in the inclusive range `[0, duration_ms]`, strictly increasing with no duplicates, and key values are finite numbers. Property-specific accepted ranges remain open.
- Between adjacent keys at times `t0` and `t1` with values `v0` and `v1`, compute `u=(t-t0)/(t1-t0)`, then sample `v=v0+(v1-v0)*u*u*(3-2*u)`. Apply this smoothstep rule to every animated numeric property, including rotation as ordinary scalar interpolation. Do not add a per-track or per-segment interpolation selector in this v1 shape.
- Before the first key and after the last key, hold the nearest endpoint value.
- For a looping clip, sample time `duration_ms` as time zero. For a non-looping clip, sample and hold the final pose at `duration_ms`.
- A host player owns `ended` notifications and decisions about what clip to play next; those are not package sampling semantics.

- Every track must contain at least one key; an empty `keys` array is invalid.
- When `loop` is omitted, its effective v1 value is `false`; preserve the authored omission separately from the effective value.
- A requested sample time must be finite and nonnegative. For looping clips, normalize it modulo `duration_ms` into `[0, duration_ms)`; for non-looping clips, clamp values above duration to `duration_ms`. Exact duration on a looping clip therefore samples time zero; negative values are invalid.

Still open: maximum v1 clip duration, precision/representation limits for fractional-millisecond key times, property-specific numeric ranges and invalid-value behavior, and interaction with effect/IK sampling limits. These choices establish a sampling contract, not wall-clock scheduling or renderer pixel equivalence.

## S5 approved variant and effect directions (planning record)

The maintainer approved these limited v1 directions. They do not change v0.x behavior or define the full v1 schema:

- If a selected variant and a clip track specify the same node property, the variant wins. The current evaluator applies the variant before tracks, so v1 must preserve the approved precedence without silently changing legacy behavior.
- Effect `offset` is node-local and transformed through the node's world transform. Beam `target` and ring/burst `radius` use canvas logical coordinates and are not scaled by the source node transform, matching the current preview's coordinate split.

Still open: the variant overlay field set, omitted-field/default behavior, merge rules, and precedence against IK or other evaluation stages; effect field grammar, units, parameter ranges/defaults, timing and renderer appearance; and cross-renderer conformance. These directions do not promise pixel-identical output.

## Remaining normative contract blockers

The additional semantic decisions below still block freezing the v1 contract and starting conformant reader/writer implementation. See [Issue #120](https://github.com/708san/motionpack/issues/120) for the authoritative acceptance criteria, including loss reporting, no output on unconfirmed loss, canonicalization, and v0.1–v0.4 regression coverage.

## Evidence-based legacy migration inventory

This is a preliminary planning matrix, not a v1 mapping. “Confirmed view” means the current experimental importer exposes the source fact; it does not mean v1 accepts or interprets it. “Open” means no target disposition is approved.

| Source | Confirmed source evidence | v1 disposition |
|---|---|---|
| v0.1 | Canvas, assets, nodes, clips, tracks, declarative effects, variants/defaults; SVG dimensions may be omitted. | Map only fields whose v1 semantics are approved. Preserve source bytes and sparse presence. Unknown nested fields are not fully classified. Dimensionless SVGs are preserved without inferred dimensions and reported unsupported or lossy until explicitly repaired. |
| v0.2 | Adds two-bone IK; missing IK `weight` is specified as 1. Runtime also observes omitted `bend` as 1, but the format does not specify this. | IK mapping and default provenance need explicit v1 semantics. The observed bend default must not become normative by inference. |
| v0.3 | Adds the SVG dimension validation profile: positive numeric px dimensions, edge up to 8,192 px, area up to 16 MP. | The maintainer selected these positive-pixel dimensions and ceilings for v1; reader conformance must validate them separately from lower host resource limits. |
| v0.4 | Adds per-node `hover`, `tap`, and `click` booleans; omitted flags are disabled; notifications are data-only. | v1 scope is approved to define semantics for all v0.4 features. Exact interaction and cross-renderer guarantees remain to be written and reviewed normatively; no behavior is inferred solely from the preview. |

Across all versions, the importer currently keeps original manifest bytes and retained regular-file payloads, while its normalized projection only reports confirmed mappings. Unrecognized top-level fields are reported unsupported by that projection; nested unknown fields are generally preserved but unclassified. v0.1 IK is preserved and warned as a specification/implementation mismatch, not interpreted as a v1 capability. These importer behaviors do not decide the future writer’s output policy.

The experimental effective-default view currently reports: clip `loop=false` for v0.1–v0.4; IK `weight=1` for v0.2–v0.4; IK `bend=1` as an implementation observation for v0.2–v0.4; burst `count=28` as an implementation observation for v0.1–v0.4 when absent; and v0.4 interaction flags as disabled when absent. These are source-version facts with provenance. They are not automatically v1 defaults, and authored values remain distinct from omitted values.

## Read-only importer evidence inventory (non-normative)

This inventory records what the current legacy importer and its tests demonstrate. It is evidence for future contract and conformance work; it does not define v1 mappings or change v0.1–v0.4 behavior.

| Area | Existing implementation/test evidence | Limit of this evidence |
|---|---|---|
| Source package preservation | `test_read_only_snapshots_preserve_all_v01_to_v04_payloads` builds v0.1–v0.4 inputs, retains the original manifest bytes and every accepted regular-file payload byte (including opaque `source/original.bin`), and checks that import does not mutate the input. Snapshot mappings are immutable. | ZIP metadata, directory-only entries, and container layout are not retained. This is the importer’s current behavior, not an approved v1 package policy. |
| Sparse fields and locations | `test_normalized_view_projects_sparse_fields_and_provenance` checks authored field presence for nodes, clips, tracks, defaults, and source JSON pointers. Omitted fields remain omitted in the projected authored values. | The projection is not a complete v1 object model; it does not decide how v1 represents these fields. |
| Root-level unknown fields | The preservation test injects an unknown top-level field. The raw manifest retains it, and the migration report marks it `unsupported` with no normalized target. | This is the read-only importer’s projection report. A future v1 reader/writer still needs an explicit preservation and save policy. |
| Nested unknown fields | The same test injects an unknown nested node field. It remains available in the preserved manifest and node fields, with no migration finding emitted for it. | Nested unknown fields are preserved but not semantically classified by the current importer. |
| Version-specific source facts | `test_report_source_facts_are_deterministic_and_source_only` checks repeatable source-fact and migration reports for v0.1–v0.4, including the v0.3+ SVG-dimension validation-profile fact and the v0.4 interaction declaration fact. | These facts describe source versions and observed declarations. They do not authorize mapping every declaration to a v1 capability or guarantee runtime parity. |
| Sparse defaults and provenance | Dedicated tests cover omitted clip `loop=false`; burst `count=28` as an implementation observation; IK `weight=1` as a v0.2+ specification default; IK `bend=1` as a v0.2+ implementation observation; and v0.4 interaction flags defaulting to disabled. Each effective value is kept separately with a source pointer and rule provenance. | None of these observations is automatically a v1 default. Authored presence and effective values must remain distinct unless an explicit v1 decision says otherwise. |
| Ambiguous v0.1 IK | `test_v01_ik_is_normalized_with_spec_mismatch_diagnostic` checks that v0.1 IK bytes and sparse fields are preserved, a specification-mismatch diagnostic is emitted, and the migration finding is `preserved_uninterpreted` with no v1 semantic target. | This is a known specification/implementation mismatch. It must not be converted into a v1 meaning by inference. |
| Deterministic reporting | The source-fact test imports each version twice and compares the findings and source facts. | Deterministic reports for these fixtures do not define canonical manifest serialization or deterministic archive bytes. |

### Candidate v1 conformance cases

These are future test targets, not currently passing v1 tests. D1–D3 are decided; expected outcomes remain conditional wherever the remaining contract choices below are open.

- Minimal valid v1 package and boundary-invalid manifest cases, after the v1 core field inventory and validation rules are approved.
- Reject an unknown core field and an unknown required capability before reading referenced asset payloads.
- Ignore an unknown optional capability only when the approved safe-ignore rule applies; otherwise reject it.
- Preserve an opaque extension payload across read and write without assigning it meaning.
- Verify canonical manifest bytes and byte-identical complete ZIP output, pinning UTF-8, JSON normalization, key ordering, number form, newline behavior, ZIP entry ordering, timestamps, permissions, compression method/parameters, comments, extra fields, directory entries, and all container metadata.
- Exercise each pinned v0.1–v0.4 fixture through the importer and v1 migration report for the data actually present in that fixture. Add separate synthetic probes for unknown top-level/nested fields, opaque `source/` payloads, sparse defaults, and dimensionless legacy SVGs. The v0.1 IK mismatch is a separately constructed probe that relabels a v0.2 fixture; it must not be reported as coverage of the pinned v0.1 fixture.
- For each reported migration loss, verify source pointer/payload identity and conversion action; ensure an unconfirmed lossy write creates no output and leaves the source unchanged.
- Verify that a confirmation becomes invalid after either the source bytes or conversion plan changes.
- Read back every accepted writer output and compare preserved data, normalized values, and the agreed canonicalization evidence.

No v1 writer, integrated v1 reader, or v1 normative conformance suite is present yet. Track these cases as planning requirements until a frozen contract makes their expected results unambiguous.

## Remaining decisions for a testable normative contract

The following details remain open even after the approved directions above:

- Complete v1 core fields, types, ranges, reference integrity, collection ordering, and closed field sets.
- Maximum clip duration, fractional-millisecond precision/representation limits, property-specific numeric ranges, and remaining effect/IK timing interactions.
- Remaining variant overlay fields/defaults/merge behavior and interaction with IK; only same-property variant-over-track precedence is approved. Remaining effect fields, units, parameter ranges/defaults, timing interactions, renderer appearance, and conformance; only the stated coordinate split is approved.
- Exact interaction field meanings and whether v1 guarantees cross-renderer event/hit-test behavior. The full v0.4 feature surface is in scope, but current preview behavior is not automatically normative.
- Capability identifier grammar, required/optional declaration rules, registry ownership, and exact safe-ignore rules.
- S3 numeric domains and invalid-value behavior for transforms, opacity and z; negative-scale support; and any further graph/reference rules.
- Canonical JSON rules for extensions, duplicate-key handling, numeric equivalence, Unicode, and extension validation.
- Exact opaque package payload identity (entry name and payload bytes), paths/types admitted, per-entry and aggregate bounds, and deterministic writer treatment. Input ZIP metadata is not retained; output ZIP metadata still requires a fixed D3 profile.
- Stable error identifiers, validation stages/order, failures before payload reads, and the distinction among invalid input, unsupported capability, and migration loss.
- Loss report schema, source pointer/payload identity, conversion action, confirmation inputs, and no-output/unchanged-destination behavior on failure.
- Compatibility boundaries for format/runtime APIs and supported platforms. Read-only v0.x importer support has no duration guarantee.

Do not classify permissively accepted v0 nested fields as invalid merely because their v1 mapping is not yet known.

## Proposed work sequence

1. Record D1–D3 and the additional approved directions above; resolve or explicitly defer remaining normative details with safe behavior.
2. Have the Architect review the resulting normative schema and migration rules.
3. Update `FORMAT_SPEC.md` and add normative fixtures/conformance cases for v1, including unknown required/core fields, explicitly safe optional capabilities, opaque extensions, canonicalization, loss confirmation, and round trips.
4. Implement manifest-first v1 validation/reading and integrate the capability preflight before referenced asset reads.
5. Implement the writer only against the frozen reader/schema. Produce a deterministic loss report before output and invalidate confirmation when source or plan identity changes.
6. Demonstrate v0.1–v0.4 regression coverage, v1 round trips, and that unconfirmed lossy saves produce no output and do not mutate input.

### Acceptance criteria for this proposal milestone

- This draft remains explicitly non-normative, records approved D1–D3 accurately, and keeps remaining semantic choices visible.
- The migration inventory distinguishes importer observations from v1 decisions.
- No legacy package acceptance or interpretation changes.
- Issue #120 remains open until its contract and implementation acceptance criteria are met.

### Rollback

Revert this proposal document if its recommendations are rejected. No source package, format rule, reader, or writer is changed by this draft.
