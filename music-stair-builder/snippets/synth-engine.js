/**
 * WebAudio 音色引擎：预调度、多分音、混响、压缩、软削波。
 * 作者 hoverwu · MIT · 提炼自 MusicStair v0.4.0
 *
 * 关键纪律：
 * - AudioContext.currentTime 是唯一主时钟，不用 setTimeout 逐音播放。
 * - 暂停只 stopAll()，绝不 suspend()；否则 resume 会被迟到的 suspend 再次挂起。
 */

const PARTIALS = {
  pad: {
    ratios: [1, 2.002, 3.004, 4.02, 5.41],
    gains: [1, 0.3, 0.16, 0.085, 0.045],
    decays: [1, 0.68, 0.46, 0.34, 0.26],
    release: 0.9
  },
  glass: {
    ratios: [1, 2.76, 5.4, 8.93, 13.34],
    gains: [1, 0.32, 0.18, 0.09, 0.04],
    decays: [1, 0.72, 0.5, 0.34, 0.22],
    release: 1.2
  },
  bell: {
    ratios: [1, 2.0, 3.0, 4.16, 5.43, 6.79],
    gains: [1, 0.36, 0.2, 0.12, 0.07, 0.035],
    decays: [1, 0.8, 0.62, 0.46, 0.34, 0.24],
    release: 1.5
  },
  synth: {
    ratios: [1, 2.0, 3.0],
    gains: [1, 0.22, 0.08],
    decays: [1, 0.7, 0.5],
    release: 1.0
  }
};

export function midiToFreq(midi) {
  return 440 * Math.pow(2, (midi - 69) / 12);
}

function clamp(v, a, b) {
  return v < a ? a : v > b ? b : v;
}

export class SynthEngine {
  constructor() {
    this.ctx = null;
    this.master = null;
    this.compressor = null;
    this.noise = null;
    this.volume = 0.78;
    this.muted = false;
    this.ready = false;
    this.sources = new Set();
  }

  get supported() {
    return typeof window !== 'undefined' && !!(window.AudioContext || window.webkitAudioContext);
  }

  now() {
    return this.ctx ? this.ctx.currentTime : performance.now() / 1000;
  }

  latency() {
    if (!this.ctx) return 0;
    return Math.min(0.08, this.ctx.outputLatency || this.ctx.baseLatency || 0);
  }

  isRunning() {
    return !!this.ctx && this.ctx.state === 'running';
  }

  /** 必须在用户手势的调用栈里调用。 */
  async unlock() {
    if (!this.supported) return false;
    if (!this.ctx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      this.ctx = new Ctx({ latencyHint: 'interactive' });
      this._buildGraph();
    }
    if (this.ctx.state === 'suspended') {
      try {
        await this.ctx.resume();
      } catch {
        /* 仍需用户手势 */
      }
    }
    if (this.ctx.state !== 'running') return false;

    if (!this.ready) {
      const src = this.ctx.createBufferSource();
      src.buffer = this.ctx.createBuffer(1, 1, this.ctx.sampleRate);
      src.connect(this.ctx.destination);
      src.start(0);
      this.ready = true;
    }
    return true;
  }

  _buildGraph() {
    const ctx = this.ctx;

    this.master = ctx.createGain();
    this.master.gain.value = this.muted ? 0 : this.volume;

    this.compressor = ctx.createDynamicsCompressor();
    this.compressor.threshold.value = -18;
    this.compressor.knee.value = 24;
    this.compressor.ratio.value = 4;
    this.compressor.attack.value = 0.004;
    this.compressor.release.value = 0.22;

    const shaper = ctx.createWaveShaper();
    const curve = new Float32Array(2048);
    for (let i = 0; i < curve.length; i += 1) {
      const x = (i / (curve.length - 1)) * 2 - 1;
      curve[i] = Math.tanh(x * 1.28) / Math.tanh(1.28);
    }
    shaper.curve = curve;
    shaper.oversample = '2x';

    const dry = ctx.createGain();
    dry.gain.value = 0.84;

    const wet = ctx.createGain();
    wet.gain.value = 0.3;

    const convolver = ctx.createConvolver();
    convolver.buffer = this._makeImpulse(3.6, 2.5);

    const reverbLp = ctx.createBiquadFilter();
    reverbLp.type = 'lowpass';
    reverbLp.frequency.value = 5200;

    this.master.connect(dry);
    this.master.connect(wet);
    wet.connect(convolver);
    convolver.connect(reverbLp);
    reverbLp.connect(this.compressor);
    dry.connect(this.compressor);
    this.compressor.connect(shaper);
    shaper.connect(ctx.destination);

    const len = Math.floor(ctx.sampleRate * 0.5);
    const buffer = ctx.createBuffer(1, len, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < len; i += 1) {
      const env = Math.pow(1 - i / len, 3.4);
      data[i] = (Math.random() * 2 - 1) * env;
    }
    this.noise = buffer;
  }

