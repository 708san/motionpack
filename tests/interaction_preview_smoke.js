const fs = require('fs'), vm = require('vm'), assert = require('assert'), path = require('path');
const root = path.resolve(__dirname, '..');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'examples/robot_demo/manifest.json'), 'utf8'));
manifest.version = '0.4';
manifest.canvas.width = 100;
manifest.canvas.height = 100;
const activeNode = manifest.nodes[0];
Object.assign(activeNode, { x: 50, y: 50, width: 20, height: 20, parent: null, rotation: 0, scale: 1, anchor: [0.5, 0.5], interaction: { click: true } });
for (const node of manifest.nodes.slice(1)) node.asset = null;
const events = [], frames = [];
const ctx = new Proxy({}, { get(t, k) { if (k === 'canvas') return { width: 800, height: 1000 }; return t[k] || (() => {}); },
  set(t, k, v) { t[k] = v; return true; } });
const listeners = new Map();
const canvas = { getContext() { return ctx; }, addEventListener(type, listener) { listeners.set(type, listener); },
  removeEventListener(type) { listeners.delete(type); }, fire(type, event) { listeners.get(type)?.(event); },
  getBoundingClientRect() { return { left: 0, top: 0, width: 100, height: 100 }; } };
const controls = { stage: canvas, status: { textContent: '' }, idle: {}, fire: {}, transform: {}, reset: {}, aim: { textContent: '' } };
const sandbox = {
  window: { __MOTIONPACK__: manifest, dispatchEvent(event) { events.push(event); } },
  document: { getElementById(id) { return controls[id]; }, body: {} },
  performance: { now() { return 0; } }, requestAnimationFrame(fn) { frames.push(fn); },
  CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init.detail; } },
  Image: class { constructor() { this.complete = true; this.naturalWidth = 100; this.width = 100; this.height = 100; }
    set src(value) { this._src = value; } get src() { return this._src; } }, Math, Map, Set, console
};
sandbox.window.MotionPackRig = require(path.join(root, 'runtime/rig.js'));
sandbox.window.MotionPackEvaluator = require(path.join(root, 'runtime/evaluator.js'));
sandbox.window.MotionPackPlayerController = require(path.join(root, 'runtime/player_controller.js'));
sandbox.window.MotionPackHitTest = require(path.join(root, 'runtime/hit_test.js'));
sandbox.window.MotionPackInteractionAdapter = require(path.join(root, 'runtime/interaction_adapter.js'));
vm.runInNewContext(fs.readFileSync(path.join(root, 'runtime/viewer.js'), 'utf8'), sandbox);
assert(sandbox.window.MotionPackInteractions, 'v0.4 preview exposes a separate interaction facade');
assert.strictEqual(typeof sandbox.window.MotionPackPlayer.setPointerIK, 'function', 'legacy player facade remains available');
frames.shift()(0);
assert.strictEqual(sandbox.window.MotionPackInteractions.activate(manifest.nodes[0].id), true);
assert.strictEqual(events.length, 1);
assert.strictEqual(events[0].type, 'motionpack:interaction');
assert.deepStrictEqual(events[0].detail, { type: 'click', nodeId: manifest.nodes[0].id, input: 'keyboard' });
canvas.fire('click', { pointerType: 'mouse', clientX: 50, clientY: 50 });
assert.deepStrictEqual(events[1].detail, { type: 'click', nodeId: manifest.nodes[0].id, input: 'mouse' },
  'rendered preview routes pointer click through hit testing');
console.log('OK: v0.4 preview emits host-facing interaction event without changing player facade');
