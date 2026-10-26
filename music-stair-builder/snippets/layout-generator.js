/**
 * 自动布局：把「音高 / 时间 / 停顿」映射成盘旋下降的阶梯与段。
 * 作者 hoverwu · MIT · 提炼自 MusicStair v0.4.0
 *
 * 纯函数，不依赖 DOM 或 Three.js。
 * 不变量：segments.length === pads.length - 1（空布局除外）。
 */

export const BALL_RADIUS = 0.28;
export const PAD_THICKNESS = 0.12;
export const PAD_TOP = PAD_THICKNESS / 2;
export const HIT_HEIGHT = PAD_TOP + BALL_RADIUS + 0.01;

export const PALETTE = [
  { hex: '#9fe7d5', name: '薄荷' },
  { hex: '#f7b6c9', name: '樱粉' },
  { hex: '#f7e2a1', name: '鹅黄' },
  { hex: '#c9baf5', name: '淡紫' },
  { hex: '#a9d9f4', name: '天蓝' },
  { hex: '#eef6ff', name: '月白' },
  { hex: '#2b3f6e', name: '靛蓝' }
];

export const SEGMENT_SHAPES = ['arc', 'wave', 'spiral', 'straight'];

export const TYPE_INFO = {
  pad: { label: '木琴', short: '琴', desc: '温暖的木质泛音，默认音色' },
  glass: { label: '玻璃', short: '璃', desc: '清澈的高频泛音，像玻璃杯' },
  bell: { label: '铃', short: '铃', desc: '明亮的铃铛，余音更长' },
  synth: { label: '合成', short: '合', desc: '柔和的三角波铺底' },
  drum: { label: '鼓', short: '鼓', desc: '无固定音高的打击声' }
};

let seedCounter = 1;

/** 确定性伪随机：同 i/salt 永远同值，避免刷新后布局变化。 */
function seeded(i, salt = 0) {
  const x = Math.sin(i * 127.1 + salt * 311.7 + 17.13) * 43758.5453;
  return x - Math.floor(x);
}

function clamp(v, a, b) {
  return v < a ? a : v > b ? b : v;
}

export function hitPoint(pad) {
  return { x: pad.x, y: pad.y + HIT_HEIGHT, z: pad.z };
}

/**
 * @param {object} song { id, bpm, phraseSize, notes }
 * @returns {{version:number, songId:string, bpm:number, seed:number, pads:Array, segments:Array}}
 */
