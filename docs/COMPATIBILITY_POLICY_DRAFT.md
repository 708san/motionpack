# MotionPack compatibility policy — proposal

**Status: draft for Architect and maintainer review.** This document proposes policy and schema choices; it does not declare a stable public contract. MotionPack formats 0.1–0.4 remain experimental until a v1.0 release decision accepts and publishes a versioned specification.

## Maintainer-approved direction (2026-11-09)

- The v1.0 importer is to support all current experimental versions: v0.1, v0.2, v0.3 and v0.4. This direction requires a frozen, checksummed package fixture and reviewed feature inventory for each version before format freeze.
- v1.0 will declare capabilities, and a reader must reject an unknown required capability before loading assets or starting playback.
- The first importer stage is read-only: it returns an in-memory snapshot for v0.1–v0.4, preserves original manifest and opaque payload bytes, and reports unsupported or unclassified information. The experimental source-fact ledger records source observations without assigning v1 meanings or target capability requirements. v1.0 serialization and conversion are separate later work.

These are scope and behavior decisions. The capability field layout and unknown-field policy below are also approved directions, but the overall v1.0 schema, importer workflow and format contract remain drafts.

## Version independently evolving components

Track these versions independently:

1. **File format version**: serialization rules, field meanings and supported package capabilities.
2. **Runtime version**: callable player/evaluator APIs and rendering or decoding implementations.
3. **Authoring tool version**: import, editing, validation, conversion and export behavior.

Each distributable should report its own version and the format versions and capabilities it supports. A runtime version must not be inferred from a file format version, or vice versa.

Use semantic versioning as a starting point for stable runtime and tool APIs: PATCH fixes preserve documented behavior; MINOR adds compatible capabilities; MAJOR may remove or change documented behavior. File format compatibility follows the format-specific rules below rather than being coupled to a runtime release number.

## Experimental v0.x input

The v0.1, v0.2, v0.3 and v0.4 formats do not receive a formal backward-compatibility guarantee. Keep the repository's frozen v0.1–v0.4 package fixtures as regression references; SHA-256 checks are pinned for each fixture in archive-reader tests. v0.1/v0.2 are historical archive-reader fuzz seeds; v0.3/v0.4 fixtures are generated from the layered plant and interaction examples. v0.4 adds optional per-node host interaction flags and does not add executable behavior to manifests. The selected v1.0 importer scope covers all four versions. It must report unsupported or lossy features and preserve source material and provenance where present. Conversion must not silently discard fields or rewrite original files. The initial importer stage is approved as read-only; v1.0 serialization and conversion remain separate open design work.

Rejection of a legacy file for a security reason must name the reason and provide a documented migration path where feasible. The repository now has regression fixtures and pinned SHA-256 checks for all four selected versions. A reviewed feature inventory for each version remains required before format freeze.

## Maintainer-approved legacy-to-v1 handling (2026-11-10)

These decisions govern the proposed v1 migration and future save behavior only; they do not alter current experimental v0.x import or runtime behavior.

- Keep authored sparse values and field presence distinct from any effective-values interpretation. Derived defaults appear only in a separate view with source and rule provenance.
- Preserve and warn about ambiguous or specification/implementation-mismatch data without assigning v1 semantics. This supersedes the earlier v1 migration proposal to interpret v0.1 IK compatibly; the existing v0.x behavior remains an observed implementation. Confirmation for a lossy save does not authorize assigning meaning to such data.
- Require explicit user confirmation before saving any output that transforms or drops information. Without prior confirmation, the tool must preserve the source or cancel the save; a warning alone is insufficient. Confirmation authorizes only the specified loss, does not authorize v1 semantic interpretation of ambiguous data, and cannot override validation failures, security rejections, or unsupported required-capability errors.

## Proposed v1 format rules

- A published v1 format contract is immutable for its major version. Existing field meanings, defaults and ordering semantics must not change silently.
- A compatible additive change may add an optional field or capability only when older conforming readers can safely identify and handle it. Required capabilities must be declared explicitly.
- A change that alters existing interpretation, makes a previously valid package invalid, or requires new behavior from every reader requires a new format major version or a separately versioned profile with an explicit migration.
- Unknown required capabilities cause a clear unsupported-feature error before loading assets or playback. Unknown optional capabilities may be ignored only when the specification defines that omission as semantically safe; otherwise the reader must fail clearly.
- Format revisions must state the minimum compatible runtime capability set. Runtime releases publish the format versions and optional capabilities they implement.

