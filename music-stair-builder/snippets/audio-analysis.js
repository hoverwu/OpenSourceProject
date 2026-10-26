/**
 * 音频转阶梯谱：整曲解码 -> 起音检测 -> 单声部基频 -> 绝对时间音符。
 * 作者 hoverwu · MIT · 提炼自 MusicStair v0.4.0
 *
 * 只在浏览器运行，依赖 Web Audio 的 OfflineAudioContext。
 * 不追求转谱级准确：和弦、强混响、密集鼓点会误判，必须给人编辑兜底。
 */

export const AUDIO_FORMATS = [
  { ext: 'mp3', label: 'MP3' },
  { ext: 'wav', label: 'WAV' },
  { ext: 'flac', label: 'FLAC' },
  { ext: 'm4a', label: 'M4A' },
  { ext: 'aac', label: 'AAC' },
  { ext: 'ogg', label: 'OGG' },
  { ext: 'opus', label: 'OPUS' }
];

export const MAX_AUDIO_BYTES = 40 * 1024 * 1024;
export const MAX_ANALYZE_SECONDS = 900;
export const MAX_NOTE_BLOCKS = 320;

const TARGET_SR = 22050;

export function audioFormatOf(name) {
  const match = /\.([a-z0-9]+)$/i.exec(String(name || ''));
  if (!match) return null;
  const ext = match[1].toLowerCase();
  return AUDIO_FORMATS.find((f) => f.ext === ext) || null;
}

export function isMidiFileName(name) {
  return /\.(mid|midi|json)$/i.test(String(name || ''));
}

function offlineContext(channels, length) {
  const Offline = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  if (!Offline) throw new Error('当前浏览器不支持离线音频解码');
  return new Offline(channels, Math.max(1, Math.floor(length)), TARGET_SR);
}

/** 解码并把整首歌重采样成 22050Hz 单声道；分析上限 900 秒，但保留完整 duration。 */
export async function decodeToMono(blob, onProgress) {
  const raw = await blob.arrayBuffer();
  let decoded;
  try {
    const decoder = offlineContext(1, 1);
    decoded = await decoder.decodeAudioData(raw.slice(0));
  } catch {
    throw new Error('浏览器无法解码这个音频，可能是格式不受支持、文件损坏或受 DRM 保护');
  }
  if (!decoded || !decoded.duration) throw new Error('音频里没有可读取的声音');

  const seconds = Math.min(decoded.duration, MAX_ANALYZE_SECONDS);
  const frames = Math.floor(seconds * TARGET_SR);
  onProgress?.('rendering');
  const mixer = offlineContext(1, frames);
  const src = mixer.createBufferSource();
  src.buffer = decoded;
  src.connect(mixer.destination);
  src.start(0);
  const rendered = await mixer.startRendering();

  return {
    samples: rendered.getChannelData(0),
    sampleRate: TARGET_SR,
    duration: decoded.duration,
    analyzedSeconds: seconds,
    sourceRate: decoded.sampleRate,
    channels: decoded.numberOfChannels
  };
}

/** RMS + 高频含量混合 novelty 的峰值检测。返回起音秒数数组。 */
export function detectOnsets(samples, sampleRate) {
  const win = 1024;
  const hop = 256;
  if (samples.length < win * 2) return [];
  const frameCount = Math.floor((samples.length - win) / hop) + 1;
  const rms = new Float32Array(frameCount);
  const hfc = new Float32Array(frameCount);

  for (let f = 0; f < frameCount; f += 1) {
    const pos = f * hop;
    let energy = 0;
    let derivative = 0;
    for (let i = 0; i < win; i += 1) {
      const v = samples[pos + i];
      energy += v * v;
      const prev = i === 0 ? (pos > 0 ? samples[pos - 1] : 0) : samples[pos + i - 1];
      const d = v - prev;
      derivative += d * d;
    }
    rms[f] = Math.sqrt(energy / win);
    hfc[f] = Math.sqrt(derivative / win);
  }

  let rmsMax = 0;
  let hfcMax = 0;
  for (let f = 0; f < frameCount; f += 1) {
    if (rms[f] > rmsMax) rmsMax = rms[f];
    if (hfc[f] > hfcMax) hfcMax = hfc[f];
  }
  if (!rmsMax) return [];

  const novelty = new Float32Array(frameCount);
  let noveltyMax = 0;
  for (let f = 1; f < frameCount; f += 1) {
    const dr = Math.max(0, rms[f] - rms[f - 1]) / rmsMax;
    const dh = Math.max(0, hfc[f] - hfc[f - 1]) / hfcMax;
    novelty[f] = dr + dh * 0.6;
    if (novelty[f] > noveltyMax) noveltyMax = novelty[f];
  }

  const radius = Math.max(3, Math.round((0.18 * sampleRate) / hop));
  const minGap = Math.max(3, Math.round((0.12 * sampleRate) / hop));
  const floor = rmsMax * 0.018;
  const onsets = [];
  let lastFrame = -Infinity;

  for (let f = 1; f < frameCount - 1; f += 1) {
    const n = novelty[f];
    if (n <= noveltyMax * 0.035 || rms[f] <= floor) continue;
    if (n < novelty[f - 1] || n < novelty[f + 1]) continue;

    let sum = 0;
    let count = 0;
    const from = Math.max(1, f - radius);
    const to = Math.min(frameCount - 1, f + radius);
    for (let j = from; j <= to; j += 1) {
      sum += novelty[j];
      count += 1;
    }
    const threshold = (sum / Math.max(1, count)) * 1.35 + noveltyMax * 0.02;
    if (n < threshold) continue;
    if (f - lastFrame < minGap) continue;

    onsets.push((f * hop) / sampleRate);
    lastFrame = f;
  }

  if (onsets.length < 4) {
    const fallback = [];
    const step = 0.45;
    for (let t = 0.25; t < samples.length / sampleRate; t += step) {
      const frame = Math.min(frameCount - 1, Math.floor((t * sampleRate) / hop));
      if (rms[frame] > floor) fallback.push(t);
    }
    if (fallback.length >= 3) return fallback;
  }
  return onsets;
}

