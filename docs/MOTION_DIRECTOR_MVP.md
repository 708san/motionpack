# Motion Director MVP (experimental host-side module)

MotionPack's experimental v0.1–v0.4 archive contract stays unchanged. The new
`runtime/motion_director.js` is a **pure, deterministic overlay** for an
already-evaluated pose. It does not choose clips, change the authored timeline,
send network requests or execute source-provided code. The host (trusted
application) supplies a data-only profile; the archive cannot supply scripts.

## Example

In the browser after opening a packaged preview:

```js
window.MotionPackPlayer.configureMotion({
  channels: [
    {id:'breath',node:'body',property:'scale',kind:'sine',
      amplitude:0.018,periodMs:3200,phase:0},
    {id:'head-sway',node:'head',property:'rotation',kind:'sine',
      amplitude:1.7,periodMs:4500,phase:0.25},
    {id:'blink',node:'eye',property:'opacity',kind:'pulse',
      amplitude:-1,periodMs:3800,width:0.08}
  ]
});
window.MotionPackPlayer.configureMotion(null); // disable overlays
```

All target node IDs must exist in the validated manifest, and the host
must choose useful targets and baseline properties. Unsupported IDs/properties,
NaN, infinite values, excess channels, extreme amplitudes and invalid periods
are rejected. Sampling clones the pose's node Map and touched node objects;
the base pose is not mutated.

The `sine` oscillator is continuous; the `pulse` oscillator provides a
periodic smooth closure suitable for a dedicated eyelid/eye node. Independent
channels use a monotonically increasing playback clock so their periods
need not divide the authored clip length. Channel order is deterministic:
ascending priority then profile order. Supported composition operations are
`add` and `multiply`; opacity and scale are clamped.

This is not Live2D Cubism compatibility, automatic rigging, mesh skinning,
fixed-timestep springs, lip synchronization, or a complete behavioral state
machine. No untrusted manifest field has been introduced. A future format
design must address named parameters, constraint groups, state transition
priorities, interruptibility, blending, fixed-step physics, and authoring tools
without breaking existing packages. Treat `configureMotion` as an
experimental host API, not the v1 format contract.

## Tests

```sh
node tests/motion_director_test.js
npm run test:visual -- --grep 'host config adds independent'
```

The programmatic overlay retains the existing offline preview as a valid
reference implementation. Human review is needed for motion naturalness;
deterministic unit tests only establish numerical behavior.