export function createLayout(song) {
  const notes = song.notes || [];
  const pads = [];
  const segments = [];

  if (!notes.length) {
    return { version: 1, songId: song.id, pads, segments };
  }

  const startAngle = -1.15;
  const phraseSize = song.phraseSize || 7;
  const count = notes.length;

  // 长曲收紧转角、封顶高度，避免螺旋无限扩大。
  const long = count > 48;
  const radiusBase = long
    ? Math.min(11.5, 8 + count * 0.012)
    : 6.8 + Math.max(0, count - 24) * 0.04;
  const angleStep = long ? Math.max(0.18, Math.min(0.42, (0.42 * 48) / count)) : 0.42;
  const spanY = long ? Math.min(18, 7 + count * 0.06) : 7 + count * 0.1;

  const yAt = (index, midi, jitter) =>
    7.4 - spanY * (index / Math.max(1, count - 1)) + (midi - 64) * 0.12 + jitter;

  notes.forEach((note, i) => {
    const pitch = note.midi - 64;
    const angle = startAngle + i * angleStep + Math.sin(i * 0.37) * 0.06;
    const radius =
      radiusBase + Math.sin(i * 0.83) * 0.22 + clamp(pitch * 0.03, -0.4, 0.7);
    const x = Math.cos(angle) * radius;
    const z = Math.sin(angle) * radius;
    const y = yAt(i, note.midi, Math.sin(i * 1.7) * 0.05);

    const next = notes[i + 1];
    const nextAngle = startAngle + (i + 1) * angleStep + Math.sin((i + 1) * 0.37) * 0.06;
    const nextPitch = next ? next.midi - 64 : pitch;
    const nextRadius =
      radiusBase + Math.sin((i + 1) * 0.83) * 0.22 + clamp(nextPitch * 0.03, -0.4, 0.7);
    const nx = Math.cos(nextAngle) * nextRadius;
    const nz = Math.sin(nextAngle) * nextRadius;
    const ny = yAt(i + 1, next ? next.midi : note.midi, Math.sin((i + 1) * 1.7) * 0.05);
    const dxz = Math.hypot(nx - x, nz - z);
    const slope = Math.atan2(ny - y, Math.max(0.001, dxz));

    const isPhraseStart = i % phraseSize === 0;
    const isPhraseEnd = i % phraseSize === phraseSize - 1;
    const type = isPhraseStart ? 'bell' : isPhraseEnd ? 'glass' : 'pad';
    const dark = note.midi < 50 || (i * 7 + note.midi) % 17 === 0;

    pads.push({
      id: `p${i}`,
      index: i,
      x,
      y,
      z,
      ry: -angle - Math.PI / 2 + (seeded(i, 3) * 2 - 1) * 0.14,
      rx: -0.04 + clamp(slope * 0.28, -0.16, 0.16) + (seeded(i, 5) * 2 - 1) * 0.03,
      rz: (seeded(i, 7) * 2 - 1) * 0.05,
      w: 1.7 + Math.min(0.75, (note.dur || 1) * 0.3) + seeded(i, 11) * 0.15,
      d: 0.95 + seeded(i, 13) * 0.18,
      elasticity: 0.52 + seeded(i, 17) * 0.3,
      type,
      color: dark
        ? '#2b3f6e'
        : type === 'bell'
          ? '#f7e2a1'
          : type === 'glass'
            ? '#a9d9f4'
            : PALETTE[i % 6].hex,
      midi: note.midi,
      lyric: note.lyric || '',
      beat: note.beat,
      dur: note.dur || 1,
      phrase: Math.floor(i / phraseSize),
      phraseIndex: i % phraseSize
    });
  });

  for (let i = 0; i < pads.length - 1; i += 1) {
    const a = pads[i];
    const b = pads[i + 1];
    const delta = b.beat - a.beat;
    const gap = b.beat - (a.beat + a.dur);
    const autoRail = gap > 0.08 || delta >= 1.9;
    segments.push({
      id: `s${i}`,
      from: a.id,
      to: b.id,
      flightTime: 0,
      rail: {
        enabled: autoRail,
        shape: SEGMENT_SHAPES[i % SEGMENT_SHAPES.length],
        curve: 0.5 + seeded(i, 19) * 0.5,
        ratio: 0.82
      }
    });
  }

  return {
    version: 1,
    songId: song.id,
    bpm: song.bpm || 90,
    seed: seedCounter++,
    pads,
    segments
  };
}

export function cloneLayout(layout) {
  return JSON.parse(JSON.stringify(layout));
}

/** 段信息：距离、可用秒数、飞行时间、速度。UI 上显示“本段可设 0–X 秒”。 */
export function segmentStats(layout, segmentIndex) {
  const a = layout.pads[segmentIndex];
  const b = layout.pads[segmentIndex + 1];
  const seg = layout.segments[segmentIndex];
  if (!a || !b || !seg) return null;

  const p0 = hitPoint(a);
  const p1 = hitPoint(b);
  const distance = Math.hypot(p1.x - p0.x, p1.y - p0.y, p1.z - p0.z);
  const span = ((b.beat - a.beat) * 60) / (layout.bpm || 90);
  const configured = Number(seg.flightTime) || 0;
  const seconds = configured > 0.04 ? Math.min(configured, span) : span;

  return {
    distance,
    seconds,
    speed: seconds > 0 ? distance / seconds : 0,
    gap: b.beat - (a.beat + a.dur),
    delta: b.beat - a.beat,
    flightTime: configured,
    span
  };
}

export function setLayoutBpm(layout, bpm) {
  layout.bpm = bpm;
  return layout;
}

export function createEmptyLayout(song) {
  return { version: 1, songId: song.id, bpm: song.bpm || 90, pads: [], segments: [] };
}
