/**
 * LRC 解析、逐字阶梯、歌词套用。
 * 作者 hoverwu · MIT · 提炼自 MusicStair v0.4.0
 *
 * 用法：
 *   import { parseLrc, lyricsToNotes, applyLyrics } from './lyrics.js';
 *   const notes = lyricsToNotes(lrcText, { bpm: 90, duration: 180 });
 *   const assigned = applyLyrics(songNotes, lrcText, { bpm: 90, duration: 180 });
 */

const TAG_TIME = /\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]/g;
const TAG_META = /^\[(ti|ar|al|by|offset|length|re|ve):([^\]]*)\]$/i;

function stripPunctuation(text) {
  return Array.from(String(text || '').replace(/[^\p{L}\p{N}]/gu, ''));
}

/**
 * 解析标准 LRC。
 * 支持：多时间标签、[offset:ms]、1–3 位小数、元数据行。
 * 返回按时间升序的 [{ time, text }]；time 单位秒，已应用 offset。
 */
export function parseLrc(text) {
  const source = String(text || '').replace(/\r\n?/g, '\n');
  let offset = 0;
  const lines = [];

  source.split('\n').forEach((raw) => {
    const line = raw.trim();
    if (!line) return;

    const meta = TAG_META.exec(line);
    if (meta) {
      if (meta[1].toLowerCase() === 'offset') {
        const ms = Number(meta[2]);
        if (Number.isFinite(ms)) offset = ms / 1000;
      }
      return;
    }

    const stamps = [];
    TAG_TIME.lastIndex = 0;
    let match;
    while ((match = TAG_TIME.exec(line))) {
      const minutes = Number(match[1]) || 0;
      const seconds = Number(match[2]) || 0;
      const fraction = match[3] ? Number(`0.${match[3].padEnd(3, '0')}`) : 0;
      stamps.push(minutes * 60 + seconds + fraction);
    }
    if (!stamps.length) return;

    const content = line.replace(TAG_TIME, '').trim();
    stamps.forEach((time) => {
      lines.push({ time: Math.max(0, time + offset), text: content });
    });
  });

  lines.sort((a, b) => a.time - b.time);
  return lines;
}

/** 曲名归一化键：去扩展名、trim、小写。用于把 song.mp3 与 song.lrc 绑定。 */
export function lrcBaseKey(name) {
  return String(name || '')
    .replace(/\.[^.]+$/, '')
    .trim()
    .toLowerCase();
}

const LYRIC_SCALE = [0, 2, 4, 7, 9, 12, 14, 16, 19, 21, 24, 21, 19, 16, 14, 12, 9, 7, 4, 2];

/**
 * 按歌词逐字生成阶梯。
 * 标准 LRC 只有整行时间：行内按字数均分，行与行之间保留真实间隔。
 * 音高用五声音阶轮廓循环，按行偏移；只用于观感，不是转谱。
 */
export function lyricsToNotes(lrcText, options = {}) {
  const lines = parseLrc(lrcText);
  if (!lines.length) return [];

  const bpm = Math.max(40, Math.min(200, Number(options.bpm) || 90));
  const secPerBeat = 60 / bpm;
  const duration = Number(options.duration) || 0;
  const notes = [];

  lines.forEach((line, li) => {
    const chars = Array.from(stripPunctuation(line.text));
    if (!chars.length) return;

    const start = Math.max(0, line.time);
    const nextTime = lines[li + 1]?.time;
    const fallbackEnd = start + Math.max(0.6, chars.length * 0.26);
    const end = nextTime && nextTime > start
      ? Math.min(nextTime, start + 18)
      : Math.max(duration, fallbackEnd);
    const span = Math.max(0.12, end - start);
    const step = span / chars.length;
    const base = 57 + (li % 7) * 2 + (li % 2 ? 5 : 0);

    chars.forEach((char, ci) => {
      const t = start + ci * step;
      const contour = LYRIC_SCALE[ci % LYRIC_SCALE.length];
      const midi = Math.max(45, Math.min(82, base + contour - 6));
      const gap = Math.max(0.08, step);
      notes.push({
        beat: Math.round((t / secPerBeat) * 10000) / 10000,
        dur: Math.round(Math.min(8, Math.max(0.12, gap)) * 10000) / 10000,
        midi,
        time: Math.round(t * 1000) / 1000,
        lyric: char
      });
    });
  });

  notes.sort((a, b) => a.beat - b.beat);
  let prevBeat = -Infinity;
  notes.forEach((note) => {
    if (note.beat <= prevBeat) note.beat = prevBeat + 0.001;
    prevBeat = note.beat;
  });
  return notes;
}

/**
 * 把歌词按行、按时间铺到已有旋律音符上；每个音符最多显示两个字。
 * 会先清空所有 note.lyric，再写入。返回被写入歌词的音符数量。
 */
export function applyLyrics(notes, lrcText, options = {}) {
  if (!Array.isArray(notes) || !notes.length) return 0;
  const lines = parseLrc(lrcText);
  if (!lines.length) return 0;

  const bpm = Number(options.bpm) || 90;
  const secPerBeat = 60 / bpm;
  const total = Number(options.duration) || 0;

  notes.forEach((note) => {
    note.lyric = '';
  });

  const times = notes.map((note) => {
    const t = Number(note.time);
    return Number.isFinite(t) ? t : (Number(note.beat) || 0) * secPerBeat;
  });

  let assigned = 0;
  lines.forEach((line, li) => {
    const chars = stripPunctuation(line.text);
    if (!chars.length) return;

    const start = line.time;
    const end = lines[li + 1] ? lines[li + 1].time : Math.max(total, start + 4);
    const idx = [];
    for (let i = 0; i < times.length; i += 1) {
      if (times[i] >= start - 0.001 && times[i] < end - 0.001) idx.push(i);
    }
    if (!idx.length) return;

    idx.forEach((noteIndex, j) => {
      const from = Math.floor((j * chars.length) / idx.length);
      const to = Math.max(from + 1, Math.floor(((j + 1) * chars.length) / idx.length));
      const chunk = chars.slice(from, to).join('').slice(0, 2);
      if (chunk) {
        notes[noteIndex].lyric = chunk;
        assigned += 1;
      }
    });
  });

  return assigned;
}
