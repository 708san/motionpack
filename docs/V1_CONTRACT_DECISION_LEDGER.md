# v1 Contract Decision Ledger

**Status: non-normative planning record.** This ledger consolidates what is approved, what remains a maintainer decision, and which work each decision gates. It does not define v1 behavior or change v0.1–v0.4.

Authoritative contract acceptance criteria remain in [Issue #120](https://github.com/708san/motionpack/issues/120). The [v1 contract proposal](V1_CONTRACT_PROPOSAL.md) contains the detailed migration evidence and fuller discussion. Promote decisions into `FORMAT_SPEC.md` only after maintainer approval and Architect review.

## Approved scope and constraints

The maintainer selected v1.0 minimum scope **A**: stable format, integrated reader/validator, and a writer that reports conversion losses and requires explicit confirmation before a lossy save. GUI and AI authoring are outside v1.0 core.

The following are **approved planning directions, not a frozen v1 contract**:

- Keep the v0.1–v0.4 importer read-only; preserve original manifest bytes, opaque payloads, sparse authored values, and provenance.
- Keep effective defaults separate from authored values, with source and rule provenance.
- Preserve ambiguous data, including v0.1 IK, with a warning and without assigning new meaning.
- Bind loss confirmation to the exact source and conversion plan; a source or plan change invalidates confirmation.
- Use `capabilities.required[]` and `capabilities.optional[]`; use reverse-domain extension keys; reject unknown core fields and unknown required capabilities; ignore unknown optional capabilities only under an explicit safe-ignore rule; retain opaque extension data.

These directions do not prove that a frozen schema or implementation exists.

## Decisions that block contract freeze

All three decisions belong to the maintainer. The choices below summarize the alternatives; the linked proposal records the fuller compatibility consequences.

| ID | Choice | Option A | Option B | Current status |
|---|---|---|---|---|
| D1 | v1 core data shapes | Reuse familiar v0.4 field shapes and explicitly define v1 meanings. This reduces structural change, but does not make every v0.x field portable. | Redesign the core schema. This permits a new model, but requires explicit mappings and can increase migration loss. | Pending |
| D2 | SVG root dimensions | Require positive numeric-pixel `width` and `height`; decide whether to adopt the existing 8,192-pixel edge and 16-megapixel ceilings. Dimensionless legacy SVGs need an explicit migration disposition. | Allow omitted dimensions; define deterministic intrinsic sizing and resource checks without renderer-dependent assumptions. | Pending |
| D3 | Canonicalization scope | Guarantee canonical manifest bytes; ZIP metadata and whole-package hashes may vary by writer. | Guarantee deterministic complete ZIP bytes, which also fixes entry order, timestamps, permissions, compression parameters, comments, extra fields, directory entries, and container metadata. | Pending |

The ledger itself makes no recommendation. The linked proposal includes planning recommendations for some options; those are not maintainer decisions. Any combination can be selected. The v1 reader, writer, fixtures, and migration behavior that depend on them remain gated.

## Additional semantic decisions

The existing v0 specifications, runtime, importer, and examples are evidence about legacy inputs. They do not automatically define v1 meanings.

| ID | Area | Evidence that can be reused | Decision needed for a testable v1 contract | Blocks |
|---|---|---|---|---|
| S1 | Package envelope and entries | ZIP packages use a root `manifest.json`; the importer retains accepted regular-file payload bytes. | Define package identity/version fields, runtime entries, `source/` policy, unknown/unreferenced regular-file handling, and whether ZIP metadata is preserved. | Reader, writer, migration |
| S2 | Core field inventory | Canvas, assets, drawable nodes, clips, tracks, variants, defaults, effects, and (by version) IK and interactions are present in v0.x. | Close v1 fields, JSON types, numeric ranges, required/optional fields, references, ordering, and unknown-field behavior by object. | Schema, validator, fixtures |
| S3 | Nodes and transforms | The importer retains IDs, declaration order, authored fields, and source pointers. | Define graph/reference integrity, transform composition, anchors, dimensions/fallbacks, opacity, and Z ordering. | Reader, renderer conformance, migration |
| S4 | Time and tracks | Legacy time values use milliseconds; omitted clip `loop` is documented false. | Define interpolation, key ordering/duplicates, boundaries, sampling, loop/end behavior, valid ranges, and v1 defaults. | Schema, runtime conformance, migration |
| S5 | Effects and variants | v0.x contains declarative effects and sparse variant overlays; omitted burst count 28 is an implementation observation. | Select supported effects/parameters, units/defaults, and variant overlay grammar, precedence, and defaults. Do not promote observations by inference. | Capabilities, reader/writer, migration |
| S6 | IK | v0.2 documents omitted `weight` as 1; omitted `bend` is only an implementation observation. v0.1 IK is ambiguous and approved as preserve/warn/uninterpreted. | Define v1 IK semantics and capability declaration; map only approved meanings. Keep v0.1 IK uninterpreted absent an explicit decision. | Capabilities, migration, conformance |
| S7 | Interaction | v0.4 stores opt-in `hover`, `tap`, and `click` booleans; current preview behavior is host notification only. | Decide whether v1 stores declarations only or guarantees cross-renderer events/hit testing. If behavior is guaranteed, define inputs, hit regions, occlusion, ordering, and host boundary. | Capability profile, runtime conformance |
| S8 | Asset formats and resource profiles | Existing tools partially validate SVG structure, attributes, references, and dimensions; raster inspection reads format headers for dimensions. These checks and configured ceilings are tool behavior, not v1 guarantees. | Define accepted asset bytes/formats and distinguish format validity from implementation resource ceilings. Entry/path placement belongs to S1; feature support belongs to S9. | Reader, security profile, conformance |
| S9 | Capabilities and extensions | The approved direction separates required/optional capabilities and retains opaque extension data. | Define identifier grammar/ownership, declaration and derivation rules, extension value representation, and exact safe-ignore conditions. Payload preservation belongs to S1/S10. | Preflight, reader, writer |
| S10 | Legacy unknowns and provenance | Importer retains raw manifest/payload data and separates authored values from provenance-bearing effective values. | Define v1 opaque-data representation and per-field mapped, preserved, unsupported, or lossy dispositions. Nested unknown legacy fields are not fully classified today. | Migration report, writer |
| S11 | Errors and validation order | Current reader has bounded archive checks and a manifest-first prototype; stable public error categories are not defined. | Define error identifiers/categories, validation order, failures that precede asset reads, and distinctions among invalid input, unsupported capability, and migration loss. | Reader API, conformance |
| S12 | Loss reports and confirmation | The approved direction requires reporting loss before output and invalidating confirmation when source or plan changes. | Define report fields, source pointer/payload identity, conversion action, confirmation inputs, and no-output behavior on unconfirmed or failed writes. | Writer API, round-trip tests |
| S13 | Compatibility lifecycle | v0.1–v0.4 remain experimental; the compatibility policy is a draft. | Define supported format versions, independent runtime/API versioning, deprecation/support windows, and platform support. | Release policy, compatibility claims |

**Boundary note:** S1 covers the ZIP/package namespace and which bytes or entries are retained. S8 covers asset content profiles and resource limits. S9 covers declared feature support and extension semantics. S10 covers legacy field preservation and migration dispositions. Keep these scopes separate when recording decisions.

## Safe work before the decisions are complete

The following work can prepare implementation without guessing at public behavior:

1. Reconcile the four pinned v0 fixtures, feature inventory, and importer evidence while keeping documented rules, implementation observations, and unknowns distinct.
2. Review internal reader stages—bounded archive snapshot, manifest-first parse, capability preflight, asset validation, and normalized view—without locking public APIs or semantics.
3. Maintain candidate conformance cases as conditional until expected outcomes are approved.
4. Continue independent security and visual-release work under their own issues; do not present those results as v1 contract approval.

## Implementation gates

1. Record D1–D3 and resolve or explicitly defer S1–S13.
2. Have the Architect review the selected schema and migration matrix.
3. Update `FORMAT_SPEC.md` and add normative fixtures.
4. Only after contract freeze, implement and verify the manifest-first reader/validator.
5. Implement the loss-aware writer against the frozen schema.
6. Prove legacy regression, v1 conformance, round trips, and no output on unconfirmed loss.

Issue #120 is complete only when its normative contract, capability and extension rules, migration paths, fixtures, integrated reader, loss-aware writer, compatibility coverage, and round-trip/confirmation criteria are satisfied.

Separate v1.0 release gates remain: security residuals, visual/motion review, platform/performance support, asset rights, license, distribution integrity, and maintainer release approval.

## Acceptance and rollback

- This ledger remains non-normative and makes no maintainer decision.
- Each open item is distinguishable from approved planning directions and observed legacy behavior.
- No v0 behavior, public contract, code, fixture, or release claim changes.
- If the ledger is rejected or redundant, revert this file; keep the choices and implementation gates in Issue #120.
