/* Experimental viewport and logical-coordinate adapter for MotionPack previews. */
(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.MotionPackViewportAdapter = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';

  const HARD_LIMITS = Object.freeze({ maxDpr: 2, maxPixels: 16000000, maxDimension: 8192 });
  const DEFAULTS = Object.freeze({ fit: 'contain', alignX: 0.5, alignY: 0.5, ...HARD_LIMITS });

  function validateOptions(options) {
    const next = { ...options };
    if (next.fit !== undefined && !['contain', 'cover', 'stretch'].includes(next.fit)) {
      throw new TypeError('fit must be contain, cover, or stretch');
    }
    for (const key of ['alignX', 'alignY']) {
      if (next[key] !== undefined && (!Number.isFinite(next[key]) || next[key] < 0 || next[key] > 1)) {
        throw new RangeError(key + ' must be between 0 and 1');
      }
    }
    for (const key of ['maxDpr', 'maxPixels', 'maxDimension']) {
      if (next[key] === undefined) continue;
      const valid = key === 'maxDpr'
        ? Number.isFinite(next[key]) && next[key] > 0 && next[key] <= HARD_LIMITS.maxDpr
        : Number.isInteger(next[key]) && next[key] >= 1 && next[key] <= HARD_LIMITS[key];
      if (!valid) throw new RangeError(key + ' exceeds its supported viewport limit');
    }
    return next;
  }

  function create(options) {
    if (!options || typeof options !== 'object' || Array.isArray(options)) {
      throw new TypeError('viewport options are required');
    }
    const { target, logicalWidth, logicalHeight } = options;
    if (!target || typeof target.getBoundingClientRect !== 'function') {
      throw new TypeError('viewport requires a canvas or element with bounds');
    }
    if (![logicalWidth, logicalHeight].every(Number.isFinite) || logicalWidth <= 0 || logicalHeight <= 0) {
      throw new RangeError('logical canvas dimensions must be finite and positive');
    }

    let settings = { ...DEFAULTS, ...validateOptions(options) };
    let state = null;
    let disposed = false;
    const readDpr = typeof options.getDevicePixelRatio === 'function'
      ? options.getDevicePixelRatio
      : () => typeof window !== 'undefined' && Number.isFinite(window.devicePixelRatio)
        ? window.devicePixelRatio : 1;

    function update() {
      if (disposed) throw new Error('viewport has been disposed');
      let rect;
      try { rect = target.getBoundingClientRect(); } catch (_) { state = null; return null; }
      if (!rect || ![rect.left, rect.top, rect.width, rect.height].every(Number.isFinite)
          || rect.width <= 0 || rect.height <= 0) {
        state = null;
        return null;
      }
      const cssWidth = rect.width, cssHeight = rect.height;
      let fitX = cssWidth / logicalWidth, fitY = cssHeight / logicalHeight;
      if (settings.fit !== 'stretch') {
        const uniform = settings.fit === 'cover' ? Math.max(fitX, fitY) : Math.min(fitX, fitY);
        fitX = fitY = uniform;
      }
      const contentWidth = logicalWidth * fitX, contentHeight = logicalHeight * fitY;
      const offsetCssX = (cssWidth - contentWidth) * settings.alignX;
      const offsetCssY = (cssHeight - contentHeight) * settings.alignY;

      let dpr = 1;
      try { dpr = readDpr(); } catch (_) { dpr = 1; }
      if (!Number.isFinite(dpr) || dpr <= 0) dpr = 1;
      dpr = Math.min(dpr, settings.maxDpr);
      let bitmapWidth = Math.max(logicalWidth, cssWidth * dpr);
      let bitmapHeight = Math.max(logicalHeight, cssHeight * dpr);
      const cap = Math.min(1, settings.maxDimension / bitmapWidth,
        settings.maxDimension / bitmapHeight,
        Math.sqrt(settings.maxPixels / (bitmapWidth * bitmapHeight)));
      bitmapWidth = Math.max(1, Math.floor(bitmapWidth * cap));
      bitmapHeight = Math.max(1, Math.floor(bitmapHeight * cap));
      if (bitmapWidth !== target.width) target.width = bitmapWidth;
      if (bitmapHeight !== target.height) target.height = bitmapHeight;

      const bufferScaleX = bitmapWidth / cssWidth;
      const bufferScaleY = bitmapHeight / cssHeight;
      state = Object.freeze({
        cssWidth, cssHeight, bitmapWidth, bitmapHeight, fit: settings.fit,
        scaleX: fitX * bufferScaleX, scaleY: fitY * bufferScaleY,
        offsetX: offsetCssX * bufferScaleX, offsetY: offsetCssY * bufferScaleY,
        contentWidth, contentHeight, offsetCssX, offsetCssY,
        logicalWidth, logicalHeight
      });
      return state;
    }

    function clientToLogical(clientX, clientY) {
      if (disposed || !Number.isFinite(clientX) || !Number.isFinite(clientY)) return null;
      const rect = target.getBoundingClientRect();
      if (!rect || ![rect.left, rect.top, rect.width, rect.height].every(Number.isFinite)
          || rect.width <= 0 || rect.height <= 0) return null;
      const current = update();
      if (!current) return null;
      const cssX = clientX - rect.left, cssY = clientY - rect.top;
      if (cssX < 0 || cssY < 0 || cssX >= rect.width || cssY >= rect.height) return null;
      const point = [(cssX - current.offsetCssX) / (current.contentWidth / logicalWidth),
        (cssY - current.offsetCssY) / (current.contentHeight / logicalHeight)];
      return point.every(Number.isFinite) && point[0] >= 0 && point[0] < logicalWidth
        && point[1] >= 0 && point[1] < logicalHeight ? point : null;
    }

    return Object.freeze({
      update,
      clientToLogical,
      apply(context) {
        const current = update();
        if (!current) return false;
        context.setTransform(current.scaleX, 0, 0, current.scaleY, current.offsetX, current.offsetY);
        return true;
      },
      configure(next) {
        if (disposed) throw new Error('viewport has been disposed');
        settings = { ...settings, ...validateOptions(next || {}) };
        return update();
      },
      getState() { return disposed ? null : update(); },
      dispose() { disposed = true; state = null; }
    });
  }

  return Object.freeze({ create });
});
