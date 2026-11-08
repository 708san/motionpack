const assert = require('assert');
const interaction = require('../runtime/interaction_adapter.js');
const hitTest = require('../runtime/hit_test.js');

class Target {
  constructor() { this.listeners = new Map(); }
  addEventListener(type, listener) { this.listeners.set(type, listener); }
  removeEventListener(type) { this.listeners.delete(type); }
  getBoundingClientRect() { return { left: 10, top: 20, width: 100, height: 100 }; }
  fire(type, event = {}) { const listener = this.listeners.get(type); if (listener) listener(event); }
}

function node(id, x, z, interactionConfig = {}, fields = {}) {
  return { id, asset: `${id}.png`, x, y: 50, width: 20, height: 20,
    anchor: [0.5, 0.5], opacity: 1, scale: 1, rotation: 0, z,
    interaction: interactionConfig, ...fields };
}
function pointer(pointerType, pointerId, x, y, extras = {}) {
  return { pointerType, pointerId, isPrimary: true, clientX: x + 10, clientY: y + 20, ...extras };
}
function setup(nodes) {
  const target = new Target(), globalTarget = new Target(), events = [];
  let pose = { nodes: new Map(nodes.map(item => [item.id, item])) };
  const adapter = interaction.create({ target, globalTarget,
    manifest: { version: '0.4', canvas: { width: 100, height: 100 }, nodes },
    getPose: () => pose, assetSizes: {}, hitTest, emit: event => events.push(event) });
  return { target, globalTarget, events, adapter, setPose(value) { pose = value; } };
}

const target = setup([node('a', 30, 0, { hover: true, tap: true, click: true })]);
target.target.fire('pointermove', pointer('mouse', 1, 30, 50));
target.target.fire('pointermove', pointer('mouse', 1, 31, 50));
target.target.fire('pointerleave', pointer('mouse', 1, 31, 50));
assert.deepStrictEqual(target.events.map(event => [event.type, event.nodeId, event.input]), [
  ['hoverenter', 'a', 'mouse'], ['hoverleave', 'a', 'mouse']
], 'hover reports transitions only, not every movement');

const touch = setup([node('a', 30, 0, { tap: true })]);
touch.target.fire('pointerdown', pointer('touch', 7, 30, 50));
touch.globalTarget.fire('pointerup', pointer('touch', 7, 31, 50));
assert.deepStrictEqual(touch.events.map(event => event.type), ['tap'], 'same-node primary touch emits tap once');
touch.globalTarget.fire('pointerup', pointer('touch', 7, 30, 50));
assert.strictEqual(touch.events.length, 1, 'duplicate pointerup cannot duplicate a tap');

const cancelled = setup([node('a', 30, 0, { tap: true })]);
cancelled.target.fire('pointerdown', pointer('touch', 1, 30, 50));
cancelled.globalTarget.fire('pointercancel', pointer('touch', 1, 30, 50));
assert.deepStrictEqual(cancelled.events, [], 'pointercancel cancels tap');

const mismatched = setup([node('a', 25, 0, { tap: true }), node('b', 75, 1, { tap: true })]);
mismatched.target.fire('pointerdown', pointer('touch', 2, 25, 50));
mismatched.globalTarget.fire('pointerup', pointer('touch', 2, 75, 50));
assert.deepStrictEqual(mismatched.events, [], 'down and up on different nodes do not tap');

const nonPrimary = setup([node('a', 30, 0, { tap: true })]);
nonPrimary.target.fire('pointerdown', pointer('touch', 8, 30, 50, { isPrimary: false }));
nonPrimary.globalTarget.fire('pointerup', pointer('touch', 8, 30, 50, { isPrimary: false }));
assert.deepStrictEqual(nonPrimary.events, [], 'secondary touch pointers do not tap');

const outside = setup([node('a', 30, 0, { tap: true })]);
outside.target.fire('pointerdown', pointer('touch', 9, 30, 50));
outside.globalTarget.fire('pointerup', pointer('touch', 9, 99, 99));
assert.deepStrictEqual(outside.events, [], 'release outside the node cancels tap');

const clipped = setup([node('edge', 98, 0, { tap: true }, { width: 20 })]);
clipped.target.fire('pointerdown', pointer('touch', 10, 98, 50));
clipped.globalTarget.fire('pointerup', pointer('touch', 10, 105, 50));
assert.deepStrictEqual(clipped.events, [], 'release outside the canvas cancels tap even for clipped node bounds');

const occlusion = setup([node('lower', 50, 0, { click: true }),
  node('upper', 50, 1, { click: false })]);
occlusion.target.fire('click', pointer('mouse', 3, 50, 50));
assert.deepStrictEqual(occlusion.events, [], 'non-interactive top drawable occludes an interactive lower node');

const click = setup([node('a', 50, 0, { click: true })]);
click.target.fire('click', pointer('touch', 4, 50, 50));
click.target.fire('click', pointer('pen', 5, 50, 50));
assert.deepStrictEqual(click.events.map(event => [event.type, event.input]), [['click', 'pen']],
  'native click accepts pen and excludes touch-generated clicks');
assert.strictEqual(click.adapter.activate('a'), true, 'host can map accessible keyboard activation');
assert.deepStrictEqual(click.events[1], { type: 'click', nodeId: 'a', input: 'keyboard' });
assert.strictEqual(click.adapter.activate('missing'), false, 'unknown or opted-out node cannot be activated');
click.adapter.dispose();
click.adapter.dispose();
click.target.fire('click', pointer('mouse', 6, 50, 50));
assert.strictEqual(click.events.length, 2, 'disposed adapter detaches event handling');

console.log('OK: opt-in host events, hover transitions, touch taps, input separation and occlusion');
