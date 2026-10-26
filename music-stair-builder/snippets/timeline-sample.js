/**
 * 确定性时间轴：时间 -> 小球位置。
 * 作者 hoverwu · MIT · 提炼自 MusicStair v0.4.0
 *
 * 设计要点：
 * - 命中时间只由 pad.beat 决定，用户拖块不会破坏音画同步。
 * - 音频曲目把 introBeats 设为第一块 beat，使 hit.t 等于绝对秒。
 * - 飞行时间只改变视觉速度，不改变 hit.t。
 *
 * 依赖：three（仅用于向量与曲线）。
 */

import * as THREE from 'three';

const PAD_THICKNESS = 0.12;
const BALL_RADIUS = 0.28;
export const HIT_HEIGHT = PAD_THICKNESS / 2 + BALL_RADIUS + 0.01;

const UP = new THREE.Vector3(0, 1, 0);

function clamp(v, a, b) {
  return v < a ? a : v > b ? b : v;
}

export function hitPoint(pad) {
  return { x: pad.x, y: pad.y + HIT_HEIGHT, z: pad.z };
}

export function flightPoint(p0, p1, u, arc = 0.4, side = 0, out = new THREE.Vector3()) {
  out.lerpVectors(p0, p1, u);
  out.y += arc * 4 * u * (1 - u);
  if (side) {
    const dx = p1.x - p0.x;
    const dz = p1.z - p0.z;
    const len = Math.hypot(dx, dz) || 1;
    const s = Math.sin(Math.PI * u) * side;
    out.x += (-dz / len) * s;
    out.z += (dx / len) * s;
  }
  return out;
}

export function buildRailCurve(a, b, rail = {}) {
  const mid = a.clone().add(b).multiplyScalar(0.5);
  const chord = b.clone().sub(a);
  const dist = chord.length();
  const dir = chord.clone().normalize();
  const side = new THREE.Vector3().crossVectors(dir, UP);
  if (side.lengthSq() < 1e-5) side.set(1, 0, 0);
  side.normalize();

  const bend = clamp(Number(rail.curve) || 0, 0, 1.4);
  const pts = [a.clone()];

  if (rail.shape === 'straight') {
    pts.push(mid.clone().add(UP.clone().multiplyScalar(-Math.min(0.25, dist * 0.02))));
  } else if (rail.shape === 'wave') {
    const amp = side.clone().multiplyScalar(dist * 0.16 * (0.3 + bend));
    pts.push(a.clone().lerp(b, 0.34).add(amp).add(UP.clone().multiplyScalar(dist * 0.045)));
    pts.push(a.clone().lerp(b, 0.67).sub(amp).add(UP.clone().multiplyScalar(dist * 0.045)));
  } else if (rail.shape === 'spiral') {
    const amp = dist * (0.1 + bend * 0.14);
    const steps = 6;
    for (let k = 1; k <= steps; k += 1) {
      const ang = (k / steps) * Math.PI * 2 * 0.8;
      const p = mid.clone().addScaledVector(side, Math.cos(ang) * amp);
      p.y += Math.sin(ang) * amp * 0.7 + dist * 0.035;
      pts.push(p);
    }
  } else {
    const amp = dist * (0.1 + bend * 0.24);
    const p = mid.clone().addScaledVector(side, amp);
    p.y += dist * 0.055;
    pts.push(p);
  }

  pts.push(b.clone());
  return new THREE.CatmullRomCurve3(pts, false, 'catmullrom', 0.5);
}

export class RailPath {
  constructor(padA, padB, rail) {
    const hp0 = hitPoint(padA);
    const hp1 = hitPoint(padB);
    this.p0 = new THREE.Vector3(hp0.x, hp0.y, hp0.z);
    this.p1 = new THREE.Vector3(hp1.x, hp1.y, hp1.z);
    this.curve = buildRailCurve(this.p0, this.p1, rail);
    this.ratio = clamp(Number(rail.ratio) || 0.82, 0.35, 1);
    const a = (1 - this.ratio) / 2;
    this.t0 = a;
    this.t1 = 1 - a;
    this.railStart = this.curve.getPointAt(this.t0);
    this.railEnd = this.curve.getPointAt(this.t1);
  }

