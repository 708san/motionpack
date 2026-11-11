# v1.0 Release Readiness and Announcement Evidence

**Status: not approved for v1.0 release or announcement.** This register maps the governed release gates to evidence and claim limits. It does not change the format contract, select a license, approve residual security risks, or authorize publication.

Audited against GitHub `main` at `60bd3ad0fc89e02ab70635cb6e1d3baf59c5a673` on 2026-11-12. Recheck every status against the release candidate before publication.

## Release gates

| Gate | Current evidence | Status | Evidence required to close |
|---|---|---|---|
| Stable v1 format, capability profiles, extensions, migration paths | [FORMAT_SPEC.md](FORMAT_SPEC.md) remains pre-alpha. [COMPATIBILITY_POLICY_DRAFT.md](COMPATIBILITY_POLICY_DRAFT.md) and [V1_CAPABILITY_PREFLIGHT.md](V1_CAPABILITY_PREFLIGHT.md) are proposals/prototypes; the preflight is not integrated into a package reader. | Open | Maintainer-approved versioned specification; integrated required-capability rejection before asset loading; extension and resource profiles; documented errors and migration guidance. |
| Versioning and public API policy | Compatibility policy describes proposed independent format, runtime, and authoring-tool versioning, but stable API and support windows remain undecided. | Open | Approved format/API lifecycle, deprecation and support windows, platform support, and public API boundaries. |
| Legacy compatibility and preservation | Read-only importer covers experimental v0.1–v0.4 and preserves source payloads. Frozen version fixtures exist. It does not serialize v1, and v1 save/reload and conversion are not established. | Partial | Reviewed v1 mapping and loss report; versioned conformance fixtures; state and visual comparisons; preservation and round-trip evidence for supported fields; explicit confirmation for lossy output. |
| Untrusted-input security | Bounded ZIP inspection, SVG/raster checks, fuzz targets and isolated workers exist. [Issue #4](https://github.com/708san/motionpack/issues/4) remains open. Workers are defense in depth, not OS sandboxes; browser-native image decoding is not isolated. | Open | Complete the approved Issue #4 acceptance work or explicitly document and obtain maintainer acceptance of each residual risk; independent security review; dependency review; vulnerability contact and response process. Do not claim a complete sandbox. |
| Browser/device support and performance | Visual regression references use pinned Linux Chromium. Performance is report-only; supported browser/device matrix and numeric budgets are absent. | Partial | Maintainer-approved support matrix tested on the named environments; repeatable performance thresholds with recorded runs and artifacts. |
| Artwork and motion quality | Five robot states have regression references. The seal sample was approved only as an additional example; it does not approve the product's overall art or motion quality. | Partial | Human review of representative assets and motion for composition, silhouette, palette/contrast, target-size legibility, layer editability, timing, naturalness and interaction feedback; record artifact, states, viewport and decision. |
| Software license and distributed asset rights | No software license is selected. Asset provenance notes exist for examples but do not constitute a complete rights inventory for release contents. | Open | Maintainer selects a software license; inventory every distributed asset and its author, source, license/permission and required attribution; resolve unknown rights before distribution. Treat software and asset licensing separately. |
| Release artifacts and integrity | Compatibility fixture hashes and dependency provenance records exist, but a v1 release package, release checksums and complete distribution provenance are not evidenced. | Open | Reproducible release artifact; published checksums and provenance; release notes and install/use/security documentation reviewed against the actual artifact. |
| AI authoring claims | AI authoring is not implemented and is not a v1.0 core requirement. | Not a release gate unless claimed | Do not claim AI authoring is available without a reviewed end-to-end example that produces an editable package, preserves originals/provenance, supports human correction, discloses off-device data transfer, and provides a non-AI route. |

## Announcement claim limits

Until the gates above are closed and the maintainer approves release:

- Describe MotionPack as experimental/pre-alpha and the browser player as a reference preview.
- Claims about offline preview, implemented v0.x formats, bounded reader behavior, screenshots, or examples must be scoped to the exact implementation and tests that support them.
- Do not claim v1 compatibility, production-safe handling of arbitrary untrusted packages, a complete sandbox, cross-browser/device parity, a complete artwork-quality review, or AI authoring.
- Public repository visibility does not grant reuse rights. State the selected software license and asset-rights limits only after those decisions and inventories are complete.

## Final release decision

The release manager should attach links to the release-candidate commit, required CI runs, security and visual reviews, compatibility evidence, asset-rights inventory, license decision, checksummed artifacts, and release notes. The maintainer reviews the complete evidence and explicitly approves publication. A green CI run, this register, or a merged PR alone is not release approval.

## Evidence sources

- [Governed roadmap, including Phase G](ROADMAP_GOVERNED.md)
- [Quality policy](QUALITY_POLICY.md)
- [Security policy](SECURITY_POLICY.md) and [public security guidance](../SECURITY.md)
- [Compatibility policy draft](COMPATIBILITY_POLICY_DRAFT.md)
- [Legacy import snapshot](LEGACY_IMPORT_SNAPSHOT.md)
- [Version-by-version feature inventory](V0_FEATURE_INVENTORY.md)
- [README and current product claims](../README.md)
