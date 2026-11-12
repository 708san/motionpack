# v0.1–v0.4 to v1.0 migration semantics (proposal)

**Status: non-normative design proposal; maintainer-approved migration handling recorded 2026-11-10.** This document uses the merged experimental read-only importer and repository fixtures as evidence. It does not define a v1 manifest, serializer, converter, or stable compatibility promise.

## Purpose and evidence labels

Prepare a version-aware interpretation boundary before v1 serialization. Every statement is marked as one of:

- **Documented rule** — stated in FORMAT_SPEC.md for the indicated source version.
- **Observed implementation** — behavior in the current validator, importer, evaluator, or preview; not automatically a format guarantee.
- **Proposed v1 interpretation** — a candidate semantic mapping that still requires maintainer approval.
- **Maintainer-approved migration policy** — an approved handling rule for future migration planning; it is not a normative format or serializer contract.
- **Unresolved** — evidence or a policy decision is insufficient.

Primary evidence: FORMAT_SPEC.md, V0_FEATURE_INVENTORY.md, NORMALIZED_LEGACY_MODEL.md, tools/legacy_importer.py, tools/validate.py, runtime/evaluator.js, runtime/ik_solver.js, and the SHA-pinned v0.1–v0.4 fixtures. External packages and assets not represented by this repository have not been inventoried.

## Three preservation layers

1. **Source bytes** — the importer retains exact manifest bytes and accepted regular-file payload bytes, including opaque source/ and unreferenced entries. This supports exact recovery of those individual payloads, not reconstruction of the original ZIP archive.
2. **Sparse normalized view** — the imported manifest and normalized records retain authored values and field presence. Missing fields stay missing. This is the current read-only importer contract.
3. **Effective semantic interpretation** — when an effective value is exposed, it appears in a separate provenance-bearing view after applying a documented or implementation-derived rule. It never overwrites the source or sparse normalized view.

**Maintainer-approved separation rule (2026-11-10):** keep authored values and field presence in the sparse normalized view. Any effective value derived from a default belongs in a separate interpretation view and carries its source version, source JSON pointer or archive path, whether the field was authored, the applied rule identifier, whether the rule is documented or implementation-derived, and a confidence/status. Never write a derived value back into the sparse view or source. If no defensible rule exists, expose no effective value and report the uncertainty.

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

### Proposed report actions with maintainer-approved handling policies (2026-11-10)

- **continue** for safely preserved and understood data.
- **warn** for implementation-derived defaults, version/spec mismatches, and ambiguous data that remains preserved but uninterpreted. The read-only v1 migration import may continue in these cases.
- **require-confirmation** before any future save that transforms or drops information. Without explicit confirmation before saving, do not produce a lossy save; preserve the original or cancel that save. Confirmation authorizes only the specified information loss and does not authorize semantic interpretation of ambiguous data.
- **fail-import** for invalid, security-rejected, or resource-limit-exceeding input and, in v1, an unknown required capability before asset loading or playback.

**Still unresolved:** which documented or implementation-derived rules are appropriate v1 semantic defaults, and whether the proposed report action names/fields should become a public API.

## Version-by-version mapping proposal