/** 自相关 + CMND 的单声部基频估计；失败返回 null。 */
export function estimatePitch(samples, sampleRate, startSec, endSec) {
  const start = Math.max(0, Math.floor(startSec * sampleRate));
  const end = Math.min(samples.length, Math.floor(endSec * sampleRate));
  const available = end - start;
  if (available < 512) return null;

  const maxTau = Math.min(Math.floor(sampleRate / 70), available - 256);
  const minTau = Math.max(2, Math.floor(sampleRate / 1000));
  if (maxTau <= minTau + 8) return null;

  const offset = Math.min(Math.floor(0.02 * sampleRate), Math.max(0, Math.floor(available * 0.12)));
  const n = Math.min(2048, available - offset - maxTau);
  if (n < 480) return null;

  const base = start + offset;
  const diff = new Float32Array(maxTau + 1);
  for (let tau = 1; tau <= maxTau; tau += 1) {
    let sum = 0;
    for (let i = 0; i < n; i += 1) {
      const d = samples[base + i] - samples[base + i + tau];
      sum += d * d;
    }
    diff[tau] = sum;
  }

  const cmnd = new Float32Array(maxTau + 1);
  cmnd[0] = 1;
  let running = 0;
  for (let tau = 1; tau <= maxTau; tau += 1) {
    running += diff[tau];
    cmnd[tau] = running ? (diff[tau] * tau) / running : 1;
  }

  let tau = -1;
  for (let t = minTau; t <= maxTau; t += 1) {
    if (cmnd[t] < 0.18) {
      tau = t;
      break;
    }
  }
  if (tau < 0) {
    let best = -1;
    let bestVal = 1;
    for (let t = minTau; t <= maxTau; t += 1) {
      if (cmnd[t] < bestVal) {
        bestVal = cmnd[t];
        best = t;
      }
    }
    if (best < 0 || bestVal > 0.42) return null;
    tau = best;
  }
  while (tau + 1 <= maxTau && cmnd[tau + 1] < cmnd[tau]) tau += 1;

  let refined = tau;
  if (tau > minTau && tau < maxTau) {
    const a = cmnd[tau - 1];
    const b = cmnd[tau];
    const c = cmnd[tau + 1];
    const denom = a - 2 * b + c;
    if (Math.abs(denom) > 1e-9) {
      const shift = (0.5 * (a - c)) / denom;
      refined = tau + Math.max(-0.5, Math.min(0.5, shift));
    }
  }

  const freq = sampleRate / Math.max(1, refined);
  if (freq < 65 || freq > 1100) return null;
  const midi = 69 + 12 * Math.log2(freq / 440);
  if (midi < 34 || midi > 100) return null;
  return midi;
}

/**
 * 空值沿用前值、八度纠正、逐起音取整。
 * 不要做中值滤波：会把孤立高音/低音抹平。
 */
