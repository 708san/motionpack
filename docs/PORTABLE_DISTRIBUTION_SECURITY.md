# MotionPack portable distribution and security contract (proposed)

## Product goal

One authored, editable animation can be distributed and run interactively with minimal preparation across browsers, desktop operating systems and host applications. Trigger-controlled clip switching, pointer/touch events, semantic actions and optional autonomous motion must be preserved; **flattening to video is not an acceptable primary format**.

**Non-goal:** a single machine-code executable that opens and runs natively on every operating system without any host runtime or viewer. This is not possible with ordinary OS loader conventions. A GIF is viewable because the receiving OS/app already implements a GIF decoder; Wasm similarly requires a supporting runtime and graphics/input host.

## Exactly three user-facing delivery modes

| Mode | User-facing format | Opens with | Main use | Interactivity |
|---|---|---|---|---|
| **Editable asset (canonical)** | `.motionpack` | MotionPack-compatible viewer/host or importer | Store, exchange, remix, import | Full declared animation/event data; host determines supported behavior |
| **Open-and-play portable** | One offline `.html` | Existing modern browser | Send a file and interact immediately without installing a player | Yes, subject to browser `file://` restrictions and browser security settings |
| **Browserless standalone** | One OS-targeted app (`.exe` for Windows; signed `.app` bundle for macOS; Linux binary/AppImage if supported) | OS native loader | Offline click-to-run desktop playback without installing a browser | Yes; native host owns graphics/input |

Internal engine artifact: `motionpack_core.wasm` is a **shared runtime component**, not a fourth user-facing animation format. Build/distribution tools may bundle it into the HTML or native player. For importing into arbitrary apps, a supported loader/renderer adapter is required (and it can reuse this engine).

Optional compatibility exports (`.webm`, `.gif`, static images) are **not canonical MotionPack delivery modes**: they flatten motion and lose part-level editability and/or interaction. They may remain diagnostic/social exports but should not appear as the primary import workflow.

## What 'one file' means

- A `.motionpack` is a **single data-only ZIP package** with manifest and referenced assets. It is portable and editable; merely embedding a Wasm engine into this ZIP would not make OSs execute it. A viewer/integration is still needed.
- A self-contained HTML file may embed a pinned Wasm binary, CSS/JS loader, rendering code, and encoded validated assets. Offline loading must be tested using an actual `file://` launch, because browser-origin rules can prevent external `.wasm` fetches and some APIs. Inline/embedded Wasm instantiation from bytes is the candidate implementation, not a current release guarantee.
- A browserless standalone desktop player is built **per OS and architecture**, including native engine, renderer and assets. macOS `.app` is a directory bundle shown as one application in Finder; it is not literally one ordinary flat file. App signing/notarization and operating-system warnings must be respected.
- An embeddable `.motionpack` remains host-controlled. Neither a bare `.wasm` nor a data ZIP becomes a portable graphics/window/interaction program by itself.

## Runtime boundaries

```text
        canonical data-only animation.motionpack
                        |
          bounded validator / safe asset loader
                        |
          MotionPack engine (Rust core; Wasm/native)
            | pose / effects / action descriptors
       +----+----------+------------------+
       |               |                  |
  Browser host     Desktop host      Host application
  canvas/input     graphics/input    adapter (e.g. Unity)
       |               |                  |
  standalone HTML  native artifact   imported .motionpack
```

The authored data must never name arbitrary functions, host scripts, URLs, executables, shell commands, file paths outside its package, or elevated permission requirements. Triggers are **declarative action identifiers**; an explicit trusted host policy maps them to application behavior. A click event from a package must not count as an authorization/security gesture.

## Minimum behavior contract

- **Same asset:** clips, variants, layer IDs, image sources, keyframe curves, IK targets, drawing order and effect descriptors survive export.
- **Interaction:** input events (`hover`, `click`, `tap`) are normalized to node/action notifications; host may opt in. Host API supports `play(clip)`, `act(action)`, `stop`, `pause`, `seek`, loop and optional autonomy. Exact names are future API proposals, not currently shipping stable ABI.
- **Deterministic pose:** for identical validated data and explicit time, the Rust native and Wasm cores produce numerically equivalent scene poses within a documented tolerance; event/ambient behavior is seeded when reproducibility is needed.
- **No hidden dependencies at recipient:** offline HTML uses an installed browser only, native apps include their own runtime and renderer, and `.motionpack` imports require a clearly stated compatible host. Rendering/input plugins are host-specific but optional to the asset author.
- **Graceful compatibility:** a host identifies format version and supported capabilities, and reports unsupported features explicitly instead of silently discarding interactions. Static fallback is optional but must be visibly identified.

