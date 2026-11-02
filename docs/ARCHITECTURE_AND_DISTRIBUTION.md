# Architecture and distribution

MotionPack consists of independent pieces:
- data format spec and editable source archives
- offline runtime and adapters (currently browser Canvas only)
- command-line authoring, validation and conversion tools
- optional end-user AI authoring skill later
- optional multi-step authoring agents later

The eleven Codex subagents in .codex/agents are **development** roles, not consumer authoring agents.

The editable .motionpack ZIP does not play on its own without a compatible runtime. The generated preview.html is a single self-contained offline browser preview.

No native engine adapters, full-body mesh skinning or reliable automatic image-to-rig conversion are currently available.
