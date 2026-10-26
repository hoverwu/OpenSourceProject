# 架构与数据流

作者 hoverwu · 版本 0.1.0 · 提炼自 MusicStair v0.4.0

这份文档回答三个问题：模块怎么分、状态放哪里、一份音频如何变成可播放的阶梯。所有结论来自已经跑通的 MusicStair 实现，可以直接照搬结构，也可以映射到 React/Vue/Svelte。

## 1. 模块划分

参考实现的目录（Vite + 原生 ES modules + Three.js）：

```text
src/
  main.js                  应用状态机、UI 绑定、播放调度、编辑器、导入流水线
  core/
    layout.js              notes -> pads/segments 的纯函数，配色与音色元数据
    timeline.js            Performance：t -> 小球位置/切线/命中段
    paths.js               抛射弧、导轨曲线、RailPath
    lrc.js                 LRC 解析、逐字阶梯、歌词套用
    audioConvert.js        解码、重采样、起音、基频、BPM
    midi.js                MIDI/JSON 导入
    musicStore.js          IndexedDB：pending/local/audio
    search.js              曲库搜索
  audio/
    engine.js              WebAudio 音色、包络、混响、压缩、预调度
  scene/
    world.js               Three.js 场景、实例化、导轨、相机、粒子
  data/songs.js            内置曲目、MIDI 频率工具
```

分工边界要守住：

- `core/` 不碰 DOM，全部是纯函数或纯数据类，方便测试和移植。
- `main.js` 是唯一的状态所有者，`world` 和 `audio` 都是被命令的执行者。
- `world` 不知道 BPM，也不读 localStorage；它只接收 `layout` 和 `song`。
- `audio` 不知道阶梯，只接收 `{midi, type, when, ring, pan, velocity}`。

## 2. 应用状态

最小状态集：

```js
state = {
  song, layout, perf,             // 当前曲目、布局、时间轴
  layoutVariant,                  // 'song' | 'lyric'
  mode,                           // 'play' | 'edit'
  playing, following, loop, speed,
  elapsed, lastHit, selected,
  clockMode,                      // 'backing' | 'audio' | 'perf'
  playStartAudio, playStartPerf,
  undo: [], redo: [],
  mineSongs: [], pendingAudio: [], localMusic: [],
  backingEnabled, backingStatus, backingDuration
}
```

两条独立的时间线：

- `state.elapsed` 是**逻辑播放头**，单位秒。
- `perf.hits[i].t` 是**第 i 块的命中秒数**，由 beat 推出。
- 真实时间来自 `AudioContext.currentTime`（有原曲时来自伴奏 source 的偏移），`performance.now()` 只在完全无音频可用时兜底。

不要用 rAF 累加时间，也不要给每个音设 `setTimeout`。rAF 只负责“读取当前时间并采样画面”。

## 3. 数据模型与不变量

```js
note    = { beat, dur, midi, lyric, time? }
pad     = { id, index, x, y, z, ry, rx, rz, w, d, elasticity, type, color,
            midi, lyric, beat, dur, phrase, phraseIndex }
segment = { id, from, to, flightTime, rail: { enabled, shape, curve, ratio } }
layout  = { version, songId, bpm, pads, segments, seed? }
song    = { id, title, artist, tags, bpm, phraseSize, desc, notes,
            variants: { song, lyric }, variant, source,
            absoluteTime, audioId, duration, totalBeats }
```

必须始终成立：

1. `segments.length === pads.length - 1`（空布局除外）。
2. `segments[i].from === pads[i].id`，`segments[i].to === pads[i + 1].id`。
3. `pad.index === 数组下标`。
4. `pads` 的 `beat` 严格递增；纯 LRC 曲目也允许 0.001 拍的最小间隔。
5. 音频曲目 `absoluteTime === true`，其 `beat` 是相对秒换算来的拍。

每次结构编辑（插入、删除、重置）后调用一个 `refreshLayoutRefs()` 统一修复 1–3，再重建时间轴。不要在每个编辑分支里手写修复逻辑。

