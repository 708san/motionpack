# Governed MotionPack roadmap

Targets are exploratory, not release commitments. This plan is reconciled with `main` at `d3e1e37`, which includes PR #38 (2026-11-08); update its evidence links as implementation and CI change.

## Current implementation status

| Area | Status | Evidence and limit |
|---|---|---|
| Experimental format | Implemented, verification incomplete | v0.1, v0.2 and v0.3 manifests, examples, validator and frozen v0.1 fixture exist. No stable v1.0 compatibility promise or migration tool exists. |
| Offline preview | Implemented, browser-specific | Packager emits a self-contained Canvas 2D preview. Cross-browser parity, mobile Safari/Chrome and real-device behavior are not established. |
| Motion | Partial | Keyframes, clips, variants, effects and two-bone IK work. No mesh skinning, blend graph, independent scale axes or authoring editor. |
| Package tooling | Partial | Validator, packager and bounded archive inspection exist. The ordinary reader is in-process; the isolated ZIP reader and optional raster decoder are opt-in worker processes, not complete OS sandboxes. |
| Untrusted input security (Issue #4) | Partial, open | ZIP, SVG and raster header checks, bounded fuzz targets and isolated worker APIs exist. Browser preview still uses browser image decoding. Issue #4's production-readiness acceptance has not been closed. |
| Visual and performance QA (Issue #5) | Pilot implemented, verification incomplete | Linux Chromium screenshot baselines and report-only timing/memory measurements exist. No mobile or cross-browser matrix, human motion-quality gate, or numeric performance thresholds exist. |
| Layered source workflow | Demonstrated, not a production authoring pipeline | A manually separated v0.3 plant sample preserves source and provenance notes. Import, masks, editable rigging, and stable authoring APIs are missing. |
| AI assistance and distribution | Not implemented / undecided | No AI authoring workflow or license selection. AI is optional and should follow stable authoring APIs; license choice requires maintainer decision. |

The isolated-reader Actions run [42455065352](https://github.com/708san/motionpack/actions/runs/42455065352) on this baseline is marked failed but has zero jobs, zero artifacts and no job logs. The same commit's functional, validation, security-negative and governance checks succeeded. The run cannot be retried through the available GitHub API. Its cause is unknown; it is not evidence of a reader test failure. A new successful Linux/macOS/Windows matrix run is required before claiming cross-platform verification.

## Phase A — stabilize the experimental baseline

1. Obtain a successful isolated-reader matrix run and retain the run URL and per-OS test results. If a later run fails, diagnose its actual job log before changing code.
2. Keep Issue #4 open. Resolve its remaining acceptance items in small changes with adversarial regression tests and independent security review. Track path races, memory containment gaps, SVG renderer limits, private source handling, and browser-native decoder exposure separately.
3. Maintain existing v0.1–v0.3 fixtures and run the current functional, negative, isolated-process, visual and performance-report checks.

**Exit evidence:** green required checks on a named commit; no unsupported claim of a complete sandbox or browser decoder isolation.

## Phase B — define runtime and compatibility contracts

1. Extract a stateless pose evaluator that accepts a manifest, clip, variant, and millisecond timestamp; preserve generated preview behavior through the existing `window.MotionPackPlayer` facade. **PR #38 merged into main as `d3e1e37`.**
2. Define the host-driven lifecycle controller contract and keep it experimental until it has been exercised and accepted; the API proposal is documented and received Architect review on the follow-up branch.
3. Review the proposed [v1.0 compatibility policy](COMPATIBILITY_POLICY_DRAFT.md) before stabilizing format or runtime APIs. Manage file-format, runtime and authoring-tool versions separately; document required/optional capabilities, migration, deprecation, unsupported-feature errors and fallback export.
4. Keep v0.1–v0.3 experimental. Specify whether/how they migrate into v1.0; keep frozen fixtures and compare both sampled state and rendered output.

**Exit evidence:** accepted runtime API proposal, compatibility policy, versioned fixtures and acceptance criteria. Any public format change requires Architect review, migration notes and regression fixtures.

## Phase C — reusable playback and interaction

1. Build on the evaluator to add a host-owned player controller and rendering adapters. A DOM-free controller prototype with per-instance clip/variant/time state, play/pause/resume/stop/seek, state queries and disposal is implemented on PR #39; preview-facade integration, loading/unloading, parameter updates, resizing and rendering adapters remain open.
2. Add pointer/touch input with canvas-to-logical coordinate mapping, then hit tests, dragging, long press and swipe. Keep host actions permissioned by the consuming application; never execute package JavaScript.
3. Separate logical canvas size from viewport policy (contain, cover, stretch, alignment and high-DPI scaling). Include 91:55 as a generic aspect-ratio test, not a product-specific feature.
4. Add an offline export path only after the player API and asset lifecycle are stable.

**Exit evidence:** independent instances, deterministic virtual-time tests, accessibility alternatives, no network requests, and visual checks for representative ratios. Playwright device emulation must be reported separately from physical iOS/Android testing.

## Phase D — richer motion

Add independent X/Y scale, easing and squash/stretch, then explicit transitions and interruption rules. Preserve existing track meanings. Consider mesh deformation and blended rigs only after authoring and runtime contracts can represent and test them. Every renderer-visible change needs visual review; aesthetic quality still requires a human.

## Phase E — authoring foundation

Stabilize programmatic import, non-destructive source retention, masks/layer editing, rig setup, keyframe and clip operations, preview, validation and reproducible export. Keep source provenance separable and make edit/save/reload information-preservation testable. Build a GUI only on the stable authoring API.

## Phase F — optional AI authoring

After authoring APIs and quality evaluation are stable, prototype a model-independent workflow for planning, segmentation, motion generation, validation and iterative correction. Preserve originals and edit history; require explicit consent for network transfer. Keep AI optional and outside the v1.0 core unless a later scope decision demonstrates it is necessary.

## Phase G — v1.0 release decision

Release only when maintainers approve all of the following:

- Stable format specification, capability profiles, extension rules and migration paths.
- Independent file, runtime and authoring-tool version policies and public API/deprecation rules.
- Frozen compatibility fixtures, read/write preservation checks, state comparisons and reviewed visual references.
- Security review of the reader, SVG/raster handling, process boundaries, dependency inventory and vulnerability contact/response process; documented residual risks.
- Supported-browser/device matrix backed by actual runs; performance budgets with repeatable thresholds; human visual and motion review.
- Offline runtime, examples, docs, checksums/distribution artifacts and a maintainer-approved software license.

Do not require every exploratory capability (GUI, AI, mesh deformation, native engine adapters) for v1.0. Prefer a small stable core with explicit capability reporting over silent feature loss.
