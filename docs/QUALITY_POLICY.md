# Quality policy

## Functional
- Validate v0.1/v0.2 compatibility fixtures and v0.3 schema tests on every PR.
- Test deterministic IK and parent transforms.
- Run idle, fire, transform, variant and reset smoke tests.
- Verify offline package creation and local archive manifest integrity.

## Visual
- Node mock tests are not pixel-level or aesthetic evaluation.
- The Issue #5 pilot captures the v0.2 preview in pinned Chromium on Linux at a fixed viewport and animation time. Screenshot candidates are review artifacts until a maintainer approves reference images; only reviewed reference images may gate later runs.
- The current pilot covers idle, fire, transform, completed form change, and pointer IK. It does not establish cross-browser parity or subjective motion quality.
- The existing robot demo draws beyond its 800 × 1000 canvas in some states; those pixels are clipped by the canvas and are part of the captured reference unless the demo framing is deliberately changed.
- Human reviewers must still assess naturalness and artistic quality; pixel thresholds measure image changes only.
- Do not claim natural whole-body motion, full mesh deformation or production performance without evidence.

## Performance
Track file size, preview size, load latency, frame duration and peak memory with fixed fixtures. Hardware/browser must be stated. No universal numerical target has yet been established.
The initial browser visual pilot does not yet measure performance; add report-only measurements separately before defining numerical gates.

## Done means
Applicable tests pass, compatibility is assessed, security impacts reviewed, known gaps documented, and maintainer approves merge.
