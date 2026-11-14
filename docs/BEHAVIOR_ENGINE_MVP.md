# Optional semantic action and nonperiodic ambient behavior — MVP

Status: experimental host-side feature. This does not change the .motionpack manifest schema or v0.1–v0.4 playback. Existing clips, effects, variants, IK and regular player controls remain available without a behavior profile.

## Motivation

Host apps can ask a character to `greet` without knowing its concrete clip name, while assets may define different clips for the same semantic intent. Optionally, a local seeded scheduler chooses occasional preauthored gestures at varying intervals. Neither capability requires AI inference during playback.

## Browser host API

```js
window.MotionPackPlayer.configureBehavior({
  seed: 71,
  actions: {
    greet: { clip: 'wave' },
    celebrate: { clip: 'jump', variant: 'happy' },
    blink: { clip: 'blink' }
  },
  ambient: {
    minIntervalMs: 2500, maxIntervalMs: 5500,
    choices: [{ action: 'blink', weight: 5 }, { action: 'greet', weight: 1 }]
  }
});
window.MotionPackPlayer.act('greet');
window.MotionPackPlayer.setAutonomy(false);
window.MotionPackPlayer.configureBehavior(null);
```

The example assumes those clips and variants exist in the current asset. Invalid clip/variant names fail configuration instead of creating unseen motions.

## Defined behavior and deliberate limits

- An `action` resolves to an explicitly authored clip and optional variant. This is a semantic routing layer, NOT an AI-generated new animation, procedural gesture synthesizer, universal emotion ontology or cross-character retargeting.
- Ambient events use a reproducible seeded pseudorandom generator and variable interval, never an unbounded timer loop. Host-supplied actions are bounded to 64; ambient choices to 16; min interval at least 1 second.
- The browser preview samples suggestions only when the currently playing clip equals the default clip. This ensures autonomous gestures do not interrupt explicit non-default actions. If an ambient clip is non-looping, the existing viewer returns to its default clip after it ends.
- When autonomy is disabled, elapsed time continues but ambient gestures are discarded instead of accumulated for later playback.
- Existing `playClip` and `configureMotion` operations are independent and remain available. Ambient suggestions are disabled until the trusted host opts in.
- All behavior profiles are data provided by a trusted host; the .motionpack archive cannot name callbacks, scripts or executable actions. No network or LLM calls are required.
- `runtime/behavior_engine.js` is DOM-independent and may be reused by future Unity/desktop hosts. The current Python headless session does not yet integrate semantic actions; that is a follow-on milestone.

## Next steps

Integrate named actions into the common persistent session protocol, add blend/interrupt priorities and cooldowns to avoid awkward transitions, then layer free-running procedural motion on a per-node channel basis. The host should be able to evaluate multiple simultaneous gestures without switching the main clip in later versions.

## Verification

```sh
node tests/behavior_engine_test.js
npx playwright test tests/behavior_engine.spec.js
```

These test semantic mapping, unsafe profile rejection, seed determinism, nonperiodic intervals and legacy clip behavior. Human evaluation is still required for motion naturalness and artistic quality in any newly authored character sample.