  getPoint(u, out = new THREE.Vector3()) {
    const a = this.t0;
    const r = this.ratio;
    if (u < a) {
      return flightPoint(this.p0, this.railStart, clamp(u / Math.max(1e-5, a), 0, 1), 0.1, 0, out);
    }
    if (u <= a + r) {
      const t = this.t0 + ((u - a) / r) * (this.t1 - this.t0);
      return this.curve.getPointAt(clamp(t, 0, 1), out);
    }
    return flightPoint(
      this.railEnd,
      this.p1,
      clamp((u - a - r) / Math.max(1e-5, 1 - a - r), 0, 1),
      0.1,
      0,
      out
    );
  }

  getTangent(u, out = new THREE.Vector3()) {
    const step = 0.0035;
    const a = this.getPoint(Math.max(0, u - step));
    const b = this.getPoint(Math.min(1, u + step));
    return out.subVectors(b, a).normalize();
  }
}

export class Performance {
  /**
   * @param {object} layout { pads, segments }
   * @param {object} song   { bpm }
   * @param {object} options
   *   introBeats: 音频/LRC 曲目传第一块 beat；普通曲目用 1.2
   *   tailBeats:  结束后的下落拍数，默认 2
   *   duration:   原曲完整时长（音频曲目）
   */
  constructor(layout, song, options = {}) {
    this.layout = layout;
    this.song = song;
    this.spb = 60 / (song?.bpm || 90);
    this.introBeats = options.introBeats ?? 1.25;
    this.tailBeats = options.tailBeats ?? 2;
    this.pads = layout?.pads || [];
    this.segments = layout?.segments || [];
    this.hits = [];
    this.paths = [];
    this.directs = [];
    this.duration = 0;

    this._pos = new THREE.Vector3();
    this._tan = new THREE.Vector3();
    this._a = new THREE.Vector3();
    this._b = new THREE.Vector3();

    if (!this.pads.length) {
      this.start = new THREE.Vector3();
      this.end = new THREE.Vector3();
      return;
    }

    const firstBeat = this.pads[0].beat;
    this.pads.forEach((pad, i) => {
      this.hits.push({
        t: (pad.beat - firstBeat + this.introBeats) * this.spb,
        padIndex: i,
        midi: pad.midi,
        type: pad.type,
        lyric: pad.lyric
      });
    });

    const hp0 = hitPoint(this.pads[0]);
    this.start = new THREE.Vector3(hp0.x + 1.6, hp0.y + 4.6, hp0.z + 2.4);
    this.firstHit = new THREE.Vector3(hp0.x, hp0.y, hp0.z);

    for (let i = 0; i < this.pads.length - 1; i += 1) {
      const a = this.pads[i];
      const b = this.pads[i + 1];
      const hpa = hitPoint(a);
      const hpb = hitPoint(b);
      const p0 = new THREE.Vector3(hpa.x, hpa.y, hpa.z);
      const p1 = new THREE.Vector3(hpb.x, hpb.y, hpb.z);
      const seg = this.segments[i];
      if (seg?.rail?.enabled) {
        this.paths.push(new RailPath(a, b, seg.rail));
        this.directs.push(null);
      } else {
        const dist = p0.distanceTo(p1);
        const arc = Math.min(
          2.4,
          0.22 + dist * 0.07 + (a.elasticity || 0.6) * 0.34 + Math.abs(a.rx || 0) * 0.25
        );
        const side = (i % 2 ? 1 : -1) * Math.min(0.55, dist * 0.045);
        this.paths.push(null);
        this.directs.push({ p0, p1, arc, side });
      }
    }

    const last = this.pads[this.pads.length - 1];
    const lastHit = hitPoint(last);
    this.lastHit = new THREE.Vector3(lastHit.x, lastHit.y, lastHit.z);
    const nextAngle = Math.atan2(last.z, last.x) + 0.7;
    this.end = new THREE.Vector3(
      Math.cos(nextAngle) * 4.5,
      lastHit.y - 3.2,
      Math.sin(nextAngle) * 4.5
    );
    this.duration = Math.max(
      this.hits[this.hits.length - 1].t + this.tailBeats * this.spb,
      Number(options.duration) || 0
    );
  }