  _makeImpulse(seconds, decay) {
    const ctx = this.ctx;
    const rate = ctx.sampleRate;
    const len = Math.floor(rate * seconds);
    const impulse = ctx.createBuffer(2, len, rate);

    for (let ch = 0; ch < 2; ch += 1) {
      const data = impulse.getChannelData(ch);
      for (let i = 0; i < len; i += 1) {
        const t = i / len;
        const sparsity = i < rate * 0.04 ? 0.32 : 1;
        data[i] = (Math.random() * 2 - 1) * Math.pow(1 - t, decay) * sparsity;
      }
      // 几个早期反射，让混响不像纯噪声尾巴。
      [0.067, 0.113, 0.171, 0.241, 0.327].forEach((tap, k) => {
        const idx = Math.floor(tap * rate + (ch ? 13 : 0));
        if (idx < len) data[idx] += (k % 2 ? -1 : 1) * 0.2;
      });
    }
    return impulse;
  }

  setVolume(v) {
    this.volume = clamp(v, 0, 1);
    this._applyGain();
  }

  setMuted(muted) {
    this.muted = !!muted;
    this._applyGain();
  }

  _applyGain() {
    if (!this.master || !this.ctx) return;
    const now = this.ctx.currentTime;
    this.master.gain.cancelScheduledValues(now);
    this.master.gain.setTargetAtTime(this.muted ? 0 : this.volume, now, 0.03);
  }

  _panner(x = 0) {
    if (!this.ctx || !this.ctx.createStereoPanner) return null;
    const p = this.ctx.createStereoPanner();
    p.pan.value = clamp((x || 0) / 9, -1, 1) * 0.5;
    return p;
  }

  _track(node, endTime) {
    this.sources.add(node);
    node.onended = () => this.sources.delete(node);
    if (!node.__msTimer) {
      node.__msTimer = setTimeout(
        () => this.sources.delete(node),
        Math.max(50, (endTime - this.now()) * 1000 + 300)
      );
    }
    return node;
  }

  /**
   * 预约一个音。
   * @param {object} opts { midi, type, when, ring, pan, velocity }
   * @returns {{when:number, end:number}|null}
   */
  scheduleNote(opts = {}) {
    if (!this.ctx) return null;
    const {
      midi = 60,
      type = 'pad',
      when = this.ctx.currentTime + 0.01,
      ring = 1.6,
      pan = 0,
      velocity = 0.18
    } = opts;

    if (type === 'drum') return this._scheduleDrum(when, pan, velocity);

    const bank = PARTIALS[type] || PARTIALS.pad;
    const ctx = this.ctx;
    const t = Math.max(when, ctx.currentTime + 0.004);
    const freq = midiToFreq(midi);
    const panner = this._panner(pan);
    const out = ctx.createGain();
    const vel = clamp(velocity, 0.04, 0.4);
    const ringTime = clamp(ring, 0.7, 3.4);

    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.Q.value = 0.35;
    lp.frequency.setValueAtTime(type === 'glass' ? 7800 : type === 'bell' ? 6600 : 5000, t);
    lp.frequency.exponentialRampToValueAtTime(type === 'synth' ? 1600 : 2400, t + ringTime);

    out.gain.setValueAtTime(0.0001, t);
    out.gain.linearRampToValueAtTime(vel, t + 0.012);
    out.gain.exponentialRampToValueAtTime(vel * 0.34, t + 0.24);
    out.gain.exponentialRampToValueAtTime(0.0001, t + ringTime);

    const detune = (Math.random() * 2 - 1) * 3;
    bank.ratios.forEach((ratio, i) => {
      const osc = ctx.createOscillator();
      osc.type = type === 'synth' && i === 0 ? 'triangle' : 'sine';
      osc.frequency.value = freq * ratio;
      osc.detune.value = detune * (i === 0 ? 1 : 0.35);

      const g = ctx.createGain();
      const pg = bank.gains[i] * (velocity > 0.24 ? 1.1 : 1);
      g.gain.setValueAtTime(0.0001, t);
      g.gain.linearRampToValueAtTime(pg, t + 0.008 + i * 0.003);
      g.gain.exponentialRampToValueAtTime(0.0001, t + ringTime * bank.decays[i]);

      osc.connect(g);
      g.connect(lp);
      osc.start(t);
      osc.stop(t + ringTime * bank.decays[i] + 0.1);
      this._track(osc, t + ringTime + 0.2);
    });

    // 极轻的撞击瞬态，让“球碰到板”有实体感。
    const ping = ctx.createBufferSource();
    ping.buffer = this.noise;
    const bp = ctx.createBiquadFilter();
    bp.type = 'bandpass';
    bp.frequency.value = 3400 + Math.random() * 900;
    bp.Q.value = 5;
    const pgain = ctx.createGain();
    pgain.gain.setValueAtTime(0.02, t);
    pgain.gain.exponentialRampToValueAtTime(0.0001, t + 0.1);
    ping.connect(bp);
    bp.connect(pgain);
    pgain.connect(lp);
    ping.start(t);
    ping.stop(t + 0.12);
    this._track(ping, t + 0.2);

    lp.connect(out);
    if (panner) {
      out.connect(panner);
      panner.connect(this.master);
    } else {
      out.connect(this.master);
    }

    return { when: t, end: t + ringTime };
  }

