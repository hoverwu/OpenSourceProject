---
name: music-stair-builder
description: >
  构建、改造或排查「音乐阶梯」H5：Three.js 三维阶梯 + WebAudio 音色与原曲伴奏，
  支持音频起音分析、LRC 逐字阶梯、歌曲/歌词双变体、可视化编辑器与本地媒体库。
  触发场景：从零做音乐阶梯/小球弹板音乐可视化；音频自动生成阶梯；LRC 导入与逐字阶梯；
  原曲伴奏与阶梯同步；阶梯增删/插入/飞行时间/另存；320 块长曲性能；切到阶梯音无声。
argument-hint: <项目路径或目标目录>
---

# MusicStair 音乐阶梯构建 Skill

作者 hoverwu · 版本 0.1.0 · 提炼自 MusicStair v0.4.0（2026-10-26 验收）

## 这个 Skill 适合什么

- **从零复刻**：做一个「小球沿阶梯下落，每撞一块发一个音」的 Three.js + WebAudio 网页玩具。
- **改造现有项目**：增加音频导入、LRC 歌词、歌曲/歌词两套布局、编辑器、曲库与另存。
- **排错**：音画不同步、导入只播十几秒、长曲卡顿、切到阶梯音没声音、歌词对不上、编辑后参数丢失。

不适合：纯音频处理库、纯 2D 音乐游戏判定、需要服务端转码/版权曲库的项目。

## 先定 4 个决策

| 决策 | 推荐默认 | 说明 |
| --- | --- | --- |
| 曲子来源 | 内置数据 + 本地音频/MIDI | 在线曲库有跨域与版权问题，默认不做 |
| 音高策略 | 单声部起音 + 自相关基频 | 混音/和弦会不准，必须提供人工编辑 |
| 视觉规模 | 普通曲 < 120 块；长曲最多 320 块 | 超过 120 块切实例化板 + 合并导轨 |
| 存储 | 元数据 localStorage，音频 Blob 存 IndexedDB | 不要把音频转 base64 塞 localStorage |

## 数据契约（先固定，后面全部围绕它）

```js
// 一个音：beat 是拍位置，midi 是音高，lyric 是显示字
note = { beat: 0.5, dur: 1.2, midi: 64, lyric: '月', time: 0.25 }

// 一块阶梯：视觉参数 + 对应音符的快照
pad = {
  id: 'p12', index: 12,
  x, y, z, ry, rx, rz,        // 位置与旋转
  w, d, elasticity,            // 尺寸与弹性
  type: 'pad',                 // pad|glass|bell|synth|drum
  color: '#9fe7d5',
  midi: 64, lyric: '月',
  beat: 0.5, dur: 1.2,
  phrase: 1, phraseIndex: 5
}

// 一段：连接 pad[i] 与 pad[i+1]，数量恒为 pads.length - 1
segment = {
  id: 's12', from: 'p12', to: 'p13',
  flightTime: 0,               // 0 = 自动用满两拍间隔；>0.04 秒时生效
  rail: { enabled: false, shape: 'arc', curve: 0.6, ratio: 0.82 }
}

layout = { version: 1, songId, bpm, pads: [], segments: [] }

// 歌曲：notes 是主变体，variants 保存另一套
song = {
  id, title, artist, bpm, phraseSize,
  notes, variants: { song: [...], lyric: [...] },
  variant: 'song' | 'lyric',
  source: 'audio' | 'lyric' | 'midi',
  absoluteTime: true,          // 纯 LRC 曲目：beat 已经是相对秒/spb
  audioId, duration
}
```

存储键建议：

```text
localStorage:  musicstair:songs:v1
               musicstair:layout:<songId>:v1            // 主变体（song）
               musicstair:layout:<songId>:lyric:v1      // 歌词变体
               musicstair:lyrics:v1                     // 曲名 -> LRC 文本
               musicstair:settings:v1
IndexedDB:     musicstair:media:v1  (v2)
               pending / local / audio
```

## 推荐构建顺序（每一步都能验收）

### 1. 脚手架与数据模型

Vite + 原生 ES modules + Three.js；先写 `notes -> pads/segments` 的纯函数，不碰 DOM。

验收：给定 20 个 note，生成 20 个 pad、19 个 segment；同输入布局可复现（固定 seed）。

### 2. 时间轴（项目的核心）

视觉不是物理模拟，而是 **`t -> 小球位置` 的纯函数**：

```js
spb = 60 / bpm
hit.t = (pad.beat - firstBeat + introBeats) * spb
// 音频曲目：introBeats = firstBeat，于是 hit.t = pad.beat * spb = 绝对秒
// 普通曲目：introBeats = 1.2，留出开场下落
```

小球在 `[hit[i].t, hit[i+1].t]` 间插值；导轨用 CatmullRom 曲线；飞行时间可配置：

```js
const depart = t1 - flight;
u = time <= depart ? 0 : (time - depart) / flight;   // 先停后飞
```

验收：拖动任意阶梯，音符触发时刻不变；纯视觉轨迹改变。

### 3. 三维场景

- 环境：渐变天穹、云海、山环、星尘；性能低配时减少粒子/管段。
- 阶梯：RoundedBox + 发光片 + 光晕 + 字精灵；长曲用 InstancedMesh。
- 小球：玻璃球 + 拖尾 + 撞击环/粒子。
- 相机：俯瞰编排视角 + 播放跟随；切换时平滑阻尼，不要瞬移。

