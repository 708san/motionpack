# Layered plant source and provenance

`plant_original.svg` is the complete, hand-authored source illustration for this example. It is preserved in this `source/` directory and is not referenced by the runtime manifest.

The two runtime assets were manually separated from the same source drawing, retaining its 512 × 512 viewBox and original coordinates:

| Runtime asset | Source content | Manual treatment |
|---|---|---|
| `assets/foliage.svg` | Stem and four leaves | Kept as one editable foliage layer. The lower stem continues behind the pot. |
| `assets/pot.svg` | Pot body, rim, and three highlights | Kept as one editable pot layer and drawn above the foliage. |

The layer paths are copied from the source SVG without geometric edits. The pot intentionally occludes the lower stem; no hidden pixels were reconstructed. There is no automated segmentation, AI service, external reference, or formal manifest provenance field in this demonstration. The file mapping and extraction method live in this sidecar so the public manifest contract stays unchanged.

Rebuild and inspect offline from the repository root:

```sh
python3 tools/validate.py examples/layered_plant_demo
python3 tools/package.py examples/layered_plant_demo --out /tmp/motionpack_layered_plant
```