## 4. 存储

### localStorage：元数据与布局

```text
musicstair:songs:v1                    我的曲库（不含音频二进制）
musicstair:lyrics:v1                   曲名 -> LRC 文本
musicstair:settings:v1                 音量、静音、上次曲目
musicstair:layout:<songId>:v1          主变体布局
musicstair:layout:<songId>:lyric:v1    歌词变体布局
```

布局存储必须带一层包装，方便以后迁移：

```js
{
  version: 1,
  savedAt: 1730000000000,
  layout: { version: 1, songId, bpm, pads, segments }
}
```

读取时验证 `layout.pads` 是数组且非空；空数组视为没有存档，重新生成。读取后强制 `layout.bpm = song.bpm`，避免旧布局带动旧速度。

写入策略：

- 拖动参数、切换颜色这类高频修改：`setTimeout(saveLayoutNow, 450)` 防抖。
- 点「确定」、撤销/重做、插入/删除、切换变体、另存：立即写。
- **不要**在拖动中的每一帧写 localStorage；序列化 320 块布局会很卡。

### IndexedDB：媒体

```text
数据库 musicstair:media:v1，版本 2
  pending  keyPath id   待转换项：音频 Blob + LRC 文本 + 模式
  local    keyPath id   转换结果：notes/songNotes/lyricNotes + 元信息
  audio    keyPath id   原曲 Blob，供伴奏与另存复制
```

音频 Blob 绝对不要转 base64 放进 localStorage：5MB 的 MP3 变成约 6.7MB 字符串，很容易触发 5–10MB 配额并把整份曲库写坏。

配额错误要单独翻译：

```js
if (err?.name === 'QuotaExceededError' || /quota/i.test(err.message)) {
  throw new Error('浏览器本地存储空间不足，请删除一些音频后重试');
}
```

## 5. 一份音频的完整数据流

```text
用户选择文件
  -> 按扩展名识别音频 / LRC
  -> 曲名 = 去扩展名 + trim + lowercase，用于合并
  -> 音频写入 pending（Blob），LRC 写入 pending.lrcText
  -> 用户点“转换”
       -> 音频：analyzeAudio(blob)
            decodeAudioData -> 单声道 22050Hz 全曲渲染
            -> 起音列表 -> 最多 320 个块 -> 基频 -> BPM
            -> songNotes（绝对时间）
       -> 歌词：lyricsToNotes(lrcText, {bpm, duration})
            -> lyricNotes（逐字）
       -> 有音频且有歌词：applyLyrics(songNotes, lrcText)
       -> 原曲 Blob 复制到 audio store
       -> 转换结果写入 local
  -> 用户点“生成阶梯”
       -> variants = { song: songNotes, lyric: lyricNotes }
       -> 主变体按用户选择的 mode
       -> 生成 song 记录，加入“我的曲库”
       -> loadSong(song, {variant: primary})
  -> 主界面
       -> readLayout(song, variant) 或 createLayout
       -> Performance(layout, song, {introBeats})
       -> world.setLayout(layout, song)
       -> prepareBacking(song)  // 取回 Blob 解码成 AudioBuffer
```

LRC 也可能在转换之后才导入：`addLrcFile` 会回填到同名的 `local` 记录和已生成的 `song.variants.lyric`，并在主界面刷新变体按钮。因此“歌词 → 音频”和“音频 → 歌词”两条顺序都要支持。

## 6. 双变体

```js
function songVariants(song) {
  return ['song', 'lyric'].filter((k) => song?.variants?.[k]?.length);
}

function notesForVariant(song, variant) {
  const list = song?.variants?.[variant];
  return list?.length ? list : song.notes || [];
}

function layoutKeyFor(song, variant) {
  return variant === 'song'
    ? `musicstair:layout:${song.id}:v1`
    : `musicstair:layout:${song.id}:${variant}:v1`;
}
```

切换变体的事务顺序：

