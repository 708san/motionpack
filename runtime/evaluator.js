/* Stateless MotionPack pose evaluator. No browser or scheduling APIs required. */
(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.MotionPackEvaluator = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';

  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const mix = (a, b, amount) => a + (b - a) * amount;
  const hasOwn = (value, key) => Object.prototype.hasOwnProperty.call(value, key);

  function sampleTrack(keys, timeMs) {
    if (timeMs <= keys[0].time_ms) return keys[0].value;
    for (let i = 1; i < keys.length; i++) {
      if (timeMs <= keys[i].time_ms) {
        const before = keys[i - 1], after = keys[i];
        const amount = clamp((timeMs - before.time_ms) / (after.time_ms - before.time_ms), 0, 1);
        const eased = amount * amount * (3 - 2 * amount);
        return mix(before.value, after.value, eased);
      }
    }
    return keys[keys.length - 1].value;
  }

  function sample(manifest, options, rig) {
    if (!manifest || typeof manifest !== 'object' || !options || typeof options !== 'object') {
      throw new TypeError('manifest and sample options are required');
    }
    const clipName = options.clip ?? manifest.defaults?.clip;
    const variantName = options.variant ?? manifest.defaults?.variant;
    const clips = manifest.clips || {}, variants = manifest.variants || {};
    const clip = hasOwn(clips, clipName) ? clips[clipName] : undefined;
    const variant = hasOwn(variants, variantName) ? variants[variantName] : undefined;
    const requestedTime = options.timeMs ?? 0;
    if (!clip) throw new RangeError(`unknown clip: ${clipName}`);
    if (!variant) throw new RangeError(`unknown variant: ${variantName}`);
    if (hasOwn(clip, 'loop') && typeof clip.loop !== 'boolean') {
      throw new TypeError('clip loop must be a boolean');
    }
    if (!Number.isFinite(requestedTime) || requestedTime < 0) {
      throw new RangeError('timeMs must be a finite nonnegative number');
    }
    if (!Number.isFinite(clip.duration_ms) || clip.duration_ms <= 0) {
      throw new RangeError('clip duration must be positive');
    }

    const timeMs = clip.loop
      ? ((requestedTime % clip.duration_ms) + clip.duration_ms) % clip.duration_ms
      : Math.min(requestedTime, clip.duration_ms);
    const nodes = new Map((manifest.nodes || []).map(node => [node.id, { ...node }]));
    for (const [id, values] of Object.entries(variant.nodes || {})) {
      const node = nodes.get(id);
      if (!node) throw new RangeError(`variant references unknown node: ${id}`);
      nodes.set(id, { ...node, ...values });
    }
    for (const track of clip.tracks || []) {
      const node = nodes.get(track.node);
      if (!node) throw new RangeError(`clip references unknown node: ${track.node}`);
      Object.defineProperty(node, track.property, {
        value: sampleTrack(track.keys, timeMs), enumerable: true, configurable: true, writable: true
      });
    }

    const iks = manifest.iks || [];
    if (iks.length) {
      if (!rig || typeof rig.applyIK !== 'function') {
        throw new TypeError('a rig with applyIK is required for manifests with IK');
      }
      const targets = Object.fromEntries(iks.map(ik => [ik.id, [...ik.target]]));
      for (const track of clip.ik_tracks || []) {
        const target = hasOwn(targets, track.ik) ? targets[track.ik] : undefined;
        if (!target) throw new RangeError(`clip references unknown IK chain: ${track.ik}`);
        target[track.axis === 'x' ? 0 : 1] = sampleTrack(track.keys, timeMs);
      }
      if (options.ikTargets != null &&
          (typeof options.ikTargets !== 'object' || Array.isArray(options.ikTargets))) {
        throw new TypeError('ikTargets must be an object keyed by IK chain ID');
      }
      for (const [id, target] of Object.entries(options.ikTargets || {})) {
        if (!hasOwn(targets, id) || !Array.isArray(target) || target.length !== 2 ||
            !target.every(Number.isFinite)) {
          throw new RangeError(`invalid IK target: ${id}`);
        }
        targets[id] = [...target];
      }
      rig.applyIK(nodes, iks, targets);
    } else if (options.ikTargets && Object.keys(options.ikTargets).length) {
      throw new RangeError('IK targets were provided for a manifest without IK');
    }

    const effects = (clip.effects || []).filter(effect =>
      timeMs >= effect.start_ms && timeMs <= effect.start_ms + effect.duration_ms
    ).map(effect => ({
      ...effect,
      offset: effect.offset ? [...effect.offset] : effect.offset,
      target: effect.target ? [...effect.target] : effect.target,
      age_ms: timeMs - effect.start_ms,
      progress: (timeMs - effect.start_ms) / effect.duration_ms
    }));
    return { clip: clipName, variant: variantName, timeMs, nodes, effects };
  }

  return Object.freeze({ sample });
});
