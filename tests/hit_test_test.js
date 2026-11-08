const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const hitTest = require('../runtime/hit_test.js');

function node(id, fields = {}) {
  return { id, asset: `${id}.png`, x: 0, y: 0, scale: 1, rotation: 0,
    width: 20, height: 10, anchor: [0.5, 0.5], opacity: 1, z: 0, ...fields };
}

function pose(...nodes) {
  return { nodes: new Map(nodes.map(item => [item.id, item])) };
}

const centered = hitTest.create();
const browserSandbox = {};
vm.runInNewContext(fs.readFileSync(require.resolve('../runtime/hit_test.js'), 'utf8'), browserSandbox);
assert.strictEqual(typeof browserSandbox.MotionPackHitTest.hitTest, 'function',
  'explicit browser script loading exposes the experimental helper');
assert.strictEqual(centered.hitTest(pose(node('box', { x: 50, y: 40 })), [50, 40]), 'box');
assert.strictEqual(centered.hitTest(pose(node('box', { x: 50, y: 40 })), [60, 45]), 'box',
  'rectangle edges are inclusive');
assert.strictEqual(centered.hitTest(pose(node('box', { x: 50, y: 40 })), [60.01, 45]), null);
assert.strictEqual(centered.hitTest(pose(node('box', { x: 50, y: 40, anchor: [0, 0] })), [50, 40]), 'box');
assert.strictEqual(centered.hitTest(pose(node('box', { x: 50, y: 40, anchor: [0, 0] })), [49.9, 40]), null);

const rotated = pose(node('rotated', { x: 50, y: 50, rotation: 90 }));
assert.strictEqual(centered.hitTest(rotated, [50, 59]), 'rotated', 'rotated rectangle interior hits');
assert.strictEqual(centered.hitTest(rotated, [50, 61]), null, 'rotated rectangle exterior misses');
assert.strictEqual(centered.hitTest(pose(node('mirrored', { x: 20, scale: -1 })), [15, 0]), 'mirrored',
  'negative scale mirrors the drawable bounds');

const nested = pose(
  node('parent', { x: 100, y: 100, rotation: 90, width: 1, height: 1, asset: null }),
  node('child', { parent: 'parent', x: 10, y: 0 })
);
assert.strictEqual(centered.hitTest(nested, [100, 110]), 'child', 'parent transform applies to child');
assert.strictEqual(centered.hitTest(nested, [115, 100]), null);
const singularParent = pose(
  node('singular_parent', { scale: 0, asset: null }),
  node('singular_child', { parent: 'singular_parent' })
);
assert.strictEqual(centered.hitTest(singularParent, [0, 0]), null, 'singular parent transforms do not hit');

const overlapping = pose(
  node('lower', { x: 10, y: 10, width: 40, height: 40, z: 0 }),
  node('upper', { x: 10, y: 10, width: 20, height: 20, z: 1 }),
  node('equal_z_last', { x: 10, y: 10, width: 10, height: 10, z: 1 })
);
assert.strictEqual(centered.hitTest(overlapping, [10, 10]), 'equal_z_last',
  'last drawn node wins equal-Z ties');
assert.strictEqual(centered.hitTest(overlapping, [10, 10], { nodeIds: new Set(['lower']) }), 'lower',
  'host may filter nodes by ID before selecting the topmost hit');
assert.strictEqual(centered.hitTest(pose(
  node('numeric_z', { x: 0, y: 0, z: '2' }), node('lower_z', { x: 0, y: 0, z: 1 })
), [0, 0]), 'numeric_z', 'Z sorting follows the renderer numeric comparator');

const invisible = pose(
  node('visible', { x: 5, y: 5, width: 30, height: 30, z: 0 }),
  node('transparent', { x: 5, y: 5, width: 30, height: 30, opacity: 0, z: 1 })
);
assert.strictEqual(centered.hitTest(invisible, [5, 5]), 'visible', 'zero-opacity nodes are excluded');

const intrinsic = pose(node('intrinsic', { x: 40, y: 30, width: undefined, height: undefined }));
assert.strictEqual(centered.hitTest(intrinsic, [49, 34], {
  assetSizes: { 'intrinsic.png': { width: 20, height: 10 } }
}), 'intrinsic', 'host intrinsic asset dimensions supply omitted node dimensions');
assert.strictEqual(centered.hitTest(intrinsic, [49, 34]), null, 'missing intrinsic dimensions cannot hit');

assert.strictEqual(centered.hitTest(pose(node('flat', { scale: 0 })), [0, 0]), null,
  'singular transforms do not hit');
assert.strictEqual(centered.hitTest(pose(node('bad', { x: NaN })), [0, 0]), null,
  'non-finite node geometry does not hit');
assert.strictEqual(centered.hitTest(pose(node('box')), [NaN, 0]), null,
  'non-finite canvas points do not hit');
assert.strictEqual(centered.hitTest({ nodes: [] }, [0, 0]), null,
  'invalid pose data does not throw');
assert.strictEqual(centered.hitTest({ nodes: new Map([['wrong_key', node('different_id')]]) }, [0, 0]), null,
  'pose map keys must match node IDs');

const deepNodes = [];
for (let index = 0; index < 5000; index++) {
  deepNodes.push(node(`deep_${index}`, {
    parent: index === 0 ? undefined : `deep_${index - 1}`,
    asset: index === 4999 ? 'deep.png' : null
  }));
}
assert.strictEqual(centered.hitTest(pose(...deepNodes), [0, 0]), 'deep_4999',
  'deep parent chains do not rely on recursive stack depth');

console.log('OK: transformed logical-canvas hit testing, ordering, filtering and invalid geometry');
