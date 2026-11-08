# MotionPack compatibility policy — proposal

**Status: draft for Architect and maintainer review.** This document proposes a policy; it does not declare a stable public contract. MotionPack formats 0.1–0.4 remain experimental until a v1.0 release decision accepts and publishes a versioned specification.

## Version independently evolving components

Track these versions independently:

1. **File format version**: serialization rules, field meanings and supported package capabilities.
2. **Runtime version**: callable player/evaluator APIs and rendering or decoding implementations.
3. **Authoring tool version**: import, editing, validation, conversion and export behavior.

Each distributable should report its own version and the format versions and capabilities it supports. A runtime version must not be inferred from a file format version, or vice versa.

Use semantic versioning as a starting point for stable runtime and tool APIs: PATCH fixes preserve documented behavior; MINOR adds compatible capabilities; MAJOR may remove or change documented behavior. File format compatibility follows the format-specific rules below rather than being coupled to a runtime release number.

## Experimental v0.x input

The v0.1, v0.2, v0.3 and v0.4 formats do not receive a formal backward-compatibility guarantee. Keep the repository's frozen v0.1 package and current v0.2/v0.3/v0.4 fixtures as regression references. v0.4 adds optional per-node host interaction flags and does not add executable behavior to manifests. A v1.0 migration plan should provide an explicit importer/converter for each legacy version that is accepted at release time, report unsupported or lossy features, and preserve source material and provenance where present. Conversion must not silently discard fields or rewrite original files.

Maintainers must choose the exact legacy versions and fixtures supported by the v1.0 importer before format freeze. Rejection of a legacy file for a security reason must name the reason and provide a documented migration path where feasible.

## Proposed v1 format rules

- A published v1 format contract is immutable for its major version. Existing field meanings, defaults and ordering semantics must not change silently.
- A compatible additive change may add an optional field or capability only when older conforming readers can safely identify and handle it. Required capabilities must be declared explicitly.
- A change that alters existing interpretation, makes a previously valid package invalid, or requires new behavior from every reader requires a new format major version or a separately versioned profile with an explicit migration.
- Unknown required capabilities cause a clear unsupported-feature error before playback. Unknown optional capabilities may be ignored only when the specification defines that omission as semantically safe; otherwise the reader must fail clearly.
- Format revisions must state the minimum compatible runtime capability set. Runtime releases publish the format versions and optional capabilities they implement.

The exact manifest encoding for capability declarations, extension namespaces and profile negotiation remains an architecture decision. Do not add such fields to v0.1–v0.3 manifests as part of this proposal.

## Reader/writer and forward-compatibility behavior

- Readers validate version and required capabilities before rendering. They never execute package-provided JavaScript, remote code, shaders or undeclared external resources.
- Readers must not silently ignore an unknown required field or capability when doing so can change the result. They return an actionable error naming the missing capability.
- Writers preserve unrecognized extension data when the format specification says it is safe and the tool can round-trip it. Otherwise they warn or refuse a lossy save until the user chooses a conversion.
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

- Which v0.x versions and capabilities the v1.0 importer will accept.
- The manifest encoding and registry/namespace rules for required and optional capabilities.
- The support window for each format and API family.
- Which runtimes/platforms are in the initial support matrix.
- The project license and release artifact signing/distribution process.

These decisions require maintainer approval. This draft makes no license selection or platform-support guarantee.
