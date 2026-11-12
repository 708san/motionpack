/* Host-driven MotionPack playback state. No DOM, clock, or rendering APIs. */
(function(root, factory) {
  const evaluator = typeof module === 'object' && module.exports
    ? require('./evaluator.js')
    : root.MotionPackEvaluator;
  const api = factory(evaluator);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.MotionPackPlayerController = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function(Evaluator) {
  'use strict';

  const hasOwn = (value, key) => Object.prototype.hasOwnProperty.call(value, key);

  class PlayerController {
    constructor(options) {
      if (options !== undefined && (!options || typeof options !== 'object' || Array.isArray(options))) {
        throw new TypeError('controller options are required');
      }
      if (!Evaluator || typeof Evaluator.sample !== 'function') {
        throw new Error('MotionPackEvaluator is required');
      }

      this._manifest = null;
      this._rig = null;
      this._clip = null;
      this._variant = null;
      this._timeMs = 0;
      this._state = 'unloaded';
      this._disposed = false;
      this._ikTargets = Object.create(null);

      if (options !== undefined) {
        if (!options.manifest || typeof options.manifest !== 'object' || Array.isArray(options.manifest)) {
          throw new TypeError('a validated manifest is required');
        }
        this.load(options);
      }
    }

    _assertActive() {
      if (this._disposed) throw new Error('player controller has been disposed');
    }

    _assertLoaded() {
      if (!this._manifest) throw new Error('player controller is not loaded');
    }

    _clipInfo(name, manifest = this._manifest) {
      const clips = manifest.clips || {};
      const clip = hasOwn(clips, name) ? clips[name] : undefined;
      if (!clip) throw new RangeError(`unknown clip: ${name}`);
      if (hasOwn(clip, 'loop') && typeof clip.loop !== 'boolean') {
        throw new TypeError('clip loop must be a boolean');
      }
      if (!Number.isFinite(clip.duration_ms) || clip.duration_ms <= 0) {
        throw new RangeError('clip duration must be positive');
      }
      return clip;
    }

    _variantInfo(name, manifest = this._manifest) {
      const variants = manifest.variants || {};
      if (!hasOwn(variants, name)) throw new RangeError(`unknown variant: ${name}`);
      return variants[name];
    }

    load(options) {
      this._assertActive();
      if (!options || typeof options !== 'object' || Array.isArray(options)) {
        throw new TypeError('load options are required');
      }
      const manifest = options.manifest;
      if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)) {
        throw new TypeError('a validated manifest is required');
      }
      const rig = options.rig;
      const defaults = manifest.defaults;
      const clipName = options.clip ?? (defaults && hasOwn(defaults, 'clip') ? defaults.clip : undefined);
      const variantName = options.variant ?? (defaults && hasOwn(defaults, 'variant') ? defaults.variant : undefined);
      this._clipInfo(clipName, manifest);
      this._variantInfo(variantName, manifest);

      const ikTargets = Object.create(null);
      const pose = Evaluator.sample(manifest, {
        clip: clipName,
        variant: variantName,
        timeMs: 0,
        ikTargets
      }, rig);

      this._manifest = manifest;
      this._rig = rig;
      this._clip = clipName;
      this._variant = variantName;
      this._timeMs = 0;
      this._state = 'stopped';
      this._ikTargets = ikTargets;
      return pose;
    }

    unload() {
      this._assertActive();
      if (!this._manifest) return false;
      this._manifest = null;
      this._rig = null;
      this._clip = null;
      this._variant = null;
      this._ikTargets = Object.create(null);
      this._timeMs = 0;
      this._state = 'unloaded';
      return true;
    }

    _normalizeTime(timeMs, clip) {
      if (clip.loop) return timeMs % clip.duration_ms;
      return Math.min(timeMs, clip.duration_ms);
    }

    play(clipName) {
      this._assertActive();
      this._assertLoaded();
      if (clipName !== undefined) {
        this._clipInfo(clipName);
        this._clip = clipName;
      }
      this._timeMs = 0;
      this._state = 'playing';
      return this.getPose();
    }

    pause() {
      this._assertActive();
      this._assertLoaded();
      if (this._state !== 'playing') return false;
      this._state = 'paused';
      return true;
    }

    resume() {
      this._assertActive();
      this._assertLoaded();
      if (this._state !== 'paused') return false;
      this._state = 'playing';
      return true;
    }

    stop() {
      this._assertActive();
      this._assertLoaded();
      this._timeMs = 0;
      this._state = 'stopped';
      return this.getPose();
    }

    seek(timeMs) {
      this._assertActive();
      this._assertLoaded();
      if (!Number.isFinite(timeMs) || timeMs < 0) {
        throw new RangeError('timeMs must be a finite nonnegative number');
      }
      const clip = this._clipInfo(this._clip);
      this._timeMs = this._normalizeTime(timeMs, clip);
      if (!clip.loop && this._timeMs >= clip.duration_ms) this._state = 'ended';
      else if (this._state === 'ended' || this._state === 'stopped') this._state = 'paused';
      return this.getPose();
    }

    advance(deltaMs) {
      this._assertActive();
      this._assertLoaded();
      if (!Number.isFinite(deltaMs) || deltaMs < 0) {
        throw new RangeError('deltaMs must be a finite nonnegative number');
      }
      if (this._state === 'playing' && deltaMs > 0) {
        const clip = this._clipInfo(this._clip);
        if (clip.loop) {
          const duration = clip.duration_ms;
          const delta = deltaMs % duration;
          const untilWrap = duration - this._timeMs;
          this._timeMs = delta >= untilWrap ? delta - untilWrap : this._timeMs + delta;
        } else if (deltaMs >= clip.duration_ms - this._timeMs) {
          this._timeMs = clip.duration_ms;
          this._state = 'ended';
        } else {
          this._timeMs += deltaMs;
        }
      }
      return this.getPose();
    }

    setVariant(variantName) {
      this._assertActive();
      this._assertLoaded();
      this._variantInfo(variantName);
      this._variant = variantName;
      return this.getPose();
    }

    setIKTarget(ikId, targetOrNull) {
      this._assertActive();
      this._assertLoaded();
      const iks = Array.isArray(this._manifest.iks) ? this._manifest.iks : [];
      if (!iks.some(ik => ik && ik.id === ikId)) {
        throw new RangeError(`unknown IK chain: ${ikId}`);
      }
      if (targetOrNull === null) {
        delete this._ikTargets[ikId];
      } else {
        if (!Array.isArray(targetOrNull) || targetOrNull.length !== 2) {
          throw new RangeError(`invalid IK target: ${ikId}`);
        }
        const x = targetOrNull[0];
        const y = targetOrNull[1];
        if (!Number.isFinite(x) || !Number.isFinite(y)) {
          throw new RangeError(`invalid IK target: ${ikId}`);
        }
        this._ikTargets[ikId] = [x, y];
      }
      return this.getPose();
    }

    getPose() {
      this._assertActive();
      this._assertLoaded();
      return Evaluator.sample(this._manifest, {
        clip: this._clip,
        variant: this._variant,
        timeMs: this._timeMs,
        ikTargets: this._ikTargets
      }, this._rig);
    }

    getState() {
      if (this._disposed) {
        return Object.freeze({ state: 'disposed', clip: null, variant: null, timeMs: 0, durationMs: 0, loop: false });
      }
      if (!this._manifest) {
        return Object.freeze({ state: 'unloaded', clip: null, variant: null, timeMs: 0, durationMs: 0, loop: false });
      }
      const clip = this._clipInfo(this._clip);
      return Object.freeze({
        state: this._state,
        clip: this._clip,
        variant: this._variant,
        timeMs: this._timeMs,
        durationMs: clip.duration_ms,
        loop: Boolean(clip.loop)
      });
    }

    dispose() {
      if (this._disposed) return;
      this._manifest = null;
      this._rig = null;
      this._clip = null;
      this._variant = null;
      this._ikTargets = null;
      this._timeMs = 0;
      this._state = 'disposed';
      this._disposed = true;
    }
  }

  return Object.freeze({ create: options => new PlayerController(options) });
});
