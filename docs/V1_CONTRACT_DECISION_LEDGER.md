# v1 Contract Decision Ledger

**Status: non-normative planning record.** This ledger consolidates what is approved, what remains a maintainer decision, and which work each decision gates. It does not define v1 behavior or change v0.1–v0.4.

Authoritative contract acceptance criteria remain in [Issue #120](https://github.com/708san/motionpack/issues/120). The [v1 contract proposal](V1_CONTRACT_PROPOSAL.md) contains the detailed three-choice options and migration evidence. Promote decisions into `FORMAT_SPEC.md` only after maintainer approval and Architect review.

## Approved scope and constraints

The maintainer selected v1.0 minimum scope **A**: stable format, integrated reader/validator, and a writer that reports conversion losses and requires explicit confirmation before a lossy save. GUI and AI authoring are outside v1.0 core.

Previously approved planning directions:

- Keep the v0.1–v0.4 importer read-only; preserve original manifest bytes, opaque payloads, sparse authored values, and provenance.
- Keep effective defaults separate from authored values, with source and rule provenance.
- Preserve ambiguous data, including v0.1 IK, with a warning and without assigning new meaning.
- Bind loss confirmation to the exact source and conversion plan; a source or plan change invalidates confirmation.
- Use `capabilities.required[]` and `capabilities.optional[]`; use reverse-domain extension keys; reject unknown core fields and unknown required capabilities; ignore unknown optional capabilities only under an explicit safe-ignore rule; retain opaque extension data.

These directions do not constitute a frozen schema or prove that an implementation exists.

## Decisions that block contract freeze

### D1 — v1 core data shapes

**Question:** Reuse v0.4-shaped fields with explicitly defined v1 meanings, or redesign the core schema?

**Record:** Pending. The detailed options and compatibility consequences are in the proposal.

**Needed before:** Closing the core-field inventory, publishing normative fixtures, and defining v0.1–v0.4 mappings.

### D2 — SVG root dimensions

**Question:** Require positive numeric-pixel `width` and `height`, or allow either to be omitted? If required, should v1 adopt the existing 8,192-pixel edge and 16-megapixel ceilings?

**Record:** Pending. v0.1/v0.2 can contain dimensionless SVGs; migration must not infer dimensions without an explicit rule.

**Needed before:** Normative asset validation and expected migration outcomes for dimensionless legacy SVGs.

### D3 — Canonicalization scope

**Question:** Guarantee canonical manifest bytes only, or deterministic complete ZIP bytes as well?

**Record:** Pending. Whole-ZIP reproducibility additionally fixes entry ordering, timestamps, permissions, compression parameters, comments, extra fields, directory entries, and container metadata.

**Needed before:** Canonical serialization fixtures and writer output guarantees.

## Additional semantic decisions

The existing v0 specifications, runtime, importer, and examples are evidence about legacy inputs. They do not automatically define v1 meanings.

| ID | Area | Evidence that can be reused | Decision needed for a testable v1 contract | Blocks |
|---|---|---|---|---|
| S1 | Package envelope and entries | ZIP packages use a root `manifest.json`; the importer retains accepted regular-file payload bytes. | Define package identity/version fields, runtime entries, `source/` policy, and handling of unknown or unreferenced regular files. State whether ZIP metadata is in the preservation contract. | Reader, writer, migration |
| S2 | Core field inventory | Canvas, assets, drawable nodes, clips, tracks, variants, defaults, effects, and (by version) IK and interactions are present in v0.x. | Close the v1 field inventory, JSON types, numeric ranges, required/optional fields, references, collection ordering, and unknown-field behavior by object. | Schema, validator, fixtures |
| S3 | Nodes and transforms | The importer retains IDs, declaration order, authored fields, and source pointers. | Define graph/reference integrity, transform composition, anchors, dimensions and fallbacks, opacity, and Z ordering. | Reader, renderer conformance, migration |
| S4 | Time and tracks | Legacy time values use milliseconds; omitted clip `loop` is documented false. | Define interpolation, key ordering and duplicates, boundaries, sampling, loop/end behavior, valid ranges, and v1 defaults. | Schema, runtime conformance, migration |
| S5 | Effects and variants | v0.x contains declarative effects and sparse variant overlays; omitted burst count 28 is an implementation observation. | Select supported effect types/parameters and their units/defaults; define variant overlay grammar, precedence, and defaults. Do not promote implementation observations by inference. | Capabilities, reader/writer, migration |
| S6 | IK | v0.2 documents omitted `weight` as 1; omitted `bend` is only an implementation observation. v0.1 IK is ambiguous and approved as preserve/warn/uninterpreted. | Define v1 IK semantics and capability declaration; specify migration only where semantics are approved. Keep v0.1 IK uninterpreted unless the maintainer decides otherwise. | Capabilities, migration, conformance |
| S7 | Interaction | v0.4 stores opt-in `hover`, `tap`, and `click` booleans; current preview behavior is host notification only. | Decide whether v1 only stores declarations or guarantees cross-renderer events/hit-testing. If behavior is guaranteed, define input types, hit regions, occlusion, ordering, and host boundary. | Capability profile, runtime conformance |
| S8 | Assets and resource profiles | Existing tools inspect SVG/raster headers under configured limits; reader limits are tool policy, not format guarantees. | Define accepted asset profiles, reference/path rules, format validity vs reader resource limits, and what validation must occur before payload use. | Reader, security profile, conformance |
| S9 | Capabilities and extensions | The approved direction separates required/optional capabilities and retains opaque extension data. | Define identifier grammar and ownership, declaration/derivation rules, extension value representation, and the exact safe-ignore condition for each optional capability. | Preflight, reader, writer |
| S10 | Legacy unknowns and provenance | Importer retains raw manifest/payload data and distinguishes authored fields from provenance-bearing effective values. | Define v1 representation and preservation of opaque data; specify mapped, preserved, unsupported, and lossy dispositions per source field. Nested unknown legacy fields are not fully classified today. | Migration report, writer |
| S11 | Errors and validation order | Current reader has bounded archive checks and a manifest-first prototype; stable public error categories are not defined. | Define error identifiers/categories, validation order, what must fail before asset reads, and how invalid input differs from unsupported capability or migration loss. | Reader API, conformance |
| S12 | Loss reports and confirmation | The approved direction requires reporting loss before output and invalidating confirmation when source or plan changes. | Define report fields, source pointer/payload identity, conversion action, confirmation inputs, and no-output behavior on unconfirmed or failed writes. | Writer API, round-trip tests |
| S13 | Compatibility lifecycle | v0.1–v0.4 remain experimental; the current compatibility policy is a draft. | Define supported format versions, runtime/API version independence, deprecation/support windows, and platform support. | Release policy and compatibility claims |

## Safe work before the decisions are complete

The following work can prepare implementation without guessing at public behavior:

1. Reconcile the four pinned v0 fixtures, feature inventory, and importer evidence while keeping documented rules, implementation observations, and unknowns distinct.
2. Review the internal reader stages: bounded archive snapshot, manifest-first parse, capability preflight, asset validation, and normalized view. Do not publish an API or semantic guarantee from this map.
3. Maintain candidate conformance cases as conditional until the expected outcomes are approved.
4. Continue independent security and visual-release work under their own issues; do not present those results as v1 contract approval.

## Implementation gates

1. Record D1–D3 and resolve or explicitly defer S1–S13.
2. Have the Architect review the selected schema and migration matrix.
3. Update `FORMAT_SPEC.md` and add normative fixtures.
4. Implement and verify the manifest-first reader/validator.
5. Implement the loss-aware writer against the frozen schema.
6. Prove legacy regression, v1 conformance, round trips, and no output on unconfirmed loss.
7. Assess separate v1 release gates: security residuals, visual/motion review, platform/performance support, asset rights, license, distribution integrity, and maintainer release approval.

Issue #120 remains open until its implementation and acceptance criteria are met.

## Acceptance and rollback

- This ledger remains non-normative and makes no maintainer decision.
- Each open item is distinguishable from approved scope and observed legacy behavior.
- No v0 behavior, public contract, code, fixture, or release claim changes.
- If the ledger is rejected or becomes redundant, revert this file; keep the contract choices and implementation gates in Issue #120.
