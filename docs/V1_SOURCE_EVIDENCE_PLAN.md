# v1 migration source-evidence ledger (experimental plan)

Status: implemented experimentally in PR #99 for the read-only v0.1–v0.4 importer. This document is not a v1 schema, compatibility guarantee, or target-runtime support statement.

## Purpose

Record facts directly observed in a legacy package or its source-version validation rules, with evidence pointers. Keep those facts distinct from v1 semantic mappings, required/optional capabilities, host authorization, and effective defaults.

## Implemented model

`ImportReport.source_facts` is an immutable tuple of `SourceFact` records. Each record contains `source_version`, `category`, `identifier`, `source_pointers`, and an optional diagnostic. Current categories are `source-format-version`, `observed-construct`, `observed-declaration`, and `validation-profile`. These records describe only the source package and the validator/spec profile used to accept it. There is no target mapping field; a source fact does not claim a v1 required/optional capability or prove that a runtime supports it.

The existing `snapshot.capabilities`, normalized `capability_facts`, effective-default view, and diagnostics retain their existing behavior. Source facts are additive and kept separate from those derived views.

## Implemented scope

- Add an immutable source-fact view alongside the existing import report.
- Record source version, fact category, identifier, and RFC 6901 JSON Pointers.
- Cover observed IK declarations, the v0.1 IK specification/implementation mismatch, v0.4 node interaction declarations, and the v0.3/v0.4 SVG-dimensions validation profile.
- Preserve all current snapshot, normalized view, capability, diagnostics, and payload behavior.
- Add no serializer, converter, public manifest field, or changes to v0.x acceptance.

## Acceptance evidence

- All frozen v0.1–v0.4 fixtures produce deterministic facts with valid source pointers.
- A v0.1 IK-bearing input is retained and reported as a mismatch without assigning v1 IK meaning.
- v0.3/v0.4 dimensions remain a validation-profile fact; v0.4 interaction remains a source declaration, not proof of host support or authorization.
- Existing sparse values and provenance-bearing effective defaults stay separate.
- Manifest bytes, asset bytes, opaque source payloads, and input archive remain unchanged.
- Existing importer tests and the repository's required CI pass.

## Review and rollback

Architect, Functional QA, Security Auditor, and Code Reviewer review the implementation independently. Revert the additive source-fact model, tests, and this document to roll back; existing import snapshots remain available.

## Decisions kept open

This proposal does not decide v1 semantics for legacy fields, the stable report/error schema, serializer/conversion behavior, capability identifier registration, support windows, runtime/platform matrix, license, or distribution/signing.
