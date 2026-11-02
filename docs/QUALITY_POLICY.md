# Quality policy (draft v1)

## Independent acceptance gates
- **Functional QA:** correct parsing, validation and animation state changes; deterministic replay where specified; unit/integration tests.
- **Compatibility QA:** existing supported fixtures remain valid; every format change declares migration and version impact.
- **Visual QA:** representative screenshots at fixed times; missing texture/mask, clipping, flicker, and joint distortion reviews.
- **Performance QA:** reproducible package size, parse/load time, memory and frame timing with recorded hardware/browser; no invented benchmarks.
- **Security QA:** malformed/untrusted ZIP, JSON, SVG and images; file traversal, unbounded expansion/allocations, hostile URLs; supply-chain checks.
- **Documentation:** examples and commands agree with checked-in code.

## Requirements for pull requests
- List exact test commands and pass/fail results; do not claim visual or security coverage from unit tests.
- New public format features require spec, fixture and backward compatibility consideration.
- Critical and high-severity security findings block distribution until addressed or documented human exception.
- Failures must include a minimal reproducible case and rollback plan.

## Initial staged gates
Phase 1: syntax/configuration checks and function tests once runtime is imported.
Phase 2: adversarial malformed inputs and compatibility tests.
Phase 3: pixel/reference visual regression and quantified performance budgets.
Actual budgets and tolerances must be agreed using baseline measurements, not guessed.
