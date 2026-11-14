const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const rig = require(path.join(root, 'runtime/rig.js'));
const evaluator = require(path.join(root, 'runtime/evaluator.js'));
const controllerApi = require(path.join(root, 'runtime/player_controller.js'));
const pointerAdapterApi = require(path.join(root, 'runtime/pointer_ik_adapter.js'));
const viewportAdapterApi = require(path.join(root, 'runtime/viewport_adapter.js'));

function makePreview(example, prepareManifest = () => {}, controllerOverride = null) {
  const manifest = JSON.parse(fs.readFileSync(
    path.join(root, 'examples', example, 'manifest.json'), 'utf8'
  ));
  prepareManifest(manifest);
  const context = new Proxy({}, {
    get(target, key) {
      if (key === 'canvas') return { width: manifest.canvas.width, height: manifest.canvas.height };
      if (typeof target[key] === 'function') return target[key];
      return () => {};
    },
    set(target, key, value) { target[key] = value; return true; }
  });
  const listeners = {};
  const rect = { left: 10, top: 20, width: 500, height: 250 };
  const canvas = {
    width: 0,
    height: 0,
    getContext: () => context,
    getBoundingClientRect: () => rect,
    addEventListener: (name, callback) => { listeners[name] = callback; },
    removeEventListener: (name, callback) => { if (listeners[name] === callback) delete listeners[name]; }
  };
  const controls = {
    stage: canvas,
    viewport: { style: {} },
    status: { textContent: '' },
    'asset-error': { textContent: '', hidden: true },
    idle: {}, fire: {}, transform: {}, reset: {}, aim: { textContent: '' }
  };
  const calls = [];
  const frames = [];
  let now = 0;
  const playerController = Object.freeze({
    create(options) {
      const player = controllerApi.create(options);
      const setIKTarget = player.setIKTarget.bind(player);
      player.setIKTarget = (id, target) => {
        calls.push({ id, target: target === null ? null : [...target] });
        return setIKTarget(id, target);
      };
      return player;
    }
  });
  const sandbox = {
    window: {
      __MOTIONPACK__: manifest,
      MotionPackRig: rig,
      MotionPackEvaluator: evaluator,
      MotionPackPlayerController: controllerOverride || playerController,
      MotionPackPointerIKAdapter: pointerAdapterApi,
      MotionPackViewportAdapter: viewportAdapterApi
    },
    document: { getElementById: id => controls[id], body: {} },
    performance: { now: () => now },
    requestAnimationFrame: callback => { frames.push(callback); },
    Image: class {
      constructor() { this.complete = true; this.naturalWidth = 100; this.width = 100; this.height = 100; }
      set src(value) { this._src = value; }
      get src() { return this._src; }
    },
    Math, Map, Set, console
  };
  vm.runInNewContext(fs.readFileSync(path.join(root, 'runtime/viewer.js'), 'utf8'), sandbox);
  return {
    manifest, controls, listeners, calls, frames, sandbox, rect,
    frame(time) {
      now = time;
      const callback = frames.shift();
      assert(callback, `no animation frame queued at ${time}`);
      callback(time);
    },
    setNow(time) { now = time; }
  };
}

const invalidStartup = makePreview('robot_demo', manifest => { manifest.defaults.clip = 'missing'; });
assert.strictEqual(invalidStartup.controls.status.textContent,
  'Playback stopped: invalid animation data', 'invalid controller startup fails with a generic status');
assert.strictEqual(invalidStartup.frames.length, 0, 'invalid startup does not schedule frames');
const failingPlayController = Object.freeze({
  create: () => ({ play() { throw new Error('internal failure detail'); } })
});
const failedInitialPlay = makePreview('robot_demo', () => {}, failingPlayController);
assert.strictEqual(failedInitialPlay.controls.status.textContent,
  'Playback stopped: invalid animation data', 'initial play errors are hidden behind generic status');
assert.strictEqual(failedInitialPlay.frames.length, 0, 'failed initial play does not schedule frames');
assert(!failedInitialPlay.controls.status.textContent.includes('internal failure detail'));

const basic = makePreview('robot_demo');
basic.frame(0);
const legacy = basic.sandbox.window.MotionPackPlayer;
assert(Object.isFrozen(legacy));
assert.deepStrictEqual(Object.keys(legacy).sort(),
  ['configureMotion', 'getState', 'playClip', 'playTransition', 'setPointerIK', 'setVariant'].sort());
legacy.configureMotion(null);
assert.deepStrictEqual(Object.keys(legacy.getState()), ['clip', 'variant', 'pointerIK']);
assert(basic.controls.status.textContent.startsWith(`${basic.manifest.defaults.clip} |`));
const beforeUnknownClip = JSON.stringify(legacy.getState());
legacy.playClip('missing');
legacy.setVariant('missing');
assert.strictEqual(JSON.stringify(legacy.getState()), beforeUnknownClip,
  'unknown legacy clip and variant names remain no-ops');
