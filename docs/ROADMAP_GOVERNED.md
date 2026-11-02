# Governed development roadmap (working draft)

## Bootstrap — now
- Public repository and governance / role definitions in draft PR.
- Establish least-privileged GitHub Actions, templates, and review practices.
- Import reviewed v0.2-alpha code and examples; enable functional validation in CI.
- Define a license before releasing redistributable packages.

## v0.3 — image-to-editable-asset vertical slice
- Preserve source image, isolate editable visual parts and background.
- Provide editable manual corrections to segmentation and rigging.
- Attach 2-bone IK and three demonstrable clips: idle, aim and beam.
- Render offline and re-open the same asset package; regression and security tests.

## v0.4 — natural motion and transformation
- Weighted meshes and skeletal blending, more joints and constraints.
- Motion blending, visual effect composition and form transitions.
- Objective functional checks + visual examples and measured performance.

## v0.5 — authoring automation
- Independent deterministic tools first, AI skills/agents later.
- Natural-language commands translate to editable, reviewable changes.
- Authoring AI remains optional; runtime never requires an AI service.

## Towards v1.0
- Stable spec/versioning, compatibility suite, hardened parser and security review.
- Lightweight browser runtime and documented adapters where implemented.
- Separate packaging/release of format spec, runtime, tool CLI and optional authoring skills.

Milestone dates are intentionally unspecified; scope and measured acceptance criteria govern readiness.
