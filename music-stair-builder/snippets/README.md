# 核心代码片段

作者 hoverwu · MIT

这些文件从已验收的 MusicStair v0.4.0 中提炼，去掉业务 UI 后保留算法主干。可以直接复制到项目里改，不要求原项目结构。

| 文件 | 内容 | 依赖 |
| --- | --- | --- |
| `timeline-sample.js` | `Performance`：拍 -> 命中秒数 -> 小球位置/切线，含飞行时间与导轨 | `three` |
| `layout-generator.js` | `createLayout`：音符 -> 盘旋阶梯与段，确定性伪随机 | 无 |
| `lyrics.js` | LRC 解析、逐字阶梯、歌词套用 | 无 |
| `audio-analysis.js` | 整曲解码、起音、基频、BPM、块数抽样 | 浏览器 Web Audio |
| `synth-engine.js` | 多分音音色、混响、压缩、预调度、打击音 | 浏览器 Web Audio |
| `storage.js` | localStorage 布局包装 + IndexedDB 媒体库 | 浏览器 |

## 接入顺序

1. `audio-analysis.js` 产出 `notes`；
2. `layout-generator.js` 把 `notes` 变成 `pads/segments`；
3. `timeline-sample.js` 把 `layout + bpm` 变成每帧位置；
4. `synth-engine.js` 按 `hits` 预约声音；
5. `storage.js` 保存布局、待转换项与原曲 Blob；
6. `lyrics.js` 在任意阶段接入，生成第二变体或把字贴到旋律上。

## 使用注意

- `timeline-sample.js` 的 `introBeats`：音频/LRC 曲目传 `pads[0].beat`，普通曲目传 `1.2`。传错会整体偏移。
- `audio-analysis.js` 的 `beat` 是绝对时间换算的拍，必须配 `absoluteTime = true`。
- `synth-engine.js` 的暂停只调用 `stopAll()`；不要接 `suspend()`。
- `storage.js` 的布局写盘分 `save()` 与 `soon()`；结构编辑用前者，拖动用后者。
- 所有随机都应是确定性的；`Math.random()` 只用于音色微去谐与粒子，不用于布局。

这些片段是 MIT，使用时保留文件头作者与来源即可。