| Source | Evidence | Sparse normalized view | Proposed effective v1 view / report | Status |
|---|---|---|---|---|
| Format envelope / version | **Documented rule:** v0.1–v0.4 use format=motionpack with explicit version. | Preserve exact source version and raw bytes. | Import profile is selected from source version; do not rewrite the legacy version. Unsupported version is a structural rejection, separate from semantic loss. | Proposed. |
| Canvas | **Documented/current:** logical pixel width/height; validator constrains integer range 1–8,192; optional background. | Preserve authored dimensions/background and presence. | Map dimensions as logical canvas units only if the v1 schema approves units; absent background stays unspecified unless a renderer profile supplies a traced fallback. Validator ceilings are tool limits unless made normative. | Units/default unresolved. |
| Assets | **Documented rule:** local SVG/PNG/JPEG/WebP paths; remote URLs rejected; source/ is reserved from runtime references. | Preserve ID/path mapping and exact bytes; opaque source/unreferenced files remain separate. | Map only supported asset declarations. Keep extension-based parser choice and reader constraints classified as tool behavior, not format meaning. | Proposed. |
| Node graph and transforms | **Inventory evidence:** parent graph, position, rotation, opacity, uniform scale, anchor, Z, optional width/height; the preview uses intrinsic image dimensions when size is omitted. **Maintainer-approved S3 direction:** compose parent-local transforms from root to node; globally draw by ascending Z, with omitted Z=0 and later declaration order in front for ties; parent opacity is not inherited. | Preserve sparse authored values, IDs/references, declaration order, and field presence. Keep effective defaults in a separate provenance-bearing view. | Apply root-to-node parent-local transform composition. Effective defaults are x/y/rotation=0, scale/opacity=1, anchor=[0.5,0.5]; omitted drawable width/height use the referenced image's intrinsic dimension. Draw all drawable nodes by ascending global Z (omitted Z=0; later declaration wins ties); do not inherit parent opacity. | Approved direction; numeric domains/invalid-value behavior, negative-scale support, residual graph rules, and renderer pixel equivalence remain unresolved. |
| Keyframe tracks and timing | **Inventory evidence:** milliseconds; node properties include x, y, rotation, opacity and uniform scale; the evaluator currently applies smoothstep and endpoint holds. **Maintainer-approved S4 direction:** positive-integer duration in milliseconds; every track has at least one key; finite key times within inclusive [0,duration], strictly increasing without duplicates; finite numeric key values; smoothstep for every animated numeric property, with rotation interpolated as a scalar; nearest-key hold outside the keyed span; omitted v1 `loop` defaults to false; requested sample time must be finite and nonnegative, looping time wraps modulo duration, and non-looping time clamps to duration; exact duration wraps to zero for looping clips and samples/holds the final pose for non-looping clips. The host owns ended notifications and next-clip selection. | Preserve each track/keyframe, ordering, and sparse field presence, including omitted `loop`. | Map sampling with u=(t-t0)/(t1-t0) and v=v0+(v1-v0)*u*u*(3-2*u) between adjacent keys; hold nearest endpoint outside the keyed span. Reject empty key arrays and negative/nonfinite requested times. Apply effective loop=false when omitted without materializing that default into source data. For looping clips, normalize time modulo duration; for non-looping clips, clamp to duration. | Approved direction; duration maximum, fractional-ms precision, property ranges/invalid-value behavior, and effect/IK timing remain unresolved. This does not define a host scheduling API or pixel equivalence. |
| Declarative effects | **Documented rule:** beam, ring and burst primitives, timed on nodes; effects are visual and do not define gameplay results. **Observed implementation:** omitted burst count defaults to 28; the preview uses `fx.count ?? 28`, so the default applies only when count is absent and authored zero remains zero (covered by `tests/runtime_smoke.js`). | Preserve declared type/parameters, field presence, and authored count values. | The experimental importer exposes 28 only for omitted burst count as an implementation-derived effective value. It preserves authored zero without a missing-field projection; the preview draws no particles for authored zero, as verified by `tests/runtime_smoke.js`; this is observed renderer behavior, not a normative v1 rule. Do not elevate this to a format or v1 default. | Importer projection implemented experimentally; v1 mapping and normative authored-zero semantics remain unresolved. |
| v0.1 IK declarations or tracks | **Observed implementation:** current validator/runtime accept and process IK without a version gate. **Documented rule:** IK is introduced in v0.2. | Preserve source IK records. The current v0.x snapshot may continue to report its existing observed capability and mismatch diagnostic as implementation evidence; that report does not establish v1 capability or meaning. | For v1 migration, preserve the records, warn about the v0.2-spec mismatch, and leave the construct semantically uninterpreted; do not infer the v1 two-bone IK capability from this ambiguous v0.1 case. The current v0.x runtime/importer behavior is unchanged. | Maintainer-approved v1 handling (2026-11-10); does not revise the experimental importer implementation. |
| v0.2 IK | **Documented rule:** two-bone IK; absent weight defaults to 1 and runtime clamps finite weight to [0,1]. | Preserve authored chain/track fields and presence. | The experimental read-only importer now exposes omitted chain weight=1 for source versions v0.2–v0.4 with rule provenance; v0.1 IK remains uninterpreted under the approved mismatch policy. This importer view does not settle the v1 semantic mapping. Clamping is runtime behavior and must not silently rewrite source. | Importer projection implemented experimentally; v1 mapping remains proposed. Confirm complete IK field mapping before serializer. |
| v0.2 IK bend | **Observed implementation:** current validator/runtime behave as if omitted bend is 1. | Preserve authored field presence. | The experimental importer now exposes omitted bend=1 for v0.2–v0.4 with `rule_origin=implementation`. This is not a format-spec guarantee and does not settle v1 semantics; do not materialize it into source. | Importer projection implemented experimentally; v1 mapping remains unresolved. |
| v0.3 validation profile | **Documented rule:** referenced SVG roots require bounded positive numeric px dimensions. | Preserve SVG bytes and report v0.3 profile fact. | Treat as source validation profile, not an animation/runtime capability. Rejection under current reader limits is reported separately from format meaning. | Proposed. |
| Sparse variants | **Documented/inventory evidence:** variants are sparse visual node overrides. | Keep only authored override fields, presence and source pointers. | Apply an overlay only where the source declares one; do not fill omitted fields from guessed defaults. | Proposed; full merge/order semantics need mapping against evaluator behavior. |
| v0.4 interaction | **Documented rule:** per-node hover/tap/click booleans are opt-in data-only host notifications. Hover reports enter/leave transitions, not every movement; the last-moving primary mouse/pen pointer owns the single target and a leave from a former owner does not clear it. Tap requires primary touch down/up on the same top node (release elsewhere or a different top node cancels; pointercancel cancels; there is no movement threshold). Native click is mouse/pen only; touch-generated clicks are excluded; a host may map its focused accessible control to keyboard activation. Hit regions are transformed rectangles including transparent pixels, omit zero opacity, and top drawable blocks input even when interaction is off. | Preserve flags, omission, source pointers, and observed capability. | The experimental importer exposes omitted v0.4 interaction flags as effective `false` with provenance; explicit flags remain sparse. This is not a v1 schema or renderer/host support claim. Do not infer host action or authorization from declaration. | Importer projection implemented experimentally; v1 mapping and renderer/host conformance remain unresolved. |
| SVG subset and rendering | **Observed tool behavior:** bounded static allowlist, same-document gradient references, namespace restrictions and size limits; generated preview uses browser image decoding plus Canvas 2D. These checks are not a sanitizer guarantee for arbitrary renderers. | Preserve SVG asset bytes and source metadata; validation profile remains separate from payload semantics. | Record accepted subset/profile and renderer separately. Do not claim browser parity, secure decoding, or universal SVG semantics. | Renderer profile and security guarantees remain out of v1 mapping; Issue #4 open. |
| Raster image inspection | **Observed tool behavior:** extension-based PNG/JPEG/WebP header dimensions; incomplete image-data validation; WebP frame accounting and configured pixel ceilings. | Preserve exact payload; store any inspection result as evidence, not decoded content. | Treat parser ceilings/results as tool validation metadata, not format-wide validity or decoder safety guarantees. | Tool profile only, subject to security review. |
| Missing clip loop | **Documented v0.x rule and maintainer-approved v1 S4 direction:** absent `loop` means effective false; a present value must be boolean. | Retain absence vs explicit false and the source version/rule provenance. | Apply effective v1 `loop=false` when omitted, while preserving the authored omission and never materializing it into source data. | Approved v1 direction; exact duration and key precision limits remain open. |
| Missing canvas background | **Documented/current:** optional; no universal fallback is established here. | Preserve omission. | Leave unspecified unless a target renderer profile defines a traced fallback. | Unresolved. |
| Missing node width/height | **Observed implementation:** the preview uses intrinsic asset dimensions when a drawable size is omitted. **Maintainer-approved S3 direction:** each omitted drawable width/height uses the referenced image's intrinsic dimension for that axis. | Preserve authored omission and the asset relationship; keep any effective dimension separate from the sparse source value and attach its provenance. | Resolve an omitted drawable dimension from the referenced image's intrinsic dimension for that axis; never write the derived value back into source data. | Approved direction; renderer pixel equivalence and asset-specific decoding/resource behavior remain separate profile questions. |
| Effects and renderer defaults | **Observed implementation:** burst count defaults to 28; interpolation and boundary details are implementation-specific. | Preserve source declarations and omissions. | Do not make renderer defaults normative by copying them into v1 semantics without approval; report profile-dependent interpretation. | Unresolved. |
| Unknown legacy fields | **Observed implementation:** unknown top-level fields are listed; nested fields remain in the parsed manifest and a general diagnostic says they are not semantically classified. Individual nested unknown locations are not currently identified. | Preserve raw manifest bytes and parsed fields; current importer does not classify every nested location. | Keep opaque and uninterpreted unless a reviewed mapping exists. A future detailed report may identify JSON Pointers; never silently drop data on save. | Proposed future reporting detail; do not claim it exists today. |
| Unknown v1 core fields / extensions | **Maintainer-approved direction, recorded in COMPATIBILITY_POLICY_DRAFT.md (2026-11-09):** unknown core fields are rejected; reverse-domain extensions hold opaque data; capability arrays separate required/optional. | Does not change v0.x manifests. | Unknown required capability fails before assets/playback; optional handling only where omission is declared safe; extension preservation required for round-trip. | Approved direction; full v1 schema remains draft. |
| Opaque source and unreferenced payloads | **Observed importer behavior:** accepted regular-file payloads, including source/ and unreferenced entries, are retained as opaque bytes. | Keep separated from runtime asset declarations and do not decode. | Preserve as payload-store entries; report semantic role as unknown unless manifest/provenance identifies it. | Proposed. |
| ZIP container details | **Observed importer limit:** compression representation, timestamps/permissions, comments/extra fields, directories, and entry ordering are not retained. | Not represented in snapshot. | Report container-unavailable; do not claim byte-identical archive round-trip. | Required limitation. |
| Tool limits and security rejection | **Observed implementation:** reader byte/entry/ratio/time/process constraints can reject a package independently of its intended visual meaning. | Failure returns no partial snapshot. | Report rejection separately from semantic unsupported/loss; no partial effective view. | Proposed; Issue #4 remains open. |
| Archive reader resource policy | **Observed tool behavior:** archive/entry/manifest/asset/ratio limits are configurable operating limits; isolated wrapper imposes timeout/response bounds and platform-specific memory controls, is not an OS sandbox, and has path-race/platform limitations. | Snapshot records accepted payloads only and reports container fields not retained; a rejected read yields no snapshot. | Report configured limits and rejection reason separately from source semantics. Do not encode tool limits as v1 format maxima or claim sandboxing. | Tool/conformance profile unresolved; Issue #4 open. |
| Source workflow and provenance | **Observed example:** layered plant source and manual separation notes demonstrate workflow, not a formal provenance schema or automated authoring pipeline. | Preserve source/ payloads opaquely; do not infer layer-to-source lineage without explicit metadata. | Carry only explicit provenance records; classify undocumented lineage as unavailable/uninterpreted. | Provenance schema remains separate work. |
| Offline preview and renderer support | **Observed implementation:** generated preview embeds referenced files and uses browser images/Canvas; no supported browser/version matrix or cross-renderer parity guarantee. | Preserve preview-independent package data; preview is not encoded as a format capability. | Declare renderer profiles/support separately from source feature facts. | Runtime/platform support remains a release decision. |

