/* Experimental DOM-free hit testing for a sampled MotionPack pose. */
(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.MotionPackHitTest = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';

  const identity = Object.freeze({ a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 });

  function localMatrix(node) {
    if ((node.x !== undefined && node.x !== null && !Number.isFinite(node.x))
        || (node.y !== undefined && node.y !== null && !Number.isFinite(node.y))
        || (node.rotation !== undefined && node.rotation !== null && !Number.isFinite(node.rotation))) return null;
    const x = node.x || 0;
    const y = node.y || 0;
    const rotation = (node.rotation || 0) * Math.PI / 180;
    const scale = node.scale ?? 1;
    if (![x, y, rotation, scale].every(Number.isFinite)) return null;
    const cosine = Math.cos(rotation);
    const sine = Math.sin(rotation);
    return {
      a: cosine * scale, b: sine * scale,
      c: -sine * scale, d: cosine * scale,
      e: x, f: y
    };
  }

  function multiply(parent, child) {
    return {
      a: parent.a * child.a + parent.c * child.b,
      b: parent.b * child.a + parent.d * child.b,
      c: parent.a * child.c + parent.c * child.d,
      d: parent.b * child.c + parent.d * child.d,
      e: parent.a * child.e + parent.c * child.f + parent.e,
      f: parent.b * child.e + parent.d * child.f + parent.f
    };
  }

  function worldMatrix(id, nodes, cache) {
    if (cache.has(id)) return cache.get(id);
    const chain = [];
    const visiting = new Set();
    let current = id;
    let parent = identity;
    while (current) {
      if (cache.has(current)) {
        parent = cache.get(current);
        break;
      }
      if (visiting.has(current)) return null;
      const node = nodes.get(current);
      if (!node || typeof node !== 'object' || node.id !== current) return null;
      const local = localMatrix(node);
      if (!local) return null;
      visiting.add(current);
      chain.push([current, local]);
      current = node.parent || null;
    }
    for (let index = chain.length - 1; index >= 0; index--) {
      const [nodeId, local] = chain[index];
      parent = multiply(parent, local);
      if (!Object.values(parent).every(Number.isFinite)) return null;
      cache.set(nodeId, parent);
    }
    return cache.get(id) || null;
  }

  function intrinsicSize(assetSizes, asset) {
    if (assetSizes instanceof Map) return assetSizes.get(asset);
    if (assetSizes && typeof assetSizes === 'object'
        && Object.prototype.hasOwnProperty.call(assetSizes, asset)) return assetSizes[asset];
    return null;
  }

  function nodeSize(node, assetSizes) {
    const intrinsic = intrinsicSize(assetSizes, node.asset);
    const width = node.width || (intrinsic && intrinsic.width);
    const height = node.height || (intrinsic && intrinsic.height);
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
    return [width, height];
  }

  function contains(node, matrix, point, assetSizes) {
    if (!node.asset) return false;
    const opacity = node.opacity ?? 1;
    if (!Number.isFinite(opacity) || opacity <= 0) return false;
    const size = nodeSize(node, assetSizes);
    if (!size) return false;
    const [width, height] = size;
    const anchor = node.anchor || [0.5, 0.5];
    const anchorX = anchor[0] ?? 0.5;
    const anchorY = anchor[1] ?? 0.5;
    if (!Number.isFinite(anchorX) || !Number.isFinite(anchorY)) return false;
    const determinant = matrix.a * matrix.d - matrix.b * matrix.c;
    if (!Number.isFinite(determinant) || determinant === 0) return false;
    const dx = point[0] - matrix.e;
    const dy = point[1] - matrix.f;
    const x = (matrix.d * dx - matrix.c * dy) / determinant;
    const y = (-matrix.b * dx + matrix.a * dy) / determinant;
    if (!Number.isFinite(x) || !Number.isFinite(y)) return false;
    const left = -anchorX * width;
    const top = -anchorY * height;
    return x >= left && x <= left + width && y >= top && y <= top + height;
  }

  function hitTest(pose, point, options = {}) {
    if (!pose || !(pose.nodes instanceof Map) || !Array.isArray(point)
        || point.length !== 2 || !point.every(Number.isFinite)
        || !options || typeof options !== 'object' || Array.isArray(options)) return null;
    const { assetSizes, nodeIds } = options;
    if (nodeIds !== undefined && !(nodeIds instanceof Set) && !Array.isArray(nodeIds)) return null;
    const allowed = nodeIds === undefined ? null : new Set(nodeIds);
    const nodes = pose.nodes;
    const ordered = [...nodes.entries()].map(([id, node], index) => {
      const rawZ = node && node.z || 0;
      const numericZ = typeof rawZ === 'number' || typeof rawZ === 'string' ? Number(rawZ) : 0;
      return { id, node, index, z: Number.isFinite(numericZ) ? numericZ : 0 };
    }).sort((first, second) => first.z - second.z || first.index - second.index);
    const cache = new Map();
    for (let index = ordered.length - 1; index >= 0; index--) {
      const { id, node } = ordered[index];
      if (!node || typeof node !== 'object' || (allowed && !allowed.has(id))) continue;
      const matrix = worldMatrix(id, nodes, cache);
      if (matrix && contains(node, matrix, point, assetSizes)) return id;
    }
    return null;
  }

  function create() {
    return Object.freeze({ hitTest });
  }

  return Object.freeze({ create, hitTest });
});
