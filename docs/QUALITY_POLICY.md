# Quality policy

## Functional
- Read the SHA-pinned v0.1 archive fixture at `tests/fuzz_corpus/archive_reader/valid_v01.motionpack` and package/read the current v0.2 example on every PR; also run v0.3 schema tests.
- Test deterministic IK and parent transforms.
- Run idle, fire, transform, variant and reset smoke tests.
- Verify offline package creation and local archive manifest integrity.

## Visual
- Node mock tests are not pixel-level or aesthetic evaluation.
- The Issue #5 pilot captures the v0.2 preview in pinned Chromium on Linux at a fixed viewport and animation time. Five maintainer-reviewed reference images are checked in and gate later runs; screenshot artifacts from CI remain available to inspect changes.
- The current pilot covers idle, fire, transform, completed form change, and pointer IK. It does not establish cross-browser parity or subjective motion quality.
- The robot demo's v0.2 canvas and background are framed at 1000 × 1000 so the five captured states keep the full character and effects within the reference image.
- Human reviewers must still assess naturalness and artistic quality; pixel thresholds measure image changes only.
- Do not claim natural whole-body motion, full mesh deformation or production performance without evidence.

## Performance
The Issue #5 Playwright CI run measures package build time, package/preview bytes, archive-reader load time and peak process RSS for the SHA-pinned v0.1 archive and generated v0.2 example. It also reports browser navigation-to-images-ready time and 180 real `requestAnimationFrame` intervals after a 30-frame warm-up in pinned Chromium. The JSON artifact records fixture hashes, sample counts, runtime versions and metric definitions.
All values are report-only. Reader RSS includes the Python interpreter and is measured in a fresh reader process per fixture; browser frame intervals include host scheduling and page work, not isolated Canvas draw time. The runner host hardware can vary even when the container is pinned. No universal numerical target or regression gate is established.

## Done means
Applicable tests pass, compatibility is assessed, security impacts reviewed, known gaps documented, and maintainer approves merge.