export function smoothPitches(raw) {
  const filled = raw.slice();
  let last = null;

  for (let i = 0; i < filled.length; i += 1) {
    if (filled[i] == null) {
      filled[i] = last;
    } else {
      if (last != null) {
        const diff = filled[i] - last;
        if (Math.abs(diff) > 10) {
          let best = filled[i];
          for (let k = -2; k <= 2; k += 1) {
            const cand = filled[i] + k * 12;
            if (Math.abs(cand - last) < Math.abs(best - last)) best = cand;
          }
          filled[i] = best;
        }
      }
      last = filled[i];
    }
  }

  const first = filled.find((v) => v != null);
  const fallback = first == null ? 60 : first;
  for (let i = 0; i < filled.length; i += 1) {
    if (filled[i] == null) filled[i] = fallback;
  }

  return filled.map((v) => Math.max(30, Math.min(100, Math.round(v))));
}

/** 起音间隔中位数，按倍频折叠到 68–168，再夹到 50–180。 */
export function estimateBpm(onsets) {
  if (onsets.length < 3) return 90;
  const iois = [];
  for (let i = 1; i < onsets.length; i += 1) {
    const d = onsets[i] - onsets[i - 1];
    if (d >= 0.18 && d <= 1.8) iois.push(d);
  }
  if (!iois.length) return 90;

  iois.sort((a, b) => a - b);
  let bpm = 60 / iois[Math.floor(iois.length / 2)];
  while (bpm < 68) bpm *= 2;
  while (bpm > 168) bpm /= 2;
  return Math.round(Math.max(50, Math.min(180, bpm)));
}

/** 超过上限时均匀抽样，保留整首歌的分布，而不是截断前 N 个。 */
export function pickOnsets(onsets, max) {
  if (onsets.length <= max) {
    return { indices: onsets.map((_, i) => i), times: onsets };
  }
  const indices = [];
  const step = (onsets.length - 1) / (max - 1);
  for (let i = 0; i < max; i += 1) {
    const idx = Math.round(i * step);
    if (indices[indices.length - 1] !== idx) indices.push(idx);
  }
  return { indices, times: indices.map((i) => onsets[i]) };
}

export async function probeAudioDuration(blob) {
  if (!blob) throw new Error('没有可读取的音频');
  const raw = await blob.arrayBuffer();
  let decoded;
  try {
    const decoder = offlineContext(1, 1);
    decoded = await decoder.decodeAudioData(raw.slice(0));
  } catch {
    throw new Error('浏览器无法解码这个音频，可能是格式不受支持、文件损坏或受 DRM 保护');
  }
  if (!decoded || !decoded.duration) throw new Error('音频里没有可读取的声音');
  return {
    duration: decoded.duration,
    sourceRate: decoded.sampleRate,
    channels: decoded.numberOfChannels
  };
}

/**
 * 完整分析。
 * 返回 notes 的 beat 是绝对时间换算来的拍，配合 introBeats=firstBeat 使用。
 */
export async function analyzeAudio(blob, onProgress) {
  onProgress?.('decoding');
  const decoded = await decodeToMono(blob, onProgress);

  onProgress?.('onsets');
  const onsets = detectOnsets(decoded.samples, decoded.sampleRate);
  if (!onsets.length) throw new Error('没有检测到有效的声音，无法提取旋律');

  const picked = pickOnsets(onsets, MAX_NOTE_BLOCKS);

  onProgress?.('pitches');
  const rawPitches = picked.times.map((t, i) => {
    const nextOnset = onsets[picked.indices[i] + 1];
    const end = Math.min(
      decoded.analyzedSeconds,
      nextOnset ? Math.min(nextOnset, t + 0.85) : t + 0.6
    );
    return estimatePitch(decoded.samples, decoded.sampleRate, t + 0.025, end);
  });
  const pitches = smoothPitches(rawPitches);
  const bpm = estimateBpm(onsets);
  const secPerBeat = 60 / bpm;

  onProgress?.('notes');
  const notes = [];
  let prevBeat = -Infinity;
  picked.times.forEach((t, i) => {
    let beat = Math.round((t / secPerBeat) * 10000) / 10000;
    if (!Number.isFinite(prevBeat)) prevBeat = -Infinity;
    if (beat <= prevBeat) beat = prevBeat + 0.001;
    prevBeat = beat;

    const next = picked.times[i + 1];
    const dur = next ? Math.max(0.08, next - t) / secPerBeat : 1;
    notes.push({
      beat,
      dur: Math.round(Math.min(16, dur) * 10000) / 10000,
      midi: pitches[i],
      time: Math.round(t * 1000) / 1000,
      lyric: ''
    });
  });

  return {
    bpm,
    notes,
    duration: decoded.duration,
    analyzedSeconds: decoded.analyzedSeconds,
    sourceRate: decoded.sourceRate,
    channels: decoded.channels,
    onsetCount: onsets.length,
    noteBlockCount: notes.length,
    densityReduced: onsets.length > MAX_NOTE_BLOCKS,
    truncatedAudio: decoded.duration > MAX_ANALYZE_SECONDS
  };
}
