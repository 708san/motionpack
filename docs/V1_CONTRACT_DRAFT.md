# MotionPack v1 contract proposal (draft)

Status: **proposal only; not a stable format or implementation contract.** Prepared for Issue #120 and the maintainer-selected v1.0 scope: stable format, reader/validator, and a v1 writer with explicit confirmation before lossy saves. GUI and AI authoring are outside v1.0 core.

This proposal does not close Issue #4, approve asset rights, select a software license, or authorize a v1.0 release.

## Existing decisions carried forward

The following directions were previously approved and are not reopened here:

- v0.1–v0.4 remain readable through a read-only legacy importer.
- Preserve source payload bytes and sparse authored values. Keep effective defaults and their provenance separate.
- Retain ambiguous legacy data without interpreting it. In particular, v0.1 IK content does not gain v1 IK meaning from current runtime behavior.
- Require explicit confirmation before a write that loses or reinterprets data.
- Use the capability arrays required[] and optional[]; use reverse-domain extension keys; reject unknown core fields and unknown required capabilities; ignore an unknown optional capability only when the reader has an explicit safe-ignore rule; retain opaque data.

## Proposed v1 manifest envelope

A v1 package proposes these root fields:

| Field | Proposal | Status |
|---|---|---|
| format | Required string "motionpack". | Proposed |
| version | Required string "1.0". | Proposed |
| capabilities | Required object containing exactly required and optional arrays of unique printable ASCII identifiers. | Carries forward approved capability shape; exact constraints must be normative |
| id | Optional project identifier, preserving v0 packages that omit it. | Proposed; validation grammar is open |
| canvas, assets, nodes, clips, variants, defaults | Core visual-animation model. Initially retain v0.4 object shapes for fields whose meanings are fully specified. | Proposed; per-field semantics remain open |
| extensions | Optional object keyed by reverse-domain identifiers; values are opaque JSON retained without interpretation. | Proposed; key grammar and preservation rules need fixtures |

Example shape (illustrative, not yet normative):

```json
{
  "format": "motionpack",
  "version": "1.0",
  "capabilities": {
    "required": [],
    "optional": []
  },
  "canvas": { "width": 800, "height": 1000 },
  "assets": {},
  "nodes": [],
  "clips": {},
  "variants": {},
  "defaults": {},
  "extensions": {}
}
```

Unknown core fields are rejected. A reader may ignore an unknown optional capability only when that reader has an explicit safe-ignore rule for it. Opaque extension values are preserved, but their meaning is not implied. Capability presence does not establish reader support for all unrelated core fields.

## Proposed migration model

A v1 migration report should classify each source item as one of:

- **mapped** — represented by a v1 core field with a defined meaning;
- **opaque-preserved** — retained without assigning semantics, in an approved extension/payload location;
- **unsupported** — the writer cannot represent it under the selected output profile;
- **lossy** — omitted or changed, with the exact affected source pointer, payload identity, and reason.

Do not call a conversion playback-equivalent unless state/render comparisons establish that separately.

Initial mapping constraints:

- Map v0.1–v0.4 root and nested data only when the v1 contract explicitly defines the corresponding meaning. Keep authored omission distinct from effective values.
- Preserve v0.2–v0.4 IK only under the approved IK capability and only after v1 defines those fields. Keep spec-derived weight defaults separate from implementation-derived bend defaults.
- Keep v0.1 IK uninterpreted with a version-mismatch diagnostic.
- Preserve interaction flags as data-only opt-ins under the approved interaction capability. Do not introduce callbacks, scripts, URLs, or actions.
- Preserve original asset bytes. Validation profiles such as v0.3 SVG dimensions are source provenance, not runtime features.
- Preserve unknown legacy fields opaquely when a defined location exists; otherwise report them and require explicit loss confirmation before writing.
- Preserve source/ bytes separately from runtime assets. The disposition of other unreferenced archive members and ZIP container metadata remains open.

## Proposed loss-aware writer lifecycle

The writer should have a no-output preflight stage and a separate commit-to-disk stage:

1. Read a bounded source and produce an immutable migration plan.
2. Produce a deterministic field-level loss report, including JSON pointers and payload hashes where applicable.
3. Bind confirmation to the source digest and the exact migration-plan/loss-report digest.
4. Reject missing, stale, or incomplete confirmation before creating or replacing an output file.
5. Validate the resulting v1 manifest and package before writing.
6. Write to a new destination by default; do not replace the source package in place.
7. Re-read the output with the v1 reader and compare canonical manifest values, opaque extensions, and asset hashes.

Any source or plan change invalidates prior confirmation. A loss report must never claim that retaining opaque bytes means the field is supported.

The exact Python API and whether confirmation selects individual losses or accepts the complete report remain open. A proposed API must make the confirmation step explicit and difficult to call accidentally.

## Manifest-first read order

The integrated v1 reader should perform these steps in order:

1. Validate ZIP container metadata and resource limits without extracting entries.
2. Read only the bounded manifest.json.
3. Validate UTF-8/JSON, duplicate keys, depth and byte limits.
4. Run capability preflight; reject unsupported required capabilities here.
5. Validate the complete v1 core schema and extension policy.
6. Only then decompress referenced runtime assets and apply path, size, format and content checks.
7. Return an engine-independent model that keeps authored sparse values, opaque data, provenance and derived values distinct.

The current v0 archive reader reads referenced assets before semantic validation, so the v1 path must explicitly insert capability and core validation before its asset-read loop.

## Canonicalization and package reproducibility proposal

Recommended manifest rules:

- UTF-8 without BOM; reject duplicate keys, non-finite numbers, and invalid UTF-8.
- Deterministic object-key ordering; preserve array order.
- Use a documented number serialization rule and a canonical fixture set.

Recommended deterministic ZIP rules if byte-identical artifacts are required:

- fixed member order: manifest.json first, then asset/payload paths in normalized lexical order;
- fixed timestamps and portable regular-file permissions;
- one specified compression method and metadata policy;
- no unreviewed ZIP comments or extra fields.

Using ZIP_STORED is the strongest simple byte-reproducibility option across compressor versions, at the cost of larger packages. A fixed DEFLATE level may reduce size but can still vary across toolchains. These are tradeoffs for maintainer selection, not settled requirements.

## Decisions awaiting maintainer confirmation

1. **Core shape:** inherit v0.4 shapes for v1 fields where semantics are already defined, or redesign the schema.
2. **SVG dimensions:** require positive numeric-pixel width and height in v1 (recommended, following v0.3), or allow omission.
3. **Reproducibility:** require deterministic ZIP bytes as well as canonical manifest output (recommended for release checksums), or guarantee canonical manifest only.
4. **Additional normative rules:** specify identifier grammar; canvas/background and node dimension defaults; transform/anchor constraints; Z-order ties; keyframe interpolation; supported effect kinds and omitted burst count; IK omitted fields; supported asset media types; unknown archive-member handling; extension identifier grammar; and archive member metadata.
5. **Confirmation surface:** choose whether a caller confirms all reported losses or explicitly selects loss identifiers. In either case, confirmation binds to source and plan digests.

Until these choices are recorded, this file remains a design proposal. It must not be cited as the stable v1 specification.

## Planned follow-up

After maintainer choices and Architect approval:

1. Freeze the normative v1 schema and fixtures.
2. Integrate manifest-first capability/core validation into the v1 reader.
3. Implement deterministic loss reporting and explicit-confirmation writing.
4. Prove v0.1–v0.4 preservation, v1 read/write round trips, and separately reviewed visual compatibility.
5. Reassess all release-readiness gates; a merged specification or writer PR alone does not approve v1.0.
