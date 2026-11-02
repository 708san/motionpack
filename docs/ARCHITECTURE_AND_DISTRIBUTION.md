# Architecture and distribution boundaries

## Core components
1. **Format**: versioned inspectable manifest and source layers, masks, rig nodes, clips, effects and variants; independent of gameplay.
2. **Runtime**: deterministic offline render/player, no required cloud API.
3. **Tools**: validation, pack/unpack, preview/export, non-destructive asset editing.
4. **Authoring skills**: optional natural-language orchestration over validated tools.
5. **Optional agents**: compose tasks and audits, but are not part of the asset playback requirement.

## Design boundaries
- Parse untrusted packages with limits and explicit feature allow-lists.
- Define animation coordinate and timing conventions before external plugin commitments.
- Avoid unreviewed arbitrary code/shaders/network URLs embedded in manifests.
- Keep original assets addressable and editable after publication/export.
- Product skills for creating animations are distinct from project-development agent skills.

## State
The v0.2-alpha local implementation has not yet been merged. This document is an architecture intent, not a claim of shipped SDK capabilities.
