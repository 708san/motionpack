const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const manifest = JSON.parse(fs.readFileSync(
  path.join(root, 'examples/robot_ik_demo/manifest.json'), 'utf8'
));
const evaluator = require(path.join(root, 'runtime/evaluator.js'));
const rig = require(path.join(root, 'runtime/rig.js'));
const original = JSON.stringify(manifest);

const initial = evaluator.sample(manifest, { timeMs: 0 }, rig);
assert.strictEqual(initial.clip, manifest.defaults.clip);
assert.strictEqual(initial.variant, manifest.defaults.variant);
assert.strictEqual(initial.timeMs, 0);
assert(initial.nodes instanceof Map);

const middle = evaluator.sample(manifest, { clip: 'idle', timeMs: 1200 }, rig);
assert.strictEqual(middle.nodes.get('mech').y, 608);
assert.strictEqual(middle.effects.length, 0);
const loopBoundary = evaluator.sample(manifest, { clip: 'idle', timeMs: 2400 }, rig);
assert.strictEqual(loopBoundary.timeMs, 0);
assert.strictEqual(loopBoundary.nodes.get('mech').y, 620);

const nonLoopEnd = evaluator.sample(manifest, { clip: 'fire', timeMs: 3000 }, rig);
assert.strictEqual(nonLoopEnd.timeMs, manifest.clips.fire.duration_ms);
assert.strictEqual(nonLoopEnd.clip, 'fire');
const effect = evaluator.sample(manifest, { clip: 'fire', timeMs: 590 }, rig).effects
  .find(item => item.kind === 'beam');
assert(effect);
assert.strictEqual(effect.age_ms, 0);
assert.strictEqual(effect.progress, 0);

const variant = evaluator.sample(manifest, { variant: 'form_b', timeMs: 0 }, rig);
assert.strictEqual(variant.nodes.get('body').asset, 'torso_power');
const explicitTarget = evaluator.sample(manifest, {
  clip: 'idle', timeMs: 800, ikTargets: { aim_right: [900, 250] }
}, rig);
assert.notStrictEqual(explicitTarget.nodes.get('right_upper').rotation,
  evaluator.sample(manifest, { clip: 'idle', timeMs: 800 }, rig)
    .nodes.get('right_upper').rotation);

assert.strictEqual(JSON.stringify(manifest), original, 'sampling must not mutate the manifest');
assert.notStrictEqual(initial.nodes.get('mech'), middle.nodes.get('mech'),
  'each result must own its node objects');
assert.throws(() => evaluator.sample(manifest, { clip: 'missing' }, rig), /unknown clip/);
assert.throws(() => evaluator.sample(manifest, { variant: 'missing' }, rig), /unknown variant/);
assert.throws(() => evaluator.sample(manifest, { clip: 'toString' }, rig), /unknown clip/);
assert.throws(() => evaluator.sample(manifest, { variant: 'toString' }, rig), /unknown variant/);
assert.throws(() => evaluator.sample(manifest, { timeMs: Infinity }, rig), /timeMs/);
const invalidLoopManifest = JSON.parse(JSON.stringify(manifest));
invalidLoopManifest.clips.idle.loop = 'false';
assert.throws(() => evaluator.sample(invalidLoopManifest, { clip: 'idle' }, rig), /loop must be a boolean/);
const invalidIkWeightManifest = JSON.parse(JSON.stringify(manifest));
invalidIkWeightManifest.iks[0].weight = 'bad';
assert.throws(() => evaluator.sample(invalidIkWeightManifest, { clip: 'idle' }, rig), /Invalid IK weight/);
assert.throws(() => evaluator.sample(manifest, {
  ikTargets: { missing: [1, 2] }
}, rig), /invalid IK target/);
assert.throws(() => evaluator.sample(manifest, {
  ikTargets: { toString: [1, 2] }
}, rig), /invalid IK target/);
const inheritedTrackManifest = JSON.parse(JSON.stringify(manifest));
inheritedTrackManifest.clips.idle.ik_tracks.push({
  ik: '__proto__', axis: 'x', keys: [{ time_ms: 0, value: 1 }]
});
assert.throws(() => evaluator.sample(inheritedTrackManifest, { clip: 'idle' }, rig),
  /unknown IK chain/);

console.log('OK: stateless pose sampling, variants, looping, effects and IK targets');
