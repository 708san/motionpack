# Read-only legacy import snapshot (experimental)

Status: implemented experimental read-only importer API. PR #59 added the payload-preserving snapshot; PR #61 added its normalized v0.1–v0.4 view. This is a tooling API, not a v1.0 package schema or stable public contract.

## Purpose

The importer reads validated v0.1, v0.2, v0.3, or v0.4 packages into one engine-independent in-memory snapshot with a sparse normalized view. It does not write, convert, render, or execute a package. A later, separately reviewed stage may define v1 serialization.

## Snapshot contents

`tools.legacy_importer.import_legacy_package(path, *, limits=None, timeout=30.0)` returns a snapshot containing:

- The detected source version, parsed manifest, and exact `manifest.json` payload bytes.
- A common asset view keyed by manifest asset ID, with each original asset path and immutable payload bytes. Snapshot mappings are read-only, nested parsed manifest objects are exposed as immutable mappings/tuples, and payloads are `bytes`.
- An entry map keyed by the accepted ZIP entry name. It contains the exact uncompressed payload bytes of every regular file entry, including referenced and unreferenced files and opaque `source/` files. Source entries remain in this map and a separate source-entry view; they are never runtime assets.
- Capabilities inferred from legacy content: `org.motionpack.ik.two-bone` when non-empty IK declarations are present, and `org.motionpack.interaction` when a node declares interaction settings.
- A v0.3 SVG-dimensions validation profile fact for v0.3 and v0.4 inputs. This is a validation rule, not a playback capability.
- An immutable normalized view of canvas, assets, nodes, clips/tracks/effects, variants/defaults, IK, interaction fields, capability facts, sparse field presence, and source pointers. It preserves authored data without materializing defaults. See [NORMALIZED_LEGACY_MODEL.md](NORMALIZED_LEGACY_MODEL.md).
- A report with unrecognized top-level manifest fields (preserved verbatim), payload preservation totals, container metadata that the snapshot does not retain, and immutable `source_facts` recording the source format version, observed IK/interaction constructs, v0.1 IK mismatch, and v0.3/v0.4 SVG-dimensions validation profile. Each fact includes a source version and JSON Pointers. These are source observations only; they do not map to v1 semantics, required/optional capabilities, or runtime support.

The source-fact ledger is additive to the existing `capabilities`, normalized `capability_facts`, `effective_defaults`, and diagnostics. It does not replace or reinterpret those fields.

The importer preserves sparse fields as written and does not inject defaults into the manifest or sparse normalized view. Its separate `normalized.effective_defaults` view contains provenance-bearing values for documented and implementation-observed defaults. See [NORMALIZED_LEGACY_MODEL.md](NORMALIZED_LEGACY_MODEL.md) for the current per-version rules. These experimental values do not define v1 semantics or serialization.

## Preservation and loss

All accepted regular-file payloads and the original manifest bytes are retained exactly as read. Parsed manifest objects are provided for inspection; the retained raw manifest bytes remain the preservation source of truth.

The snapshot does not preserve ZIP compression choices, timestamps, comments, extra fields, directory-only entries, or other ZIP container metadata. It cannot recreate an identical archive. It never writes back to the input path. A later converter must report any additional transformation or loss it introduces.

Unknown top-level manifest fields are listed in the report and remain present in the raw and parsed manifest. This first stage does not claim complete semantic classification of unknown nested fields. Such fields remain preserved and uninterpreted.

## Input and resource boundary

The importer uses the isolated archive reader by default. It retains payloads only after the ZIP reader checks path safety, entry types, entry count, archive size, per-entry sizes, total expanded size, compression ratio, manifest JSON, and referenced assets. Entry payloads are read under the existing reader limits; no ZIP member is extracted to a caller-selected path or decoded as an image by the importer.

The isolated worker response remains capped at 40 MiB. If the complete snapshot, including names and protocol framing, exceeds that ceiling, import fails with a resource-limit error rather than returning a partial snapshot. On macOS, the worker retains its documented timeout and result-size limits but has no whole-process hard memory guarantee. This API is not a complete OS sandbox.

The default `read_package()` API uses the isolated worker and returns manifest-referenced assets only. `read_package_in_process()` remains available for explicit in-process parsing of trusted local inputs. Full entry retention remains an explicit opt-in used by this importer; it does not change normal reader behavior.

## Acceptance evidence

- Read the frozen, checksummed v0.1–v0.4 fixtures through direct and isolated paths.
- Verify manifest bytes, each file payload, asset-ID mappings, source-entry separation, inferred capabilities, validation profile, and diagnostics.
- Verify source bytes remain opaque for arbitrary binary data, including nested archive signatures.
- Reject malformed or over-limit inputs without returning a partial snapshot.
- Confirm existing readers do not decompress source entries unless full retention is explicitly requested.
- Run the full repository checks and report exact commands/results.
