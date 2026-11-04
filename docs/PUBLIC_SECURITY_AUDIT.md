# Public pre-alpha security status

Basic path traversal checks, SVG subset validation, size budgets and negative metadata tests exist. These do not constitute a hardened security audit.

Unresolved (Issue #4):
- The new experimental reader prechecks ZIP entry count and central-directory byte size, then checks paths, file types, duplicate/colliding names, declared sizes and compression ratios. Referenced assets are read with byte limits. A small deterministic archive-byte mutation smoke test checks that each input is rejected or returns a dict manifest whose asset IDs match the returned byte-valued assets; at least one mutation must be rejected. Sustained/coverage-guided fuzzing remains unverified. It is not a production-hardened archive boundary; the standard-library ZIP parser is not isolated, and CPU/time defenses remain unverified.
- Complete SVG sanitization for arbitrary renderers, hostile raster media decoding and downstream renderer behavior. `.png`/`.jpg`/`.jpeg`/`.webp` asset paths receive format-specific header dimension checks before decode and share configured dimension/pixel limits. Animated WebP canvas and frame areas are counted, but frame image data is not decoded; JPEG DNL height remains unsupported, content under another extension is classified by that extension, and no decoder is isolated.
- Secret content embedded in explicitly referenced runtime assets is not detected or filtered by the packager.
- Sustained fuzzing, dependency review and resource exhaustion defense.

Untrusted packs must not be opened with a production assumption of safety.