## Threat model and requirements before public release

| Threat | Required mitigation / acceptance test |
|---|---|
| ZIP bombs, oversized metadata and asset path traversal | Bounded central-directory and decompression validation, per-asset and total-memory ceilings, no path extraction, fuzz and mutation tests; preserve isolated reader |
| Active SVG content, script URLs, foreign references | Strict, versioned static-SVG allowlist; block scripts, external resources, event attributes and references; validate before passing to browser/native image decoders; include malicious-SVG tests |
| Untrusted Wasm/code hidden inside an asset | `.motionpack` remains **data only**; reject `.wasm`, JS, executable files as runtime assets. Only publisher-supplied, pinned and verified engine binaries may execute; engine is not sourced from imported animation packages |
| Malicious host event or autoplay triggering privileged action | Capabilities deny-by-default; allow only declarative event IDs; host explicitly grants actions; no shell, arbitrary filesystem, clipboard or network effects from asset data |
| Parser/decoder vulnerabilities | Use isolated or OS-sandboxed decoding where possible, patch dependencies, bound pixels/dimensions/CPU/memory/time; test with corrupted raster/vector formats |
| Runtime DoS via huge animations, long loops or excessive events | Hard limits for node/track/key count and nesting, frame/event budget, timeout/cancel control and memory upper bounds; CI stress tests |
| Data exfiltration | Offline by default; network disabled in generated HTML/player and never needed for local playback; optional connectivity requires explicit host opt-in; verify no network activity during offline playback |
| Tampered player or supply-chain malware | Deterministic release pipeline, source-controlled/pinned dependencies, checksums and signed release artifacts; macOS Developer ID signing and notarization where applicable; Windows code signing and reputation considerations; dependency/security advisory review |
| Cross-origin browser restrictions | Test offline `file://` interaction and embedded Wasm/assets on supported browsers; do not depend on remote CDN, external fonts or runtime fetches |

Wasm memory isolation is a useful defense **inside a correctly configured host**, not a malware scanner or blanket security guarantee. Host-imported capabilities are the security boundary. Native executables have broader OS capabilities and must be signed/sandboxed appropriately.

## Security acceptance gates

1. Asset cannot cause arbitrary JavaScript/Wasm/native code execution or network access through the importer.
2. Valid packages replay deterministically in supported runtimes; malformed packages fail closed without crashes or partial privileged effects.
3. Every export format passes independent smoke tests for **offline startup, input triggers and action switching**. Visual snapshots/video alone do not prove interactivity.
4. Fuzz/resource-ceiling tests pass for package reader and SVG/raster decoder. Desktop players are tested in a clean standard-user account (no developer tools installed).
5. Runtime ABI/format versions and hashes are recorded in each distributable. Signing/notarization requirements are respected for OS-targeted artifacts.

## Scope decision and implementation order

1. **Keep `.motionpack` as the only source-of-truth editable asset.** Do not embed independently executable Wasm in each imported package; a dependency/version declaration is allowed but must never be an instruction to download/execute code.
2. Complete one **reusable Rust/Wasm pose + behavior runtime** against reference parity; keep the browser/native renderers outside the numeric kernel.
3. Build and test an **offline, single-file HTML** bundle with assets and Wasm embedded and real click/trigger integration. Require direct local-file smoke tests before advertising one-file portability.
4. Build **OS-targeted self-contained desktop players** only after the host renderer/input loop is stable; create separate signed deliverables per platform.
5. Add lightweight game/Unity adapters **on demand**, not as a separately reimplemented animation engine; integrate validated assets using host renderers.

Do not add a fourth permanent user-facing extension unless a clearly different audience/use case cannot be served by these three modes. Browser-only or native-only build artifacts remain implementation details.
