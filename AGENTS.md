# MotionPack — development instructions (repository root)

## Product contract
- MotionPack is a generic, editable, engine-agnostic animated visual asset format, not a card-game format.
- The package must remain usable without AI services, proprietary editor software or network access.
- Source images, masks, layer graphs, rigs, animations, variants and edit provenance remain separable and non-destructive.
- Unknown and optional features must fail safely; keep legacy fixtures working when adding capabilities.
- Keep format, runtime, CLI/tools and optional authoring AI skill independently distributable.
- No arbitrary executable scripts, remote loading, shader code or external URLs from untrusted manifests without an explicit, reviewed opt-in architecture.

## Entry points
- `docs/DEVELOPMENT_GOVERNANCE_V1.md`: decisions, escalation, required gates.
- `docs/AGENT_ROLES.md`: ownership and delegation rules.
- `docs/GITHUB_POLICY.md`: issue, branch, PR, merge, release process.
- `docs/QUALITY_POLICY.md`: functionality, visual fidelity, performance and compatibility.
- `docs/SECURITY_POLICY.md`: threat model, input and supply-chain safety.
- `docs/ROADMAP_GOVERNED.md`: milestones and release readiness.
- `docs/decisions/0001-governance.md`: accepted initial design decision.
- `docs/REPOSITORY_CREATION.md`: first-time GitHub setup.

## Before editing
1. Read the related spec, architecture, affected code and tests. For public-format changes read `docs/FORMAT_SPEC.md`.
2. For nontrivial work, record a concise plan, scope, acceptance criteria, and a rollback path in an Issue/PR (or draft it locally if not yet connected).
3. Keep one accountable implementer per file set; use subagents for bounded investigation, testing and review. Do not assign multiple editing agents the same files concurrently.
4. No change to the public `.motionpack` contract without versioning, migration/compatibility consideration, fixtures and architect review.
5. Do not silently overwrite source assets or remove their provenance. Do not introduce gameplay terms into the format/runtime.

## Repository baseline
- PR #1 established governance and development-agent definitions.
- PR #3 adds experimental v0.1/v0.2 runtime, examples, validation, build tools, and executable CI. Follow the commands in README when these files are present.
- Treat documentation as current only for its stated supported subset. Production-ready untrusted package import, complete SVG sanitization, visual regression baselines and automatic asset authoring remain future work (Issues #4 and #5).

## Test and evidence
- Baseline (as provided by v0.2-alpha):
  `python tools/validate.py examples/robot_ik_demo`
  `python tools/package.py examples/robot_ik_demo --out /tmp/motionpack_build`
  `node tests/ik_test.js`
  `node tests/runtime_ik_smoke.js`
  `node tests/runtime_smoke.js`
  `python -m unittest discover -s tests -v`
  `python -m unittest discover -s tests -p test_isolated_archive_reader.py -v` (Linux/macOS/Windows matrix)
  `python -m unittest discover -s tests -p test_isolated_raster_decoder.py -v` (requires optional Pillow dependency; Linux/macOS/Windows matrix)
- Test command names may evolve, but record exact commands and real results in the PR.
- Unit tests are not evidence of visually natural motion. Visual tests and humans must verify appearance where relevant.
- Do not assert a security check, UI run, performance result or compatibility test passed unless actually executed.

## Review / approval boundaries
- Main/implementers create code. QA, security and review agents report evidence and requested changes separately.
- Agent role instructions do NOT confer GitHub permissions or isolate filesystem access. Use GitHub rulesets, CI and approvals for enforcement.
- A human maintainer must authorize: public release, license selection, production credential changes, destructive migrations, security-rule relaxation and high-risk dependency/network additions.
- Never push to `main` directly or publish from an agent as an automatic side effect of completing a task.

## Communication
- Report: changed files, behavior, risk, test commands/results, known gaps and next suggested action.
- In Japanese-facing summaries, explain technical abbreviations on first mention.
- Prefer minimal, clear instructions; use detailed docs and specialized skills rather than making this file enormous.