## Capability facts versus target support

Keep three facts separate:

1. **Observed source capability** — a construct is present in the manifest.
2. **Version/profile rule** — a source-version requirement applies, such as v0.3 SVG dimensions.
3. **Target support** — the selected v1 reader/runtime actually implements the construct.

The v0.1–v0.4 importer can infer source facts but cannot claim target support. The approved capability identifiers are org.motionpack.ik.two-bone and org.motionpack.interaction. Their approved direction does not settle the full v1 schema, identifier registration policy, or every version-to-capability derivation rule.

## Maintainer-approved migration handling (2026-11-10)

1. Keep sparse authored values and field presence separate from a provenance-bearing effective-values interpretation. Derived defaults never overwrite the source or sparse view.
2. Preserve ambiguous and specification/implementation-mismatch data, warn, and do not assign v1 semantics to it. This supersedes the earlier proposal to interpret v0.1 IK compatibly for v1 migration. It does not change the existing v0.x runtime or normalized importer behavior. Explicit confirmation for a lossy save cannot authorize assigning v1 semantics to ambiguous data.
3. Require explicit confirmation before any future save that transforms or drops information. Without that confirmation, no lossy output is produced.

## Remaining maintainer decisions

1. Which documented or implementation-derived source behaviors should become v1 semantic defaults, and which must remain profile-dependent or unresolved?
2. What exact v1 fields, stable diagnostic identifiers, and error/report model consume these policies? This proposal does not define or implement them.
3. Which source-version/profile facts can be converted to required/optional v1 capabilities without overstating target support?

## Acceptance and next step

Before this proposal is treated as accepted:

- Review every row against the full feature inventory and four pinned fixtures.
- Have Architect verify format/runtime boundaries and Functional QA verify that each claim has fixture or code evidence.
- Resolve the remaining maintainer decisions above before designing a serializer.
- Keep any v1 schema, converter, and serializer in a later issue/PR with migration fixtures and no-silent-loss tests.

Rollback: remove this non-normative proposal. It changes no package, code path, legacy acceptance rule, or fixture.