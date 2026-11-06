# Quality policy

## Functional
- Validate v0.1/v0.2 compatibility fixtures and v0.3 schema tests on every PR.
- Test deterministic IK and parent transforms.
- Run idle, fire, transform, variant and reset smoke tests.
- Verify offline package creation and local archive manifest integrity.

## Visual
- Node mock tests are not pixel-level or aesthetic evaluation.
- Until Issue #5 lands, human reviewers must inspect generated browser preview after visual-affecting changes.
- Do not claim natural whole-body motion, full mesh deformation or production performance without evidence.

## Performance
Track file size, preview size, load latency, frame duration and peak memory with fixed fixtures. Hardware/browser must be stated. No universal numerical target has yet been established.

## Done means
Applicable tests pass, compatibility is assessed, security impacts reviewed, known gaps documented, and maintainer approves merge.
