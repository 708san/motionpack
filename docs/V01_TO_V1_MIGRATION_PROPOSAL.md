# v0.1–v0.4 to v1.0 migration semantics (proposal)

**Status: non-normative design proposal for Issue #62.** This document uses the merged experimental read-only importer and repository fixtures as evidence. It does not define a v1 manifest, serializer, converter, or stable compatibility promise.

## Purpose and evidence labels

Prepare a version-aware interpretation boundary before v1 serialization. Every statement is marked as one of:

- **Documented rule** — stated in FORMAT_SPEC.md for the indicated source version.
- **Observed implementation** — behavior in the current validator, importer, evaluator, or preview; not automatically a format guarantee.
- **Proposed v1 interpretation** — a candidate migration behavior that still requires maintainer approval.
- **Unresolved** — evidence or a policy decision is insufficient.

Primary evidence: FORMAT_SPEC.md, V0_FEATURE_INVENTORY.md, NORMALIZED_LEGACY_MODEL.md, tools/legacy_importer.py, tools/validate.py, runtime/evaluator.js, runtime/ik_solver.js, and the SHA-pinned v0.1–v0.4 fixtures. External packages and assets not represented by this repository have not been inventoried.

## Three preservation layers

1. **Source bytes** — the importer retains exact manifest bytes and accepted regular-file payload bytes, including opaque source/ and unreferenced entries. This supports exact recovery of those individual payloads, not reconstruction of the original ZIP archive.
2. **Sparse normalized view** — the imported manifest and normalized records retain authored values and field presence. Missing fields stay missing. This is the current read-only importer contract.
3. **Effective semantic interpretation** — a proposed separate view may expose behavior after applying a documented or implementation-derived rule. It must never overwrite the source or sparse normalized view.

**Proposed v1 interpretation:** each effective value should carry the source version, source JSON pointer or archive path, whether the source field was authored, the applied rule identifier, whether the rule is documented or implementation-derived, and a confidence/status. If no defensible rule exists, do not invent an effective value.

## Proposed preservation and loss report

Each report item should identify the source location and distinguish source retention from semantic support. Candidate fields:

| Field | Meaning |
|---|---|
| code | Stable diagnostic identifier, once identifiers are approved. |
| source_version | Original v0.x version. |
| source_pointer / archive_path | JSON Pointer for manifest data or ZIP member path for payloads. |
| category | One of the categories below. |
| observed | Authored value or implementation evidence, when safe and useful to show. |
| interpretation | Effective value/rule, or why no interpretation was made. |
| target_capability | v1 capability needed to preserve/use the construct, if known. |
| action | Proposed import/save handling. |
| reason | Compatibility, ambiguity, unsupported behavior, or preservation limitation. |

### Categories

- **byte-preserved** — exact manifest or accepted payload bytes retained.
- **mapped** — source construct has a proposed v1 semantic counterpart.
- **interpreted-default** — an absent field receives an effective value under a named rule; source presence remains absent.
- **preserved-uninterpreted** — source value remains available but no semantic behavior is claimed.
- **unsupported** — current target does not implement the construct.
- **ambiguous** — evidence conflicts or does not determine a safe meaning.
- **container-unavailable** — ZIP metadata not captured by the importer.
- **rejected** — structural, security, resource-limit, or unsupported-required-capability error prevented a complete import.

### Candidate actions (policy unresolved)

- **continue** for safely preserved and understood data.
- **warn** for implementation-derived defaults, version mismatches, and uninterpreted data that remains byte-preserved.
- **require-confirmation** before a future save would drop or transform authored information.
- **fail-import** for invalid/security/resource-limit input and, in v1, an unknown required capability before asset loading or playback.

**Unresolved:** whether a read-only import should ever fail solely because semantic information is ambiguous (the proposal is to preserve and report); which lossy-save categories require confirmation versus hard refusal; and whether report action names should become public API.

## Version-by-version mapping proposal

