# Architecture and distribution

MotionPack consists of independent pieces:
- data format spec and editable source archives
- offline runtime and adapters (currently browser Canvas only)
- command-line authoring, validation and conversion tools
- optional end-user AI authoring skill later
- optional multi-step authoring agents later

The eleven Codex subagents in .codex/agents are **development** roles, not consumer authoring agents.

The editable .motionpack ZIP does not play on its own without a compatible runtime. The generated preview.html is a single self-contained offline browser preview. Its current SVG path loads data-URL assets as browser images and draws them through Canvas 2D; no browser family/version conformance matrix or cross-browser pixel parity is established. This preview path is the only renderer implemented here, not a requirement that all compatible runtimes use the same browser APIs.

The optional `tools/isolated_raster_decoder.py` adapter accepts bounded bytes for explicitly referenced raster assets and returns static RGBA pixel buffers from a separate Pillow process. It is a host-side building block; the offline HTML preview still uses the browser image decoder. Animated WebP and SVG are outside this adapter’s current scope. This API does not change the package manifest or v0.1/v0.2/v0.3 format contract.

No native engine adapters, full-body mesh skinning or reliable automatic image-to-rig conversion are currently available.
