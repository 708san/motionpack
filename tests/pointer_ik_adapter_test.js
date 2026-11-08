const assert = require('assert');
const adapterApi = require('../runtime/pointer_ik_adapter.js');

function makeTarget() {
  const listeners = new Map();
  const rect = { left: 10, top: 20, width: 500, height: 250 };
  return {
    listeners,
    rect,
    addEventListener(name, callback) { listeners.set(name, callback); },
    removeEventListener(name, callback) {
      if (listeners.get(name) === callback) listeners.delete(name);
    },
    getBoundingClientRect() { return rect; },
    emit(name, event = {}) {
      const callback = listeners.get(name);
      if (callback) callback(event);
    }
  };
}

function makeAdapter() {
  const target = makeTarget();
  const calls = [];
  const controller = { setIKTarget: (id, point) => calls.push({ id, point }) };
  const adapter = adapterApi.create({
    target, controller, ikId: 'aim', logicalWidth: 1000, logicalHeight: 500
  });
  return { target, calls, adapter };
}

function pointer(pointerId, pointerType = 'mouse', extra = {}) {
  return { pointerId, pointerType, isPrimary: true, clientX: 110, clientY: 70, ...extra };
}

const basic = makeAdapter();
assert.deepStrictEqual([...basic.target.listeners.keys()].sort(),
  ['pointercancel', 'pointerdown', 'pointerleave', 'pointermove', 'pointerup']);
basic.target.emit('pointermove', pointer(1));
assert.strictEqual(basic.calls.length, 0, 'adapter starts disabled');
basic.adapter.enable();
basic.target.emit('pointermove', pointer(1));
assert.deepStrictEqual(basic.calls.pop(), { id: 'aim', point: [200, 100] });
basic.target.emit('pointermove', pointer(1, 'mouse', { clientX: 5, clientY: 400 }));
assert.deepStrictEqual(basic.calls.pop(), { id: 'aim', point: [-10, 760] },
  'coordinates map to logical space without clamping');

const touch = makeAdapter();
touch.adapter.enable();
touch.target.emit('pointermove', pointer(7, 'touch'));
assert.strictEqual(touch.calls.length, 0, 'touch requires an active pointerdown');
touch.target.emit('pointerdown', pointer(7, 'touch'));
touch.target.emit('pointermove', pointer(7, 'touch', { clientX: 210, clientY: 120 }));
assert.deepStrictEqual(touch.calls.pop(), { id: 'aim', point: [400, 200] });
touch.calls.length = 0;
touch.target.emit('pointerdown', pointer(8, 'touch', { isPrimary: false }));
touch.target.emit('pointermove', pointer(8, 'touch', { isPrimary: false, clientX: 310 }));
assert.strictEqual(touch.calls.length, 0, 'non-primary pointers are ignored');
touch.target.emit('pointerup', pointer(7, 'touch'));
assert.deepStrictEqual(touch.calls.pop(), { id: 'aim', point: null });
touch.target.emit('pointermove', pointer(7, 'touch'));
assert.strictEqual(touch.calls.length, 0, 'touch input stops after pointerup');

for (const endEvent of ['pointercancel', 'pointerleave']) {
  const ended = makeAdapter();
  ended.adapter.enable();
  ended.target.emit('pointerdown', pointer(3, 'pen'));
  ended.target.emit(endEvent, pointer(3, 'pen'));
  assert.deepStrictEqual(ended.calls.map(call => call.point), [[200, 100], null], endEvent);
}

const invalid = makeAdapter();
invalid.adapter.enable();
invalid.target.emit('pointermove', pointer(2));
invalid.calls.length = 0;
invalid.target.rect.width = 0;
invalid.target.emit('pointermove', pointer(2));
assert.deepStrictEqual(invalid.calls.pop(), { id: 'aim', point: null }, 'zero-size bounds clear the target');
invalid.target.rect.width = 500;
invalid.target.emit('pointermove', pointer(2));
invalid.calls.length = 0;
invalid.target.emit('pointermove', pointer(2, 'mouse', { clientX: NaN }));
assert.deepStrictEqual(invalid.calls.pop(), { id: 'aim', point: null }, 'non-finite coordinates clear the target');

const disabled = makeAdapter();
disabled.adapter.enable();
disabled.target.emit('pointermove', pointer(4));
disabled.adapter.disable();
assert.deepStrictEqual(disabled.calls.pop(), { id: 'aim', point: null });
disabled.calls.length = 0;
disabled.target.emit('pointermove', pointer(4));
assert.strictEqual(disabled.calls.length, 0, 'disabled adapter ignores input');

const disposed = makeAdapter();
disposed.adapter.enable();
disposed.target.emit('pointermove', pointer(9));
disposed.adapter.dispose();
disposed.adapter.dispose();
assert.deepStrictEqual(disposed.calls.slice(-1)[0], { id: 'aim', point: null });
assert.strictEqual(disposed.target.listeners.size, 0, 'dispose removes every listener');
assert.throws(() => disposed.adapter.enable(), /disposed/);

console.log('OK: pointer IK adapter mapping, primary input, clearing and disposal');
