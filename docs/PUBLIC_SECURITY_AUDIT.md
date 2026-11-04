# Public pre-alpha security status

Basic path traversal checks, SVG subset validation, size budgets and negative metadata tests exist. These do not constitute a hardened security audit.

Unresolved (Issue #4):
- The new experimental reader prechecks ZIP entry count and central-directory byte size, then checks paths, file types, duplicate/colliding names, declared sizes and compression ratios. Referenced assets are read with byte limits. It is not a production-hardened archive boundary; the standard-library ZIP parser is not isolated, and CPU/time defenses and fuzzing remain unverified.
- Complete SVG sanitization for arbitrary renderers, hostile raster media decoding and downstream renderer behavior.
- Secret content embedded in explicitly referenced runtime assets is not detected or filtered by the packager.
- Fuzzing, dependency review and resource exhaustion defense.

Untrusted packs must not be opened with a production assumption of safety.
