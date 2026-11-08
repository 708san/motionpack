/* Experimental host-facing node interaction adapter for MotionPack v0.4. */
(function(root, factory) {
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.MotionPackInteractionAdapter = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function(root) {
  'use strict';

  function create(options) {
    if (!options || typeof options !== 'object' || Array.isArray(options)) {
      throw new TypeError('interaction adapter options are required');
    }
    const { target, manifest, getPose, assetSizes, getDrawableNodeIds, hitTest, emit } = options;
    if (!target || typeof target.addEventListener !== 'function'
        || typeof target.removeEventListener !== 'function'
        || typeof target.getBoundingClientRect !== 'function') {
      throw new TypeError('interaction adapter requires an event target with bounds');
    }
    if (!manifest || manifest.version !== '0.4' || !Array.isArray(manifest.nodes)
        || typeof getPose !== 'function' || typeof emit !== 'function'
        || !hitTest || typeof hitTest.hitTest !== 'function') {
      throw new TypeError('interaction adapter requires a v0.4 manifest, pose and hit tester');
    }
    const logicalWidth = manifest.canvas && manifest.canvas.width;
    const logicalHeight = manifest.canvas && manifest.canvas.height;
    if (!Number.isFinite(logicalWidth) || logicalWidth <= 0
        || !Number.isFinite(logicalHeight) || logicalHeight <= 0) {
      throw new TypeError('interaction adapter canvas dimensions must be positive');
    }
    const globalTarget = options.globalTarget || root.window || target;
    const nodes = new Map(manifest.nodes.filter(node => node && typeof node.id === 'string')
      .map(node => [node.id, node]));
    const hasHoverOptIn = manifest.nodes.some(node => node && node.interaction?.hover === true);
    let hovered = null;
    let touch = null;
    let disposed = false;

    function optedIn(nodeId, flag) {
      const interaction = nodes.get(nodeId)?.interaction;
      return !!interaction && interaction[flag] === true;
    }

    function pointFrom(event) {
      if (!event || !Number.isFinite(event.clientX) || !Number.isFinite(event.clientY)) return null;
      let rect;
      try { rect = target.getBoundingClientRect(); } catch (_) { return null; }
      if (!rect || !Number.isFinite(rect.left) || !Number.isFinite(rect.top)
          || !Number.isFinite(rect.width) || !Number.isFinite(rect.height)
          || rect.width <= 0 || rect.height <= 0) return null;
      const point = [(event.clientX - rect.left) * logicalWidth / rect.width,
        (event.clientY - rect.top) * logicalHeight / rect.height];
      return point.every(Number.isFinite) && point[0] >= 0 && point[0] < logicalWidth
        && point[1] >= 0 && point[1] < logicalHeight ? point : null;
    }

    function topNode(event) {
      const point = pointFrom(event);
      if (!point) return null;
      let pose;
      try { pose = getPose(); } catch (_) { return null; }
      let nodeIds;
      try { nodeIds = typeof getDrawableNodeIds === 'function' ? getDrawableNodeIds() : undefined; }
      catch (_) { return null; }
      try { return hitTest.hitTest(pose, point, { assetSizes, nodeIds }) || null; }
      catch (_) { return null; }
    }

    function send(type, nodeId, input) {
      try { emit(Object.freeze({ type, nodeId, input })); } catch (_) { /* Host callback failures do not escape into rendering. */ }
    }

    function updateHover(nodeId, input) {
      const next = nodeId && optedIn(nodeId, 'hover') ? nodeId : null;
      if (next === hovered) return;
      const previous = hovered;
      hovered = next;
      if (previous) send('hoverleave', previous, input);
      if (disposed || hovered !== next) return;
      if (hovered) send('hoverenter', hovered, input);
    }

    function onPointerMove(event) {
      if (disposed || event.isPrimary === false
          || (event.pointerType !== 'mouse' && event.pointerType !== 'pen')) return;
      if (!hasHoverOptIn && !hovered) return;
      const nodeId = topNode(event);
      updateHover(nodeId, event.pointerType);
    }

    function onPointerLeave(event) {
      if (disposed || event.isPrimary === false
          || (event.pointerType !== 'mouse' && event.pointerType !== 'pen')) return;
      updateHover(null, event.pointerType);
    }

    function onPointerDown(event) {
      if (disposed || event.isPrimary === false || event.pointerType !== 'touch') return;
      if (touch) return;
      const nodeId = topNode(event);
      touch = { id: event.pointerId, nodeId };
    }

    function clearTouch(event, complete) {
      if (disposed || !touch || event.pointerId !== touch.id) return;
      const started = touch;
      touch = null;
      if (!complete || event.isPrimary === false || event.pointerType !== 'touch' || !started.nodeId) return;
      const endedAt = topNode(event);
      if (endedAt === started.nodeId && optedIn(started.nodeId, 'tap')) {
        send('tap', started.nodeId, 'touch');
      }
    }

    function onPointerUp(event) { clearTouch(event, true); }
    function onPointerCancel(event) { clearTouch(event, false); }

    function onClick(event) {
      if (disposed || (event.pointerType !== 'mouse' && event.pointerType !== 'pen')) return;
      const nodeId = topNode(event);
      if (nodeId && optedIn(nodeId, 'click')) send('click', nodeId, event.pointerType);
    }

    const listeners = [
      [target, 'pointermove', onPointerMove], [target, 'pointerleave', onPointerLeave],
      [target, 'pointerdown', onPointerDown], [globalTarget, 'pointerup', onPointerUp],
      [globalTarget, 'pointercancel', onPointerCancel], [target, 'click', onClick]
    ];
    for (const [element, type, listener] of listeners) element.addEventListener(type, listener);

    return Object.freeze({
      activate(nodeId) {
        if (disposed) return false;
        if (typeof nodeId !== 'string' || !optedIn(nodeId, 'click')) return false;
        send('click', nodeId, 'keyboard');
        return true;
      },
      dispose() {
        if (disposed) return;
        disposed = true;
        for (const [element, type, listener] of listeners) {
          element.removeEventListener(type, listener);
        }
        touch = null;
        hovered = null;
      }
    });
  }

  return Object.freeze({ create });
});
