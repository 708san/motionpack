# Frozen archive-reader compatibility fixtures

The immutable v0.1 and v0.2 packages are historical fuzz seeds. The v0.3 and v0.4 packages are compatibility fixtures generated from `examples/layered_plant_demo` and `examples/interaction_demo` by running:

```sh
python3 tests/build_compatibility_fixtures.py
```

The builder validates each example, includes only the manifest and referenced runtime assets, and uses stored ZIP entries with fixed metadata so the package checksums are reproducible. It never includes `source/` entries.

| Fixture | Source example | SHA-256 |
|---|---|---|
| `valid_v03.motionpack` | `examples/layered_plant_demo` | `06ad0b8b4b05e8212573784cbdda00a6c8dee9cfe8a9840888feb50cbf6611ea` |
| `valid_v04.motionpack` | `examples/interaction_demo` | `c98a270b566a6792748fc479a63af484fc1c9378d3a4e7c638db96704943bcb8` |

The archive-reader tests pin these hashes and verify direct and isolated reading across v0.1–v0.4. Update a frozen fixture hash only with explicit compatibility review.
