# Portable Motion Core — milestone 1

Status: experimental. No native executable, Unity player, or WebAssembly release yet. The MotionPack archive format is unchanged.

## What works

The existing JavaScript evaluator and inverse-kinematics solver run without a browser, HTML, DOM, network or Canvas. The new headless entrypoint uses the same implementation. A Python CLI first validates and snapshots a .motionpack archive through the existing bounded isolated ZIP reader, then samples a requested animation time through trusted repository-owned Node.js code.

### Commands

```sh
python3 tools/package.py examples/robot_ik_demo --out /tmp/mp-build
python3 tools/sample_pose.py /tmp/mp-build/robot_ik_demo.motionpack --clip idle --time-ms 1200 --out /tmp/mp-pose.json
node tests/headless_pose_test.js
python3 -m unittest tests.test_headless_pose -v
```

Python 3 and Node.js must be installed. This is a developer integration bridge, not a native executable or a self-executing archive.

## Pose-frame protocol v1

The JSON object includes protocol=motionpack-pose, version=1, clip, variant, time_ms, canvas, nodes, and effects. Each node has id, parent, asset, z, width, height, anchor, local (x/y/rotation/scale/opacity), and world. World is an affine transform [a,b,c,d,tx,ty] in MotionPack logical pixel coordinates. Nodes appear in draw order by z value.

Effects are active effect descriptions; the host renderer implements beam, burst and ring. Asset IDs refer to images validated in the package. The frame carries **no** image bytes and is not a renderer.

The reused evaluator supports keyframe interpolation, loop boundaries, variants, two-bone IK, parents and effects. No new manifest schema or format version is introduced.

## Unity prototype (source only)

The adapters/unity/MotionPackPoseAdapter.cs example maps one JSON pose frame to inspector-bound Unity SpriteRenderer objects. Each SpriteRenderer must be assigned its sprite separately. Use root/unparented SpriteRenderers, matching sprite pivots and matching pixelsPerUnit, because the world matrix already contains parent transforms. Assign the exported frame JSON as a Unity TextAsset and wire node IDs to renderers; ApplyFrame(json) can be called with other sampled frames.

Unity Editor compilation, image import, effects, automatic archive loading, sustained real-time playback, and Unity visual parity have **not** been tested or implemented. Unity's rendering, animation timing, textures and interaction integration remain host concerns.

## Planned portability

- .motionpack stays the editable, data-only asset package.
- Windows/macOS/Linux native app bundles would embed a trusted core plus a platform renderer.
- A WebAssembly (Wasm) build could reuse compute logic where a suitable Wasm host exists. Wasm is **not** a universal executable for every Unity/mobile host.
- For Unity/mobile runtime integration, a persistent core library and host adapter are needed, not one subprocess per frame.
- No untrusted asset is permitted to ship executable code that the viewer runs automatically.

## Scope and limitations

The current one-shot CLI launches subprocesses and is not suitable for 60 fps sampling. The bridge does not decode/rasterize SVGs or PNGs; it returns transforms and effect descriptions only. The reader's isolated process is defense-in-depth, not an OS security sandbox. Platform parity, performance, deterministic physics, independent native player and self-contained native app exports are future milestones.

## Persistent headless pose session (experimental)

The new `tools/pose_session.py` loads one validated `.motionpack` archive **once** using the existing bounded isolated ZIP reader, then keeps the trusted Node.js pose evaluator running for a stream of requests. This removes the one-process-per-frame overhead from `sample_pose.py`, but remains an interprocess bridge rather than a production native library.

```sh
python3 tools/package.py examples/robot_ik_demo --out /tmp/mp-build
printf '%s\\n' '{"timeMs":0}' '{"timeMs":500,"clip":"idle"}' \\
  | python3 tools/pose_session.py /tmp/mp-build/robot_ik_demo.motionpack
```

The protocol uses newline-delimited JSON (one request/response per line). The first output line is a `ready` object; subsequent output lines contain `{ "type":"frame", "frame": ... }` or generic `{ "type":"error","code":"INVALID_REQUEST" }`. Every request may include `timeMs`, `clip`, `variant`, and `ikTargets`. The output frame schema is the same `motionpack-pose` v1 protocol described above. The bridge rejects oversized requests, unsupported keys and malformed input; the archive cannot provide code to execute. The Python and Node processes still require an installed runtime.

Cross-platform functional CI uses real packaged archives to compare multiple streamed frames against independently sampled reference frames. This does **not** validate 60 fps rendering, low-latency performance, C# integration, production process isolation or Unity Editor support.