legacy.playClip('fire');
basic.frame(0);
assert(basic.controls.status.textContent.startsWith('fire |'),
  'playClip resets playback time and uses the controller');
const transitionStart = 100;
basic.setNow(transitionStart);
legacy.playTransition('transform', 'form_b');
basic.frame(transitionStart);
const duration = basic.manifest.clips.transform.duration_ms;
basic.frame(transitionStart + duration);
assert(basic.controls.status.textContent.startsWith(`transform | form_a | ${duration}`),
  'the legacy exact-duration frame keeps its final pose and pre-transition variant');
const afterTransitionTime = transitionStart + duration + 0.25;
basic.frame(afterTransitionTime);
assert(basic.controls.status.textContent.startsWith('idle | form_b | 0'),
  'legacy transition applies only after the duration boundary and resumes the default clip');
legacy.setVariant('form_a');
assert.strictEqual(legacy.getState().variant, 'form_a');
legacy.setVariant('form_b');
legacy.playClip('fire');
basic.setNow(afterTransitionTime + 200);
basic.frame(afterTransitionTime + 200);
basic.controls.reset.onclick();
assert.deepStrictEqual(JSON.parse(JSON.stringify(legacy.getState())), {
  clip: basic.manifest.defaults.clip,
  variant: basic.manifest.defaults.variant,
  pointerIK: false
});
basic.frame(afterTransitionTime + 200);
assert(basic.controls.status.textContent.startsWith(`${basic.manifest.defaults.clip} | ${basic.manifest.defaults.variant} | 0`),
  'reset restores the default clip, variant and time');

const ikPreview = makePreview('robot_ik_demo');
ikPreview.frame(0);
const ikFacade = ikPreview.sandbox.window.MotionPackPlayer;
assert.strictEqual(ikPreview.sandbox.window.MotionPackViewport.getState().fit, 'contain');
ikPreview.sandbox.window.MotionPackViewport.configure({ fit: 'stretch' });
ikFacade.setPointerIK(true);
ikPreview.controls.aim.onclick();
assert.strictEqual(ikFacade.getState().pointerIK, false,
  'the preview button toggles its own pointer IK state from the initial value');
ikPreview.controls.aim.onclick();
assert.strictEqual(ikFacade.getState().pointerIK, true);
ikPreview.listeners.pointermove({ clientX: 110, clientY: 70 });
ikPreview.frame(16);
const chainId = ikPreview.manifest.iks[0].id;
assert(ikPreview.calls.some(call => call.id === chainId &&
  call.target && call.target[0] === 200 && call.target[1] === 200),
'pointer coordinates map from CSS bounds into logical canvas coordinates');
ikPreview.listeners.pointerdown({ pointerId: 5, pointerType: 'touch', isPrimary: true, clientX: 110, clientY: 70 });
ikPreview.listeners.pointermove({ pointerId: 5, pointerType: 'touch', isPrimary: true, clientX: 210, clientY: 120 });
assert(ikPreview.calls.some(call => call.id === chainId &&
  call.target && call.target[0] === 400 && call.target[1] === 400),
'primary touch pointer maps to logical canvas coordinates while pressed');
ikPreview.listeners.pointermove({ pointerId: 6, pointerType: 'touch', isPrimary: false, clientX: 310, clientY: 170 });
assert.deepStrictEqual(ikPreview.calls[ikPreview.calls.length - 1].target, [400, 400],
'secondary pointer cannot replace the active touch target');
ikPreview.listeners.pointercancel({ pointerId: 5, pointerType: 'touch', isPrimary: true });
assert.strictEqual(ikPreview.calls[ikPreview.calls.length - 1].target, null,
'pointercancel clears the touch target');
ikPreview.rect.width = 0;
ikPreview.listeners.pointermove({ clientX: 110, clientY: 70 });
ikPreview.frame(32);
assert(!ikPreview.controls.status.textContent.includes('Playback stopped'),
  'a zero-size canvas rect discards the pointer input without stopping playback');
ikPreview.rect.width = 500;
ikPreview.listeners.pointermove({ clientX: NaN, clientY: 70 });
ikPreview.frame(48);
assert(!ikPreview.controls.status.textContent.includes('Playback stopped'),
  'non-finite pointer coordinates do not stop playback');
ikPreview.listeners.pointerleave({ pointerId: 1, pointerType: 'mouse', isPrimary: true });
assert(ikPreview.calls.some(call => call.id === chainId && call.target === null),
  'pointerleave clears the temporary IK target');
ikFacade.setPointerIK(false);
assert.deepStrictEqual(JSON.parse(JSON.stringify(ikFacade.getState())), {
  clip: ikPreview.manifest.defaults.clip,
  variant: ikPreview.manifest.defaults.variant,
  pointerIK: false
});

console.log('OK: legacy preview facade, controller timing, transition and pointer IK');