  get hasNotes() {
    return this.pads.length > 0;
  }

  segmentIndexAt(t) {
    let lo = 0;
    let hi = this.hits.length - 1;
    while (lo < hi) {
      const mid = Math.ceil((lo + hi) / 2);
      if (this.hits[mid].t <= t) lo = mid;
      else hi = mid - 1;
    }
    return Math.min(lo, this.hits.length - 2);
  }

  hitIndexAt(t) {
    let count = 0;
    for (let i = 0; i < this.hits.length; i += 1) {
      if (this.hits[i].t <= t + 1e-6) count = i + 1;
      else break;
    }
    return count - 1;
  }

  sample(t) {
    if (!this.pads.length) {
      return {
        pos: new THREE.Vector3(),
        tangent: new THREE.Vector3(0, 0, 1),
        u: 0,
        segmentIndex: -1,
        phase: 'empty'
      };
    }
    const time = Math.max(0, Math.min(t, this.duration));
    const pos = this._pos;
    const tan = this._tan;

    if (time < this.hits[0].t) {
      const u = this.hits[0].t > 1e-5 ? time / this.hits[0].t : 1;
      const k = u * u;
      pos.lerpVectors(this.start, this.firstHit, k);
      pos.y += Math.sin(Math.PI * u) * 0.12;
      const u2 = Math.min(1, u + 0.004);
      const k2 = u2 * u2;
      const nxt = this._a.lerpVectors(this.start, this.firstHit, k2);
      nxt.y += Math.sin(Math.PI * u2) * 0.12;
      tan.subVectors(nxt, pos).normalize();
      return { pos: pos.clone(), tangent: tan.clone(), u, segmentIndex: -1, phase: 'intro' };
    }

    if (time >= this.hits[this.hits.length - 1].t) {
      const u = Math.min(
        1,
        (time - this.hits[this.hits.length - 1].t) / Math.max(1e-5, this.tailBeats * this.spb)
      );
      const k = Math.pow(u, 1.4);
      pos.lerpVectors(this.lastHit, this.end, k);
      pos.y += Math.sin(Math.PI * u) * 0.15;
      const k2 = Math.pow(Math.min(1, u + 0.004), 1.4);
      const nxt = this._a.lerpVectors(this.lastHit, this.end, k2);
      nxt.y += Math.sin(Math.PI * Math.min(1, u + 0.004)) * 0.15;
      tan.subVectors(nxt, pos).normalize();
      return {
        pos: pos.clone(),
        tangent: tan.clone(),
        u,
        segmentIndex: this.pads.length - 1,
        phase: 'tail'
      };
    }

    const i = this.segmentIndexAt(time);
    const t0 = this.hits[i].t;
    const t1 = this.hits[i + 1].t;
    const span = Math.max(1e-5, t1 - t0);
    const flight = Number(this.segments[i]?.flightTime) || 0;
    let u;
    if (flight > 0.04 && flight < span) {
      const depart = t1 - flight;
      u = time <= depart ? 0 : Math.max(0, Math.min(1, (time - depart) / flight));
    } else {
      u = Math.max(0, Math.min(1, (time - t0) / span));
    }

    const rail = this.paths[i];
    if (rail) {
      rail.getPoint(u, pos);
      rail.getTangent(u, tan);
    } else {
      const d = this.directs[i];
      flightPoint(d.p0, d.p1, u, d.arc, d.side, pos);
      const ua = Math.max(0, u - 0.004);
      const ub = Math.min(1, u + 0.004);
      flightPoint(d.p0, d.p1, ua, d.arc, d.side, this._a);
      flightPoint(d.p0, d.p1, ub, d.arc, d.side, this._b);
      tan.subVectors(this._b, this._a).normalize();
    }
    return { pos: pos.clone(), tangent: tan.clone(), u, segmentIndex: i, phase: rail ? 'rail' : 'flight' };
  }

  hitAt(index) {
    return this.hits[index] || null;
  }
}
