# Experimental v1 capability preflight

Status: internal, experimental prerequisite for a future v1 reader. This helper is not part of the v0.1–v0.4 archive reader, does not make a v1 package playable, and does not freeze the v1 format.

`tools.v1_capability_preflight.preflight_v1_capabilities()` accepts bounded raw UTF-8 manifest bytes and checks the proposed `capabilities.required[]` and `capabilities.optional[]` arrays before returning a small immutable result. It performs no ZIP access, asset read, network request, or playback initialization. A future v1 package reader must call this preflight after safely reading the manifest and before reading referenced assets or constructing a player. That reader integration is not implemented here.

The prototype recognizes the two previously approved identifiers:

- `org.motionpack.ik.two-bone`
- `org.motionpack.interaction`

Recognition is not proof that a particular runtime supports the capability. Callers provide the runtime's supported set. An unsupported required capability raises `UnsupportedRequiredCapability`. An unsupported optional capability raises `UnsafeOptionalCapability` unless the caller supplies an explicit per-capability safe-to-ignore rule. The helper does not treat every unknown optional capability as safe.

The helper rejects a missing/malformed declaration, duplicate identifiers, identifiers repeated across the arrays, duplicate JSON object keys, non-standard JSON constants, invalid UTF-8/JSON, manifests over 1,000,000 bytes, and JSON nesting deeper than its operational limit of 128 levels. The byte and nesting limits constrain this prototype; they do not establish public-format limits. It does not interpret extension payloads or define their preservation. Identifier grammar, whether the declaration is mandatory in the final v1 schema, extension storage, capability registry ownership, and the safe-to-ignore rules remain open design decisions.

Run the focused checks with:

```sh
python3 -m unittest tests.test_v1_capability_preflight -v
```