  _scheduleDrum(when, pan = 0, velocity = 0.2) {
    const ctx = this.ctx;
    const t = Math.max(when, ctx.currentTime + 0.004);
    const panner = this._panner(pan);
    const out = ctx.createGain();
    out.gain.value = 0.28 + Math.min(0.16, velocity * 0.3);
    if (panner) {
      out.connect(panner);
      panner.connect(this.master);
    } else {
      out.connect(this.master);
    }

    const osc = ctx.createOscillator();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(180, t);
    osc.frequency.exponentialRampToValueAtTime(56, t + 0.16);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(0.85, t + 0.006);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.34);
    osc.connect(g);
    g.connect(out);
    osc.start(t);
    osc.stop(t + 0.36);
    this._track(osc, t + 0.4);

    const n = ctx.createBufferSource();
    n.buffer = this.noise;
    const hp = ctx.createBiquadFilter();
    hp.type = 'highpass';
    hp.frequency.value = 1100;
    const ng = ctx.createGain();
    ng.gain.setValueAtTime(0.15, t);
    ng.gain.exponentialRampToValueAtTime(0.0001, t + 0.18);
    n.connect(hp);
    hp.connect(ng);
    ng.connect(out);
    n.start(t);
    n.stop(t + 0.2);
    this._track(n, t + 0.25);

    return { when: t, end: t + 0.4 };
  }

  /**
   * 预约所有未来音符。fromElapsed 之后的 hit 才排。
   * @param {Array<{t:number, padIndex:number}>} hits
   * @param {object} layout
   * @param {number} fromElapsed
   * @param {number} audioBase 起播时的 AudioContext.currentTime
   * @param {number} speed
   */
  scheduleHits(hits, layout, fromElapsed, audioBase, speed = 1) {
    if (!this.isRunning()) return 0;
    const now = this.now();
    let count = 0;

    hits.forEach((hit) => {
      if (hit.t < fromElapsed - 0.02) return;
      const pad = layout.pads?.[hit.padIndex];
      if (!pad) return;

      const when = audioBase + hit.t / speed;
      if (when < now - 0.16) return;

      const ring = Math.min(3.2, 0.9 + (pad.dur || 1) * 0.24) / Math.max(0.65, speed);
      this.scheduleNote({
        midi: pad.midi,
        type: pad.type,
        when: Math.max(when, now + 0.015),
        ring,
        pan: pad.x,
        velocity: 0.16 + Math.min(0.09, (pad.elasticity || 0.6) * 0.1)
      });
      count += 1;
    });

    return count;
  }

  stopAll() {
    for (const node of this.sources) {
      try {
        if (typeof node.stop === 'function') node.stop(0);
      } catch {
        /* already stopped */
      }
      try {
        node.disconnect();
      } catch {
        /* noop */
      }
    }
    this.sources.clear();
  }

  /**
   * 仅当确定不再播放、且页面长时间隐藏时才调用。
   * 不要把它接在暂停按钮上。
   */
  async suspendWhenIdle() {
    if (this.ctx?.state === 'running') {
      try {
        await this.ctx.suspend();
      } catch {
        /* noop */
      }
    }
  }

  async resume() {
    if (this.ctx?.state === 'suspended') {
      try {
        await this.ctx.resume();
      } catch {
        /* noop */
      }
    }
  }
}
