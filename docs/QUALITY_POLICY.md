# Quality policy

## Functional
- Validate v0.1/v0.2 compatibility fixtures and v0.3 schema tests on every PR.
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
Track file size, preview size, load latency, frame duration and peak memory with fixed fixtures. Hardware/browser must be stated. No universal numerical target has yet been established.
The initial browser visual pilot does not yet measure performance; add report-only measurements separately before defining numerical gates.

## Done means
Applicable tests pass, compatibility is assessed, security impacts reviewed, known gaps documented, and maintainer approves merge.