| Source | Evidence | Sparse normalized view | Proposed effective v1 view / report | Status |
|---|---|---|---|---|
| v0.1 shared package fields | **Documented rule:** base canvas/assets/nodes/clips/tracks/effects/variants/defaults. | Preserve authored fields and pointers; unclassified fields remain reachable through manifest. | Map known constructs only; report unknown fields as preserved-uninterpreted. | Proposed; audit full field list before approval. |
| v0.1 IK declarations or tracks | **Observed implementation:** current validator/runtime accept and process IK without a version gate. **Documented rule:** IK is introduced in v0.2. | Keep IK records and observed IK capability; attach the v0.2-spec mismatch diagnostic. | Preserve current behavior as an observed interpretation, tagged ambiguous/version-spec-mismatch; do not claim ordinary v0.1 semantics. | Explicit user decision: interpret compatibly and report mismatch. Stable v1 mapping remains open. |
| v0.2 IK | **Documented rule:** two-bone IK; absent weight defaults to 1 and runtime clamps finite weight to [0,1]. | Preserve authored chain/track fields and presence. | Candidate effective default weight=1 with rule provenance; clamping is runtime behavior and must not silently rewrite source. | Proposed. Confirm complete IK field mapping before serializer. |
| v0.2 IK bend | **Observed implementation:** current inventory reports missing bend behaves as 1. | Keep absence distinguishable. | Candidate implementation-derived default, not a format-wide guarantee; report the rule source. | Unresolved maintainer approval. |
| v0.3 validation profile | **Documented rule:** referenced SVG roots require bounded positive numeric px dimensions. | Preserve SVG bytes and report v0.3 profile fact. | Treat as source validation profile, not an animation/runtime capability. Rejection under current reader limits is reported separately from format meaning. | Proposed. |
| v0.4 interaction | **Documented rule:** per-node hover/tap/click booleans are opt-in data-only host notifications. | Preserve flags, omission, source pointers, and observed capability. | Map to host interaction data only; do not infer host action, authorization, or runtime support from declaration. | Proposed, consistent with current contract. |
| Missing clip loop | **Documented rule:** absent loop means false; present value must be boolean. | Retain absence vs explicit false. | Effective false may be exposed with a versioned rule reference; never materialize it into source. | Proposed. |
| Missing canvas background | **Documented/current:** optional; no universal fallback is established here. | Preserve omission. | Leave unspecified unless a target renderer profile defines a traced fallback. | Unresolved. |
| Missing node width/height | **Observed implementation:** preview uses intrinsic asset size. | Preserve omission and asset relationship. | Renderer-dependent unless a v1 engine-independent rule is explicitly approved; report when the target lacks intrinsic dimensions. | Unresolved. |
| Effects and renderer defaults | **Observed implementation:** burst count defaults to 28; interpolation and boundary details are implementation-specific. | Preserve source declarations and omissions. | Do not make renderer defaults normative by copying them into v1 semantics without approval; report profile-dependent interpretation. | Unresolved. |
| Unknown legacy fields | **Observed implementation:** nested fields are retained in parsed manifest but are not comprehensively classified. | Preserve raw manifest bytes and parsed fields; mark unclassified locations. | Keep opaque and uninterpreted unless a reviewed mapping exists. Never silently drop on save. | Proposed. |
| Unknown v1 core fields / extensions | **Approved direction:** unknown core fields rejected; reverse-domain extensions hold opaque data; capability arrays separate required/optional. | Does not change v0.x manifests. | Unknown required capability fails before assets/playback; optional handling only where omission is declared safe; extension preservation required for round-trip. | Approved direction; full v1 schema remains draft. |
| Opaque source and unreferenced payloads | **Observed importer behavior:** accepted regular-file payloads, including source/ and unreferenced entries, are retained as opaque bytes. | Keep separated from runtime asset declarations and do not decode. | Preserve as payload-store entries; report semantic role as unknown unless manifest/provenance identifies it. | Proposed. |
| ZIP container details | **Observed importer limit:** compression representation, timestamps/permissions, comments/extra fields, directories, and entry ordering are not retained. | Not represented in snapshot. | Report container-unavailable; do not claim byte-identical archive round-trip. | Required limitation. |
| Tool limits and security rejection | **Observed implementation:** reader byte/entry/ratio/time/process constraints can reject a package independently of its intended visual meaning. | Failure returns no partial snapshot. | Report rejection separately from semantic unsupported/loss; no partial effective view. | Proposed; Issue #4 remains open. |

## Capability facts versus target support

Keep three facts separate:

1. **Observed source capability** — a construct is present in the manifest.
2. **Version/profile rule** — a source-version requirement applies, such as v0.3 SVG dimensions.
3. **Target support** — the selected v1 reader/runtime actually implements the construct.

The v0.1–v0.4 importer can infer source facts but cannot claim target support. The approved capability identifiers are org.motionpack.ik.two-bone and org.motionpack.interaction. Their approved direction does not settle the full v1 schema, identifier registration policy, or every version-to-capability derivation rule.

## Maintainer decisions before this can be accepted

1. Should effective defaults be a separate traced interpretation over the sparse view? The recommendation is yes; do not rewrite source values.
2. Which behavior is sufficiently documented to become a v1 semantic default, versus implementation-derived or unresolved?
3. Should ambiguous constructs (especially v0.1 IK) remain available but uninterpreted for conversion, or be eligible for an explicitly confirmed mapping?
4. Which preservation-report outcomes warn, require explicit confirmation before save, or make lossless save unavailable?
5. What exact v1 field and error model consumes this report? This issue deliberately does not define or implement it.

## Acceptance and next step

Before this proposal is treated as accepted:

- Review every row against the full feature inventory and four pinned fixtures.
- Have Architect verify format/runtime boundaries and Functional QA verify that each claim has fixture or code evidence.
- Resolve the maintainer decisions above and record them before designing a serializer.
- Keep any v1 schema, converter, and serializer in a later issue/PR with migration fixtures and no-silent-loss tests.

Rollback: remove this non-normative proposal. It changes no package, code path, legacy acceptance rule, or fixture.