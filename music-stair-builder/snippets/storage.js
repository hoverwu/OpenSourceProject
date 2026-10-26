/**
 * 存储：元数据走 localStorage，音频 Blob 走 IndexedDB。
 * 作者 hoverwu · MIT · 提炼自 MusicStair v0.4.0
 *
 * 原则：
 * - 永远不要把音频转 base64 塞进 localStorage。
 * - 布局写盘要防抖；结构编辑与提交要立即写。
 * - 配额错误翻译成用户能理解的话。
 */

/* ---------------- localStorage ---------------- */

export const SETTINGS_KEY = 'musicstair:settings:v1';
export const SONGS_KEY = 'musicstair:songs:v1';
export const LYRICS_KEY = 'musicstair:lyrics:v1';

export function layoutKey(id) {
  return `musicstair:layout:${id}:v1`;
}

export function variantLayoutKey(id, variant) {
  return `musicstair:layout:${id}:${variant}:v1`;
}

export function keyForVariant(song, variant) {
  return variant && variant !== 'song' ? variantLayoutKey(song.id, variant) : layoutKey(song.id);
}

export function readJson(key, fallback = null) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

export function writeJson(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch (err) {
    if (err?.name === 'QuotaExceededError') {
      console.warn('localStorage 配额不足，元数据未保存', err);
    }
    return false;
  }
}

export function readLayout(song, variant = 'song') {
  const saved = readJson(keyForVariant(song, variant), null);
  const layout = saved?.layout;
  if (!layout || !Array.isArray(layout.pads) || !layout.pads.length) return null;
  if (!Array.isArray(layout.segments)) layout.segments = [];
  layout.bpm = song.bpm;
  return layout;
}

export function writeLayout(song, variant, layout) {
  return writeJson(keyForVariant(song, variant), {
    version: 1,
    savedAt: Date.now(),
    layout
  });
}

export function removeLayout(song, variant) {
  try {
    localStorage.removeItem(keyForVariant(song, variant));
  } catch {
    /* noop */
  }
}

/** 布局写盘防抖：拖动滑杆时每 450ms 最多写一次。 */
export function createLayoutSaver(getSong, getVariant, getLayout, delay = 450) {
  let timer = 0;
  const save = () => {
    const song = getSong();
    const layout = getLayout();
    if (!song || !layout) return;
    layout.bpm = song.bpm;
    writeLayout(song, getVariant(), layout);
  };
  const soon = () => {
    clearTimeout(timer);
    timer = setTimeout(save, delay);
  };
  return { save, soon, cancel: () => clearTimeout(timer) };
}

/* ---------------- IndexedDB ---------------- */

const DB_NAME = 'musicstair:media:v1';
const DB_VERSION = 2;
const PENDING = 'pending';
const LOCAL = 'local';
const AUDIO = 'audio';

let dbPromise = null;

function openDb() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('当前浏览器不支持本地媒体存储'));
      return;
    }
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(PENDING)) db.createObjectStore(PENDING, { keyPath: 'id' });
      if (!db.objectStoreNames.contains(LOCAL)) db.createObjectStore(LOCAL, { keyPath: 'id' });
      if (!db.objectStoreNames.contains(AUDIO)) db.createObjectStore(AUDIO, { keyPath: 'id' });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error || new Error('无法打开本地媒体库'));
    req.onblocked = () =>
      reject(new Error('本地媒体库被其他页面占用，请关闭重复的标签页'));
  });
  return dbPromise;
}

async function request(store, mode, run) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    let tx;
    try {
      tx = db.transaction(store, mode);
    } catch (err) {
      reject(err);
      return;
    }
    const req = run(tx.objectStore(store));
    tx.oncomplete = () => resolve(req?.result);
    tx.onerror = () => reject(tx.error || new Error('本地媒体库操作失败'));
    tx.onabort = () => reject(tx.error || new Error('本地媒体库操作被中止'));
  });
}

function quotaError(err, message) {
  if (err?.name === 'QuotaExceededError' || /quota/i.test(err?.message || '')) {
    return new Error(message);
  }
  return err;
}

/* pending：待转换项 */

export async function listPendingAudio() {
  const list = (await request(PENDING, 'readonly', (s) => s.getAll())) || [];
  return list.sort((a, b) => (b.addedAt || 0) - (a.addedAt || 0));
}

export async function getPendingAudio(id) {
  return request(PENDING, 'readonly', (s) => s.get(id));
}

export async function putPendingAudio(record) {
  try {
    await request(PENDING, 'readwrite', (s) => s.put(record));
    return record;
  } catch (err) {
    throw quotaError(err, '浏览器本地存储空间不足，请删除一些待转换音频后重试');
  }
}

export async function removePendingAudio(id) {
  return request(PENDING, 'readwrite', (s) => s.delete(id));
}

/* local：转换结果 */

export async function listLocalMusic() {
  const list = (await request(LOCAL, 'readonly', (s) => s.getAll())) || [];
  return list.sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));
}

export async function getLocalMusic(id) {
  return request(LOCAL, 'readonly', (s) => s.get(id));
}

export async function putLocalMusic(record) {
  try {
    await request(LOCAL, 'readwrite', (s) => s.put(record));
    return record;
  } catch (err) {
    throw quotaError(err, '浏览器本地存储空间不足，无法保存转换结果');
  }
}

export async function removeLocalMusic(id) {
  return request(LOCAL, 'readwrite', (s) => s.delete(id));
}

/* audio：原曲 Blob */

export async function putAudioBlob(id, blob) {
  try {
    await request(AUDIO, 'readwrite', (s) => s.put({ id, blob, savedAt: Date.now() }));
    return blob;
  } catch (err) {
    throw quotaError(err, '浏览器本地存储空间不足，无法保留原曲音频');
  }
}

export async function getAudioBlob(id) {
  if (!id) return null;
  const record = await request(AUDIO, 'readonly', (s) => s.get(id));
  return record?.blob || null;
}

export async function removeAudioBlob(id) {
  if (!id) return;
  return request(AUDIO, 'readwrite', (s) => s.delete(id));
}
