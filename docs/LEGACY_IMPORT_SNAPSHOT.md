# Read-only legacy import snapshot (experimental)

Status: implementation proposal for the v1.0 importer work. This is a tooling API proposal, not a v1.0 package schema and not a stable public contract.

## Purpose

The first importer stage reads validated v0.1, v0.2, v0.3, or v0.4 packages into one engine-independent in-memory snapshot. It does not write, convert, render, or execute a package. A later, separately reviewed stage may define v1 serialization.

## Snapshot contents

`tools.legacy_importer.import_legacy_package(path, *, limits=None, timeout=30.0)` returns a snapshot containing:

- The detected source version, parsed manifest, and exact `manifest.json` payload bytes.
- A common asset view keyed by manifest asset ID, with each original asset path and immutable payload bytes. Snapshot mappings are read-only, nested parsed manifest objects are exposed as immutable mappings/tuples, and payloads are `bytes`.
- An entry map keyed by the accepted ZIP entry name. It contains the exact uncompressed payload bytes of every regular file entry, including referenced and unreferenced files and opaque `source/` files. Source entries remain in this map and a separate source-entry view; they are never runtime assets.
- Capabilities inferred from legacy content: `org.motionpack.ik.two-bone` when non-empty IK declarations are present, and `org.motionpack.interaction` when a node declares interaction settings.
- A v0.3 SVG-dimensions validation profile fact for v0.3 and v0.4 inputs. This is a validation rule, not a playback capability.
- A report with unrecognized top-level manifest fields (preserved verbatim), payload preservation totals, and the container metadata that the snapshot does not retain.

The importer preserves sparse fields as written. It does not inject defaults such as `loop: false` or IK weight `1` into the manifest. Interpretation of those defaults remains governed by the source-version rules in [FORMAT_SPEC.md](FORMAT_SPEC.md).

## Preservation and loss

All accepted regular-file payloads and the original manifest bytes are retained exactly as read. Parsed manifest objects are provided for inspection; the retained raw manifest bytes remain the preservation source of truth.

The snapshot does not preserve ZIP compression choices, timestamps, comments, extra fields, directory-only entries, or other ZIP container metadata. It cannot recreate an identical archive. It never writes back to the input path. A later converter must report any additional transformation or loss it introduces.

Unknown top-level manifest fields are listed in the report and remain present in the raw and parsed manifest. This first stage does not claim complete semantic classification of unknown nested fields. Such fields remain preserved and uninterpreted.

## Input and resource boundary

The importer uses the isolated archive reader by default. It retains payloads only after the ZIP reader checks path safety, entry types, entry count, archive size, per-entry sizes, total expanded size, compression ratio, manifest JSON, and referenced assets. Entry payloads are read under the existing reader limits; no ZIP member is extracted to a caller-selected path or decoded as an image by the importer.

The isolated worker response remains capped at 40 MiB. If the complete snapshot, including names and protocol framing, exceeds that ceiling, import fails with a resource-limit error rather than returning a partial snapshot. On macOS, the worker retains its documented timeout and result-size limits but has no whole-process hard memory guarantee. This API is not a complete OS sandbox.

The existing `read_package()` and `read_package_isolated()` behavior remains unchanged by default. Full entry retention is an explicit opt-in used by this importer.

## Acceptance evidence

- Read the frozen, checksummed v0.1–v0.4 fixtures through direct and isolated paths.
- Verify manifest bytes, each file payload, asset-ID mappings, source-entry separation, inferred capabilities, validation profile, and diagnostics.
- Verify source bytes remain opaque for arbitrary binary data, including nested archive signatures.
- Reject malformed or over-limit inputs without returning a partial snapshot.
- Confirm existing readers do not decompress source entries unless full retention is explicitly requested.
- Run the full repository checks and report exact commands/results.
