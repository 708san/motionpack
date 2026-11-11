# Interactive Seal source and provenance

`interactive_seal_original.svg` is the complete hand-authored source illustration. It is retained unchanged in this directory and is not referenced by the runtime manifest.

The runtime drawing was manually separated from this shared 910 × 550 coordinate space. The runtime source remains editable SVG and is packaged only through manifest references.

| Runtime layer | Source content | Treatment |
|---|---|---|
| `assets/background.svg` | Sea gradient, shoreline, distant wave and bubbles | Separated without external references. |
| `assets/shadow.svg` | Soft oval contact shadow | Isolated for a subtle idle pulse and squash feedback. |
| `assets/flippers.svg` | Paired rear flippers | Separated as a layer behind the seal body to keep the silhouette readable. |
| `assets/body.svg` | Seal silhouette, coat shading and flipper details | Edited into a reusable body layer. |
| `assets/body_squash.svg` | Wider, lower seal silhouette | Hand-drawn squash pose, cross-faded by the sample clip. |
| `assets/face.svg` | Open eyes, muzzle, nose, smile and cheeks | Idle facial layer. |
| `assets/face_rest.svg` | Closed-eye version of the same face | Derived rest expression, independently layered and cross-faded from the idle face by the `rest` variant. |
| `assets/seal_hit.svg` | Near-transparent silhouette | Input target; v0.4 hit-testing uses the node rectangle, not vector pixels. |

This is manually authored artwork, not AI-generated or automatically segmented. The original and runtime layers are kept together so the source-to-layer relationship is reproducible. The closed-eye rest expression is a manually authored derivative; the complete original source illustration remains unchanged. No hidden pixels are reconstructed. The sample host script, rather than the manifest, maps tap/click notifications to animation playback. It does not add a portable squash feature to the format.

The preview generator creates a self-contained HTML file. No remote assets, network service, or external runtime is used. The static fallback is embedded in the HTML and remains visible if scripts or image decoding fail. Browser emulation is not evidence of physical-device behavior.

Rebuild and validate from the repository root:

```sh
python3 tools/validate.py examples/interactive_seal_demo
python3 tools/package.py examples/interactive_seal_demo --out /tmp/motionpack_interactive_seal
python3 examples/interactive_seal_demo/build_preview.py --out /tmp/motionpack_interactive_seal
```

The generated `.motionpack` includes the manifest and referenced runtime assets only; the preserved original source remains a separate repository file.
