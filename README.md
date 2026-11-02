# MotionPack

**Engine-independent, editable 2D animation asset format and lightweight player — experimental project.**

> Public **pre-alpha** development repository. No open-source license has been selected yet. Source code is visible, but permission to copy, modify, or redistribute is not generally granted by visibility alone.

## Goals
- Separate original images, layers, masks, rigs, timelines, visual effects, variants and edit history.
- Keep source projects inspectable and non-destructively editable.
- Enable offline playback without a particular game engine or AI service.
- Build independent format, runtime, command-line tools, and optional AI authoring skills.
- Keep game rules and card-specific metadata outside the core asset format.

## Repository status

**Bootstrap stage (2026-11-02):** GitHub governance, eleven specialized Codex subagents, contributor guidance, and governance validation workflow are proposed in [PR #1](https://github.com/708san/motionpack/pull/1).

The existing local **v0.2-alpha demonstration** (two-bone IK / inverse kinematics, particle beam, variant switching, HTML preview, Python validator/packager) is **not yet committed to this repository**. The next step is a separate import after code and rights inspection. Do not treat this README as a claim that those tools can currently be run from the repository.

## Documentation
- [Agent and coding rules](AGENTS.md)
- [Governance and decision rights](docs/DEVELOPMENT_GOVERNANCE_V1.md)
- [Agent roles](docs/AGENT_ROLES.md)
- [GitHub workflow](docs/GITHUB_POLICY.md)
- [Security policy](docs/SECURITY_POLICY.md)
- [Quality policy](docs/QUALITY_POLICY.md)
- [Development roadmap](docs/ROADMAP_GOVERNED.md)
- [Contributing](CONTRIBUTING.md)
- [Vulnerability reporting](SECURITY.md)

## Safety and scope
The current format is experimental. Untrusted .motionpack packages, embedded SVG, ZIP archives, large images and effects must not be considered safe to parse until resource limits and security reviews are implemented. Native game engine adapters, robust mesh skinning and AI one-image auto-rigging are not yet available.

## Maintainer approval
AI agents may propose branches and draft pull requests; merging, making releases, choosing the license, or relaxing protections require the human maintainer's explicit approval.
