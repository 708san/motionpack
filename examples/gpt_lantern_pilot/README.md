# GPT authoring pilot — floating lantern

Issue: #175. This is original GPT-authored sample geometry and motion, not an image-to-layer conversion. It is an **unreviewed quality candidate**, not a validated example or a v1 format commitment.

## Authoring brief

> Create a self-contained, editable, gently floating paper lantern in a nighttime scene. Use three separately editable static SVG layers (sky, warm halo, lantern). Keep proportions readable on a small display. Produce a MotionPack v0.3 manifest with a looping 3.2-second animation, using only documented attributes and track properties. Never use scripts, external assets, CSS, or remote references.

The three SVGs were drafted directly from this brief and iterated with additional original path-based detail; no external images were imported. This measures direct text-to-vector generation rather than image segmentation or photographic illustration synthesis. The scene has independent sky, light and lantern nodes. All runtime files live under `assets/`; source text remains editable SVG. The generator did not receive an input image, so source-image correspondence and occlusion reconstruction are **not** evaluated.

## Reproduce

```sh
python3 tools/validate.py examples/gpt_lantern_pilot
python3 tools/package.py examples/gpt_lantern_pilot --out /tmp/motionpack-gpt-pilot
# Open /tmp/motionpack-gpt-pilot/preview.html locally, without network access
```

## Evidence and open review

- Functional acceptance: GitHub Actions browser visual run #43595335306 and the functional unit-test job passed with this sample. Source-layer round-trip and offline Chromium rendering were exercised. A subsequent change adds exact clip-phase assertions; use the newest run for its result.
- An actual 390x844 screenshot from run #43595335306 was inspected. The lantern silhouette is readable, but overall artwork is deliberately simple; no human artistic approval is recorded.
- The previously failing security-negative cases were fixed in merged PR #180; the synchronized pilot branch now has passing functional and security-negative jobs. Check the current PR head for final visual and fuzz results.
- Visual iteration 2: 20 authored lantern shapes/details, layered stars, crescent moon and distant landscape. The lantern uses -2.2° to +2.2° tilt in **degrees** (matching the canonical renderer); its glow follows the lantern's vertical track to avoid separating during motion. The 3.2 s cycle returns continuously to the first pose.
- Automated motion evidence checks compare screenshot bytes at opposite phases, ensure an actual clip-time readout and assert the glow and lantern vertical tracks are identical. This detects a frozen player or a mismatched light track, but cannot measure artistic excellence or physically realistic motion.
- Functional: validate manifest and static SVG subset; package; check an offline preview and archive; inspect layer isolation; reload and amend the SVG paths.
- Visual: record stills at 0/800/1600/2400/3200 ms plus a full-cycle WebM or equivalent, at desktop and 390×844 full viewport. Explicitly distinguish canvas crop versus full viewport. Check palette, silhouette, lighting, periodic continuity, any doubled edges, and clipping.
- Human quality judgment: grade composition, originality, detail, layer editability and motion naturalness on an explicit 1–5 scale. Record failure reasons even if the validator passes; do not modify approved baseline assets.
- Limitations: no deformable mesh, no image-to-motion conversion, no cross-browser support claim and no human artwork approval.

Iterate on this candidate through separate small PRs or commits, retaining the rejected candidate's result and evidence for comparison.
