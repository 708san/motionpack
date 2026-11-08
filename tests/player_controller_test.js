const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const manifest = JSON.parse(fs.readFileSync(
  path.join(root, 'examples/robot_ik_demo/manifest.json'), 'utf8'
));
const rig = require(path.join(root, 'runtime/rig.js'));
const { create } = require(path.join(root, 'runtime/player_controller.js'));

const player = create({ manifest, rig });
assert.deepStrictEqual(player.getState(), {
  state: 'stopped', clip: manifest.defaults.clip, variant: manifest.defaults.variant,
  timeMs: 0, durationMs: manifest.clips[manifest.defaults.clip].duration_ms,
  loop: Boolean(manifest.clips[manifest.defaults.clip].loop)
});

player.play('idle');
player.advance(600);
assert.strictEqual(player.getState().timeMs, 600);
const pausedPose = player.getPose();
assert.strictEqual(player.pause(), true);
player.advance(500);
assert.strictEqual(player.getState().timeMs, 600);
assert.strictEqual(player.resume(), true);
player.advance(200);
assert.strictEqual(player.getState().timeMs, 800);
assert.notDeepStrictEqual(player.getPose().nodes.get('mech'), pausedPose.nodes.get('mech'));

const loopDuration = manifest.clips.idle.duration_ms;
player.seek(loopDuration);
assert.strictEqual(player.getState().timeMs, 0, 'loop seek wraps duration to zero');
player.seek(loopDuration - 1);
player.advance(1);
assert.strictEqual(player.getState().timeMs, 0, 'loop advance wraps exactly at duration');
player.seek(loopDuration * 2 + 125);
assert.strictEqual(player.getState().timeMs, 125);
player.advance(Number.MAX_VALUE);
assert(Number.isFinite(player.getState().timeMs), 'large loop advances remain finite');
assert(player.getState().timeMs >= 0 && player.getState().timeMs < loopDuration);

player.play('fire');
const fireDuration = manifest.clips.fire.duration_ms;
player.advance(fireDuration - 1);
assert.strictEqual(player.getState().state, 'playing');
player.advance(Number.MAX_VALUE);
assert.strictEqual(player.getState().state, 'ended');
assert.strictEqual(player.getState().timeMs, fireDuration);
assert.strictEqual(player.getPose().timeMs, fireDuration);
player.advance(100);
assert.strictEqual(player.getState().timeMs, fireDuration, 'ended playback holds final pose');
player.play();
assert.strictEqual(player.getState().timeMs, 0, 'play restarts selected clip');

player.stop();
player.seek(400);
assert.strictEqual(player.getState().state, 'paused', 'seeking a stopped player creates a paused pose');
player.seek(fireDuration);
assert.strictEqual(player.getState().state, 'ended');
player.seek(400);
assert.strictEqual(player.getState().state, 'paused', 'seeking back from ended pauses at that time');
player.stop();
assert.strictEqual(player.getState().state, 'stopped');
assert.strictEqual(player.getState().timeMs, 0);

player.setVariant('form_b');
assert.strictEqual(player.getState().variant, 'form_b');
assert.strictEqual(player.getPose().nodes.get('body').asset, 'torso_power');
assert.throws(() => player.play('missing'), /unknown clip/);
assert.throws(() => player.setVariant('missing'), /unknown variant/);

const manifestWithoutIKTracks = JSON.parse(JSON.stringify(manifest));
manifestWithoutIKTracks.clips.idle.ik_tracks = [];
const ikPlayer = create({ manifest: manifestWithoutIKTracks, rig });
const defaultIKPose = ikPlayer.getPose();
const requestedTarget = [900, 250];
const overriddenIKPose = ikPlayer.setIKTarget('aim_right', requestedTarget);
assert.notStrictEqual(overriddenIKPose.nodes.get('right_upper').rotation,
  defaultIKPose.nodes.get('right_upper').rotation,
  'an IK override changes the sampled pose');
requestedTarget[0] = 1;
assert.strictEqual(ikPlayer.getPose().nodes.get('right_upper').rotation,
  overriddenIKPose.nodes.get('right_upper').rotation,
  'the controller copies the target on set');
assert.deepStrictEqual(ikPlayer.setIKTarget('aim_right', null), defaultIKPose,
  'clearing an override restores the manifest and animation target');
assert.throws(() => ikPlayer.setIKTarget('missing', [1, 2]), /unknown IK chain/);
let getterReads = 0;
const getterTarget = [0, 0];
Object.defineProperty(getterTarget, 0, { get() { getterReads++; return getterReads === 1 ? 321 : NaN; } });
assert.deepStrictEqual(ikPlayer.setIKTarget('aim_right', getterTarget),
  ikPlayer.getPose(), 'target values are snapshotted before storage');
assert.strictEqual(getterReads, 1, 'each target coordinate getter is read once');
const trackedIKPlayer = create({ manifest, rig });
const trackedDefaultPose = trackedIKPlayer.getPose();
trackedIKPlayer.setIKTarget('aim_right', [900, 250]);
const restoredTrackPose = trackedIKPlayer.setIKTarget('aim_right', null);
assert.deepStrictEqual(restoredTrackPose.nodes.get('right_upper'),
  trackedDefaultPose.nodes.get('right_upper'),
  'clearing an override restores clip IK-track values');
trackedIKPlayer.dispose();
for (const invalidTarget of [undefined, {}, [1], [1, 2, 3], [1, NaN], [Infinity, 2], [, 2]]) {
  assert.throws(() => ikPlayer.setIKTarget('aim_right', invalidTarget), /invalid IK target/);
}
ikPlayer.dispose();
assert.throws(() => ikPlayer.setIKTarget('aim_right', [1, 2]), /disposed/);

const inheritedDefaultsManifest = { ...manifest, defaults: Object.create({ clip: 'idle', variant: 'form_a' }) };
assert.throws(() => create({ manifest: inheritedDefaultsManifest, rig }), /unknown clip/);
const invalidLoopManifest = JSON.parse(JSON.stringify(manifest));
invalidLoopManifest.clips.idle.loop = 'false';
assert.throws(() => create({ manifest: invalidLoopManifest, rig }), /loop must be a boolean/);
const numericallyExtremeManifest = JSON.parse(JSON.stringify(manifest));
numericallyExtremeManifest.iks[0].lengths = [1e308, 1e308];
assert.throws(() => create({ manifest: numericallyExtremeManifest, rig }), /numeric range/,
  'overflowing IK math fails safely instead of returning a non-finite pose');
for (const value of [-1, NaN, Infinity, -Infinity]) {
  assert.throws(() => player.advance(value), /deltaMs/);
  assert.throws(() => player.seek(value), /timeMs/);
}

const otherManifest = JSON.parse(JSON.stringify(manifest));
otherManifest.defaults.clip = 'fire';
const second = create({ manifest: otherManifest, rig });
second.play('fire');
second.advance(900);
assert.strictEqual(second.getState().clip, 'fire');
assert.strictEqual(second.getState().timeMs, 900);
assert.strictEqual(player.getState().clip, 'fire');
assert.strictEqual(player.getState().timeMs, 0);
second.dispose();
assert.strictEqual(second.getState().state, 'disposed');
second.dispose();
assert.throws(() => second.getPose(), /disposed/);
assert.throws(() => second.advance(1), /disposed/);

const independentPose = player.getPose();
independentPose.nodes.get('mech').x = -999;
assert.notStrictEqual(player.getPose().nodes.get('mech').x, -999,
  'callers receive independent sampled poses');
player.dispose();
console.log('OK: host-driven playback lifecycle, boundaries, isolation and disposal');
