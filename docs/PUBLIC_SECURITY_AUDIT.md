# Public pre-alpha security status

Basic path traversal checks, limited SVG tag restrictions, size budgets and negative metadata tests exist. These do not constitute a hardened security audit.

Unresolved (Issue #4):
- Safe archive reader for untrusted ZIP entries, symlinks, duplicates and decompression bombs.
- Strict SVG handling, including XML entities, CSS/URL edge cases and hostile media decoding.
- Prevention of private authoring source and credentials leakage in published packages.
- Fuzzing, dependency review and resource exhaustion defense.

Untrusted packs must not be opened with a production assumption of safety.