1. `saveLayoutNow()` 保存当前变体。
2. 暂停播放，关闭编辑器并丢弃未确认的修改。
3. 改 `layoutVariant`。
4. 读取目标布局；没有就 `createLayout({...song, notes: notesForVariant(...)})`。
5. 重建 `Performance`，`world.setLayout(..., {frame:false})`，重置播放头和选择。
6. 刷新 UI：标题旁音符数、变体按钮、歌词条、进度条。
7. `song.variant = next` 并保存曲库。

变体按钮只在 `songVariants(song).length > 1` 时显示。只有歌曲没有歌词时不要显示一个点不动的按钮。

## 7. 三种时钟

| clockMode | 主时钟 | 阶梯音是否调度 | 用途 |
| --- | --- | --- | --- |
| `backing` | 原曲 `AudioBufferSourceNode` | 否 | 播放导入的歌曲 |
| `audio` | `AudioContext.currentTime` | 是 | 纯阶梯音 |
| `perf` | `performance.now()` | 否 | 浏览器拒绝音频时的静音动画 |

选择顺序：

```js
useBacking = isAudioSong() && backingEnabled && backing.ready
clockMode = useBacking ? 'backing' : audioUnlocked ? 'audio' : 'perf'
```

`currentElapsed()` 必须按模式分支；尤其原曲模式要减去 `audio.latency()`（上限 0.08 秒），否则阶梯会比伴奏晚半拍。没有原曲时用 `state.playStartAudio` 记录 `AudioContext` 起点，再按倍速换算。

暂停只做三件事：停掉所有 source、记录 `state.elapsed`、把伴奏偏移写回 `backing.offset`。**不要 `suspend()` AudioContext**，原因见 [audio-and-lyrics.md](audio-and-lyrics.md) 的第 7 节。

## 8. 编辑器事务

编辑器不是“改一下就写一下”，而是小事务：

```js
editSession = {
  baseline: cloneLayout(state.layout),  // 打开编辑器时的快照
  dirty: false
}
```

- 所有滑杆只改 `state.layout` 与场景，标记 `dirty`。
- 「确定」：`pushUndo(editSession.baseline)` → `saveLayoutNow()` → `dirty=false`。
- 「取消」：`applyLayoutSnapshot(editSession.baseline, {save:false})`。
- 结构编辑（插入/删除）直接 `beginEdit()`，让本次结构变化也走确定/取消。
- 撤销/重做保存完整 layout 快照，最多 40 步；撤销前若有未确认修改，提示先处理。

快照应用函数必须同时做：克隆、重建时间轴、重设场景、恢复选择、刷新编辑器、刷新歌词、刷新标题音符数、刷新变体按钮、刷新进度条、安排一次性能采样，最后防抖保存。漏掉任何一项都会出现“数量没变”“歌词没刷新”的假象。

## 9. 另存为

另存不是简单复制 JSON：

1. 保存当前曲目的最新布局。
2. 新 id、新标题，深拷贝歌曲。
3. 如果 `audioId` 存在，把 Blob 复制到新 id 下，令 `copy.audioId = newId`；复制失败则共用原 id 并提示。
4. 对每个变体：读原布局（没有则生成），写到新 id 的布局键。
5. 加入曲库，原曲目与布局完全不动。

这样“编辑坏了就重新生成、原来的还能重置”才成立。

## 10. 迁移到 React/Vue

映射建议：

- `state` 拆成 stores：`playerStore`、`layoutStore`、`libraryStore`。
- `Performance` 保持为普通类，不要放进响应式系统；320 个 hit 不需要被代理。
- `world` 挂在一个 `ref` 上，组件卸载时显式 `dispose()`。
- 播放头用外部 store + rAF 写入，不要每帧 `setState`；进度条与歌词条通过订阅更新。
- 编辑器用「草稿 + 提交」两份状态，和本文的事务模型一致。

不要做的事：把 Three.js 对象放进 Vue 的 `reactive()`，或把整个 layout 每帧复制给 React state。这两件事都会让 320 块场景掉到个位数帧率。
