/* Experimental DOM adapter for pointer-driven IK targets. */
(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.MotionPackPointerIKAdapter = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';

  function create(options) {
    if (!options || typeof options !== 'object' || Array.isArray(options)) {
      throw new TypeError('pointer IK adapter options are required');
    }
    const { target, controller, ikId, logicalWidth, logicalHeight } = options;
    if (!target || typeof target.addEventListener !== 'function'
        || typeof target.removeEventListener !== 'function'
        || typeof target.getBoundingClientRect !== 'function') {
      throw new TypeError('pointer IK adapter requires an event target with bounds');
    }
    if (!controller || typeof controller.setIKTarget !== 'function') {
      throw new TypeError('pointer IK adapter requires a player controller');
    }
    if (typeof ikId !== 'string' || !ikId
        || !Number.isFinite(logicalWidth) || logicalWidth <= 0
        || !Number.isFinite(logicalHeight) || logicalHeight <= 0) {
      throw new TypeError('pointer IK adapter dimensions and chain ID must be valid');
    }

    let enabled = false;
    let disposed = false;
    let activePointer = null;
    let hasTarget = false;

    function clearTarget() {
      if (!hasTarget) return;
      hasTarget = false;
      controller.setIKTarget(ikId, null);
    }

    function clearPointer() {
      activePointer = null;
      clearTarget();
    }

    function update(event) {
      let rect;
      try {
        rect = target.getBoundingClientRect();
      } catch (_) {
        clearTarget();
        return;
      }
      if (!rect || !Number.isFinite(rect.left) || !Number.isFinite(rect.top)
          || !Number.isFinite(rect.width) || !Number.isFinite(rect.height)
          || rect.width <= 0 || rect.height <= 0
          || !Number.isFinite(event.clientX) || !Number.isFinite(event.clientY)) {
        clearTarget();
        return;
      }
      const x = (event.clientX - rect.left) * logicalWidth / rect.width;
      const y = (event.clientY - rect.top) * logicalHeight / rect.height;
      if (!Number.isFinite(x) || !Number.isFinite(y)) {
        clearTarget();
        return;
      }
      controller.setIKTarget(ikId, [x, y]);
      hasTarget = true;
    }

    function primary(event) {
      return event && event.isPrimary !== false;
    }

    function onDown(event) {
      if (!enabled || !primary(event)) return;
      if (activePointer && activePointer.id !== event.pointerId) return;
      activePointer = { id: event.pointerId, type: event.pointerType };
      update(event);
    }

    function onMove(event) {
      if (!enabled || !primary(event)) return;
      if (activePointer) {
        if (activePointer.id !== event.pointerId) return;
      } else if (event.pointerType === 'touch') {
        return;
      }
      update(event);
    }

    function onEnd(event) {
      if (!enabled || !primary(event) || !activePointer
          || activePointer.id !== event.pointerId) return;
      clearPointer();
    }

    function onLeave(event) {
      if (!enabled || !primary(event)) return;
      if (activePointer && activePointer.id !== event.pointerId) return;
      clearPointer();
    }

    const listeners = {
      pointerdown: onDown,
      pointermove: onMove,
      pointerup: onEnd,
      pointercancel: onEnd,
      pointerleave: onLeave
    };
    for (const [name, listener] of Object.entries(listeners)) {
      target.addEventListener(name, listener);
    }

    return Object.freeze({
      enable() {
        if (disposed) throw new Error('pointer IK adapter has been disposed');
        enabled = true;
      },
      disable() {
        if (disposed) return;
        enabled = false;
        clearPointer();
      },
      dispose() {
        if (disposed) return;
        disposed = true;
        enabled = false;
        try {
          clearPointer();
        } finally {
          for (const [name, listener] of Object.entries(listeners)) {
            target.removeEventListener(name, listener);
          }
        }
      }
    });
  }

  return Object.freeze({ create });
});
