const assert = require('assert');
const Viewport = require('../runtime/viewport_adapter.js');

function fakeTarget(width, height, left = 10, top = 20) {
  return {
    width: 0, height: 0,
    rect: { left, top, width, height },
    getBoundingClientRect() { return this.rect; }
  };
}

const canvas = fakeTarget(910, 550);
const view = Viewport.create({ target: canvas, logicalWidth: 910, logicalHeight: 550,
  getDevicePixelRatio: () => 1 });
let state = view.update();
assert.strictEqual(state.fit, 'contain');
assert.deepStrictEqual([state.bitmapWidth, state.bitmapHeight], [910, 550]);
assert.deepStrictEqual(view.clientToLogical(10 + 455, 20 + 275), [455, 275]);

canvas.rect = { left: 10, top: 20, width: 1000, height: 1000 };
state = view.update();
assert(Math.abs(state.contentWidth - 1000) < 1e-9);
assert.strictEqual(state.contentHeight, 1000 * 550 / 910);
assert.strictEqual(view.clientToLogical(500, 21), null, 'contain letterbox must not hit');
const center = view.clientToLogical(510, 520);
assert(Math.abs(center[0] - 455) < 1e-9);
assert(Math.abs(center[1] - 275) < 1e-9);

view.configure({ fit: 'cover' });
state = view.getState();
assert.strictEqual(state.fit, 'cover');
const croppedLeft = view.clientToLogical(11, 520);
assert(croppedLeft && Math.abs(croppedLeft[0] - 180) < 1,
  'cover maps visible viewport pixels to the corresponding cropped logical region');
assert(Math.abs(view.clientToLogical(510, 520)[0] - 455) < 1e-9);

view.configure({ fit: 'stretch' });
state = view.getState();
const stretchedOrigin = view.clientToLogical(10, 20);
assert(Math.abs(stretchedOrigin[0]) < 1e-8 && Math.abs(stretchedOrigin[1]) < 1e-8);
assert.deepStrictEqual(view.clientToLogical(1010 - 0.001, 1020 - 0.001).map(Math.floor), [909, 549]);

view.configure({ fit: 'contain', alignX: 0, alignY: 1 });
state = view.getState();
assert(Math.abs(state.offsetCssX) < 1e-9);
assert.strictEqual(state.offsetCssY, 1000 - 1000 * 550 / 910);

const hidpiCanvas = fakeTarget(800, 600);
const hidpi = Viewport.create({ target: hidpiCanvas, logicalWidth: 800, logicalHeight: 600,
  getDevicePixelRatio: () => 3 });
state = hidpi.update();
assert.deepStrictEqual([state.bitmapWidth, state.bitmapHeight], [1600, 1200]);
const cappedCanvas = fakeTarget(6000, 6000);
const capped = Viewport.create({ target: cappedCanvas, logicalWidth: 6000, logicalHeight: 6000,
  maxPixels: 16000000, maxDimension: 8192, getDevicePixelRatio: () => 2 });
state = capped.update();
assert(state.bitmapWidth * state.bitmapHeight <= 16000000);
assert(state.bitmapWidth <= 8192 && state.bitmapHeight <= 8192);
assert.throws(() => capped.configure({ alignX: 2 }), /alignX/);
assert.throws(() => capped.configure({ fit: 'fill' }), /fit/);
assert.throws(() => capped.configure({ maxDpr: 3 }), /maxDpr/);
assert.throws(() => capped.configure({ maxPixels: 16000001 }), /maxPixels/);
assert.throws(() => capped.configure({ maxDimension: 8193 }), /maxDimension/);

let transform;
assert.strictEqual(hidpi.apply({ setTransform(...args) { transform = args; } }), true);
assert.strictEqual(transform[0], hidpi.getState().scaleX);
view.dispose();
assert.strictEqual(view.clientToLogical(10, 20), null);
assert.throws(() => view.update(), /disposed/);
console.log('OK: viewport adapter geometry and limits');