### Approved capability and extension direction

The v1.0 manifest declares capabilities using separate required and optional identifier arrays:

```json
"capabilities": {
  "required": ["org.motionpack.ik.two-bone"],
  "optional": ["org.motionpack.interaction"]
}
```

The selected standard identifiers are `org.motionpack.ik.two-bone` for the v0.2 two-bone IK feature and `org.motionpack.interaction` for v0.4 node interaction. Unknown required identifiers must fail before assets are loaded or playback starts. Unknown optional identifiers may be ignored only when the v1.0 specification defines omission as safe; writers preserve the declaration and associated opaque data when round-tripping.

A top-level `extensions` object uses reverse-domain keys to hold opaque extension data. Unknown fields in core objects are rejected. Extension identifiers and payloads never trigger network lookup, code execution, shader execution or external resource loading. Writers that cannot preserve opaque extension data must obtain explicit confirmation before producing a lossy save. Without confirmation, they must preserve the original or cancel the save. Downgrade conversion must report unsupported capabilities.

These directions apply to v1.0 only. A v1.0 importer derives capabilities only where the source version and contents have an approved, unambiguous v1 mapping; it does not add fields to legacy manifests. In particular, v0.1 IK records are preserved and reported as a specification mismatch, but do not imply the v1 two-bone IK capability. The exact identifier grammar and namespace registration process remain open release-design details. The schema and format are still drafts, not a stable public contract.

## Reader/writer and forward-compatibility behavior

- Readers validate version and required capabilities before rendering. They never execute package-provided JavaScript, remote code, shaders or undeclared external resources.
- Readers must not silently ignore an unknown required field or capability when doing so can change the result. They return an actionable error naming the missing capability.
- Writers preserve unrecognized extension data when the format specification says it is safe and the tool can round-trip it. Any save that transforms or drops information requires explicit confirmation before output; without confirmation the writer cancels the lossy save.
- A writer may offer a named compatibility profile. The selected profile and every omitted or transformed feature are visible in the export report.
- Static-image or video fallback is an optional export feature, not a substitute for required-feature detection in an editable package.

## Deprecation and support

Before stabilizing v1.0, publish a support window for file formats, runtime APIs and authoring APIs separately. For stable runtime/tool APIs, announce deprecation in a MINOR release and keep the behavior available through at least the next MINOR release before removal in a MAJOR release. Security fixes may require faster restriction or removal; document the affected inputs, reason and migration guidance without implying old files are safe to open.

The v1.0 release proposal must name the supported format versions, target runtimes/platforms, known unsupported capabilities and end-of-support process. Maintainers approve support-window durations as a release decision.

## Compatibility evidence required for a stable release

Keep immutable, checksummed samples for each supported format version and runtime API major version. CI should cover:

- Read and validate every supported historical fixture.
- Compare sampled animation states at fixed timestamps, clip boundaries, loop boundaries and variants.
- Compare reviewed render baselines for each supported renderer profile; image comparisons do not replace human motion and appearance review.
- Exercise edit/save/reload and conversion while checking that supported fields, source assets and provenance are retained.
- Confirm clear failure for missing required capabilities and safe handling of each explicitly optional capability.
- Verify offline use and ensure compatibility fallback never fetches network resources or executes package code.

Once v1.0 is published, retain its normative specification, fixtures and compatibility test definitions. A security-motivated rejection of a previously supported file requires a recorded security rationale, impact assessment and migration guidance.

## Decisions still required before v1.0

- Which documented or implementation-derived source behaviors map to v1.0 semantics, and the exact fields/identifiers in the loss and preservation report. The approved separation, ambiguity-warning, and explicit lossy-save confirmation policies do not define that model. v1.0 serialization remains separate open work.
- The exact capability identifier grammar, extension namespace owner and identifier registration process.
- How reader resource limits differ from format validity and whether v1.0 defines conformance/resource profiles.
- The support window for each format and API family.
- Which runtimes/platforms are in the initial support matrix.
- The project license and release artifact signing/distribution process.

These remaining decisions require maintainer approval. The migration-handling policies above are approved planning direction but do not freeze a schema or serializer. This draft makes no license selection or platform-support guarantee.