验收：1440×900 下普通曲稳定 50+ FPS；320 块曲在集显上 ≥ 20 FPS。

### 4. 音频引擎

- 每个音预调度，不用 `setTimeout` 逐音播放；主时钟是 `AudioContext.currentTime`。
- 音色 = 多正弦分音 + 指数包络 + 低通 + 混响 + 压缩 + 软削波。
- 原曲伴奏单独用 `AudioBufferSourceNode`，与阶梯共用同一时间轴。
- 暂停只停 source，**不要 `suspend()` AudioContext**（见坑 1）。

验收：播放/暂停/拖动进度/倍速/循环后，音符与小球仍对齐；切原曲/阶梯音都有声。

### 5. 媒体库与导入

流水线：

```text
音频/LRC -> 待转换（按曲名绑定）-> 转换 -> 本地音乐 -> 生成阶梯 -> 我的曲库
```

- 待转换项按「去扩展名、小写」的曲名合并；歌曲与 LRC 可分别导入/重导。
- `mode = song` 用起音节奏；`mode = lyric` 用逐字时间轴；纯 LRC 也能转换。
- 转换时同时产出 `songNotes` 与 `lyricNotes`，供主界面切换。
- 原音频 Blob 存 IndexedDB `audio` store，播放时可随时取回。

验收：先导入 LRC 再导入同名音频仍合并为一项；只导入 LRC 可直接生成歌词阶梯。

### 6. 编辑器

- 选中块的参数即时预览，点「确定」才保存，点「取消」回到 baseline。
- 撤销/重做保存完整 layout 快照；结构编辑（插入/删除）也进入同一事务。
- 每块可改字；每段可设飞行时间；可在前/后插入；删除后前后自动连接。
- 端点删除采用「角色继承」：删首块后第二块成为起点，删尾块后倒数第二块成为终点。

验收：插入后 `segments == pads - 1`；删除中间/首/尾后数量与连接正确；取消/撤销可恢复。

### 7. 双变体与另存

- `song.variants.song` 与 `song.variants.lyric` 各自生成布局、各自存 key。
- 切换变体时先保存当前布局，再载入/创建目标布局；播放中切换先暂停。
- 「另存」= 复制曲目为新 id，复制音频 Blob 与两个变体的布局，原曲不变。

验收：切变体后布局数量正确；另存后原曲布局未被改动，新曲可独立编辑。

### 8. 验收

见 [references/testing-and-acceptance.md](references/testing-and-acceptance.md)。至少覆盖：

- 普通曲、LRC 曲、长音频曲三条链路；
- 暂停/继续、seek、倍速、循环、原曲↔阶梯音；
- 编辑器事务、撤销/重做、插入/删除、另存；
- 390px 手机布局无横向溢出。

## 六个最容易踩的坑

1. **切到阶梯音没声音**：暂停时 `await ctx.suspend()` 与恢复播放竞态，`suspend()` 晚到会把刚 resume 的 context 再次挂起，而调度函数只在 `state === 'running'` 时工作。暂停只 `stopAll()`，不要 suspend；需要省电时在页面隐藏且确定不再播放时再处理。
2. **音频曲目整体偏移**：视觉 `hit.t` 用「第一块拍位置」当 intro 时，音频曲目又额外加了前奏。音频曲目必须 `introBeats = firstBeat`，让 `hit.t` 直接等于绝对秒。
3. **导入只播十几秒**：解码时只渲染了前若干秒，或只分析了片段。`decodeAudioData` 得到完整时长后，用 `OfflineAudioContext` 按目标采样率渲染整段（上限 900 秒），并把真实 `duration` 写进曲目。
4. **量化破坏音画同步**：把 beat 四舍五入到整数拍会整体漂移。保留 4 位小数，`beat = onsetSeconds / spb`；只保证严格递增，不做整拍吸附。
5. **长曲卡死**：每块一个 Mesh + 每段两根 Tube，320 块会产生上千 draw call。> 120 块时：板按 `type|color` 合批 InstancedMesh，导轨几何合并，珠链合并或降低段数；字精灵仍是主要开销，可做纹理缓存。
6. **编辑后刷新丢失**：结构编辑只改内存，必须点「确定」才 `saveLayoutNow()`；测试也要先点确定再读 localStorage。撤销/重做后要同时刷新 `songMeta`，否则数量看起来没变。

## 参考文件

- [references/architecture.md](references/architecture.md)：模块、状态、数据流、存储与变体。
- [references/audio-and-lyrics.md](references/audio-and-lyrics.md)：解码、起音、基频、BPM、伴奏时钟、LRC。
- [references/timeline-and-editor.md](references/timeline-and-editor.md)：时间轴公式、飞行/导轨、编辑事务、增删/另存。
- [references/rendering-and-performance.md](references/rendering-and-performance.md)：场景、LOD、实例化、相机、移动端。
- [references/testing-and-acceptance.md](references/testing-and-acceptance.md)：测试矩阵、CDP + Playwright、FPS 与移动端探针。
- [snippets/](snippets/)：可直接借鉴的核心算法（MIT）。

## 交付前的最后检查

- `npm run build` 通过，控制台无 error/pageerror。
- 新导入曲目刷新后仍在，原曲仍可播放。
- 任何结构编辑后 `pads.length - 1 === segments.length`。
- 播放中切原曲/阶梯音/变体不崩、不静音。
- 手机 390px：编辑器、待转换卡片、播放条不横向溢出。
