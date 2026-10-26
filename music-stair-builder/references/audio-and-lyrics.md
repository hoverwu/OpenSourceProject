# 音频分析与歌词

作者 hoverwu · 版本 0.1.0

本文覆盖三件事：把任意常见格式变成可分析的 PCM、从 PCM 里估出起音/音高/BPM、把 LRC 变成可演奏的阶梯。末尾解释原曲伴奏时钟，以及“切到阶梯音没声音”的真正原因。

## 1. 解码：必须拿到整首歌

浏览器能解码的格式取决于实现，一般 MP3/WAV/M4A/AAC/OGG/FLAC/Opus 都可以。流程：

```js
const raw = await blob.arrayBuffer();
const decoder = new OfflineAudioContext(1, 1, 22050);
const decoded = await decoder.decodeAudioData(raw.slice(0));
```

两个关键点：

1. `raw.slice(0)`：部分浏览器会 detach 传入的 ArrayBuffer，保留副本方便重试或探测时长。
2. 目标分析采样率固定 22050 Hz，单声道。人声与主旋律的基频基本在 1.1kHz 以下，22050 足够，数据量只有 44.1kHz 的一半。

**不要只渲染前 10–20 秒。** 常见错误是 `new OfflineAudioContext(1, 22050 * 20, 22050)` 后只分析这段，结果导入后只能播十几秒。正确做法：

```js
const seconds = Math.min(decoded.duration, 900);
const frames = Math.floor(seconds * 22050);
const mixer = new OfflineAudioContext(1, frames, 22050);
const src = mixer.createBufferSource();
src.buffer = decoded;
src.connect(mixer.destination);
src.start(0);
const rendered = await mixer.startRendering();
const samples = rendered.getChannelData(0);
```

返回值同时保留：

```js
{
  samples, sampleRate: 22050,
  duration: decoded.duration,       // 原始完整时长，用于进度条和伴奏
  analyzedSeconds: seconds,         // 实际分析时长
  sourceRate: decoded.sampleRate,
  channels: decoded.numberOfChannels
}
```

`duration` 与 `analyzedSeconds` 必须分开。超长音频（播客、现场）只分析前 900 秒，但进度条仍按完整时长显示；UI 上标注“仅分析前 15 分钟”。

错误要具体：解码失败统一提示“格式不受支持、文件损坏或受 DRM 保护”，不要只抛 `EncodingError`。

## 2. 起音检测

用 RMS 能量上升 + 高频含量上升的混合 novelty，比单纯能量更适合有伴奏的流行歌。

参数（22050 Hz）：

```text
窗长 1024，帧移 256（约 11.6ms 一帧）
rms[f] = sqrt(mean(x^2))
hfc[f] = sqrt(mean((x[n]-x[n-1])^2))
novelty[f] = max(0, rms[f]-rms[f-1])/rmsMax
           + 0.6 * max(0, hfc[f]-hfc[f-1])/hfcMax
```

峰值筛选：

```text
局部极大：novelty[f] > 左右邻居
最低高度：noveltyMax * 0.035
静音门限：rms[f] > rmsMax * 0.018
自适应门限：novelty[f] > 邻域均值 * 1.35 + noveltyMax * 0.02
最小间距：0.12 秒
```

如果峰值少于 4 个，退回“每 0.45 秒取一个高于门限的帧”，保证节奏极弱的环境音乐也能生成阶梯；仍不足 3 个就报“没有检测到有效声音”。

起音时间取帧中心：`f * hop / sampleRate`。

## 3. 音高：单声部自相关

对每个起音取一小段：

```text
start = onset + 0.025s          // 跳过瞬态
end   = min(下一拍, onset+0.85s, 分析终点)
最大延迟 tau = sampleRate / 70  // 最低约 70Hz
最小延迟 tau = sampleRate / 1000
```

计算差值函数与累积均值归一化差值（CMND）：

```js
diff[tau] = Σ (x[i] - x[i+tau])^2
cmnd[tau] = diff[tau] * tau / Σ_{k=1..tau} diff[k]
```

取第一个 `cmnd[tau] < 0.18` 的延迟；找不到就取全局最小，且必须 `< 0.42`，否则视为无音高返回 `null`。然后沿下降方向走到局部底，再用三点抛物线插值细化：

```text
refined = tau + clamp(0.5*(a-c)/(a-2b+c), -0.5, 0.5)
freq = sampleRate / refined
midi = 69 + 12*log2(freq/440)
```

只接受 65–1100 Hz、MIDI 34–100。

后续处理：

1. **空值填充**：用前一个有效值；开头空值用第一个有效值；全空用 60。
2. **八度纠正**：与上一个音差超过 10 个半音时，在当前值上试 ±1/±2 个八度，取最接近的。
3. **逐起音取整**，不要做中值滤波。中值滤波会把孤立的高音/低音抹平，而旋律里恰恰常有这种跳进。

这套算法对清唱、单旋律乐器效果好；对和弦、强混响、鼓点密集的段落会不准。产品上必须提供“逐块改音高/改字/删除”的兜底，不要承诺自动转谱级准确。

## 4. BPM

不要用 FFT 做全曲节拍跟踪，代价高且容易错倍。用起音间隔（IOI）中位数：

```js
iois = 相邻起音差，只保留 0.18–1.8 秒
bpm = 60 / median(iois)
while (bpm < 68) bpm *= 2
while (bpm > 168) bpm /= 2
bpm = round(clamp(bpm, 50, 180))
```

每倍频折叠保证结果落在人类可读区间。三拍子、自由速度会有偏差；把它当“视觉速度参考”，不要让 BPM 决定音符的绝对时间。

## 5. 从起音到音符

```js
spb = 60 / bpm
beat = round(t / spb * 10000) / 10000     // 保留 4 位小数
if (beat <= prevBeat) beat = prevBeat + 0.001
dur = 下一拍 ? (下一拍 - t) / spb : 1
time = round(t * 1000) / 1000
```

三条纪律：

1. **绝不四舍五入到整拍**。整拍吸附会让 3 分钟的曲子累计漂移几百毫秒。
2. **严格递增**。密集鼓点可能算出相同 beat，用 0.001 拍递推。
3. **保留 `time` 原始秒**。歌词套用、调试、导出都要用它，而不是反算。

块数上限 320：

```js
if (onsets.length > 320) {
  const step = (onsets.length - 1) / 319;
  indices = [0, round(step), round(2*step), ..., 319]
}
```

均匀抽样而不是截断前 320 个，保证整首歌都有阶梯。返回 `densityReduced: true` 让 UI 提示“已降低密度”。

## 6. 原曲伴奏

音频曲目要同时拥有“原曲”和“阶梯音”两种播放方式。原曲单独解码成 `AudioBuffer`，不要每次播放重新 `decodeAudioData`。

```js
const ctx = new AudioContext({ latencyHint: 'interactive' });
const raw = await blob.arrayBuffer();
const buffer = await ctx.decodeAudioData(raw);
```

播放：

```js
const src = ctx.createBufferSource();
src.buffer = buffer;
const gain = ctx.createGain();
gain.gain.value = backingEnabled ? volume : 0;
src.connect(gain).connect(ctx.destination);
src.start(0, offset);              // offset 为当前逻辑播放头
state.backingStartCtx = ctx.currentTime;
state.backingOffset = offset;
```

当前播放头：

```js
elapsed = backingOffset + (ctx.currentTime - backingStartCtx);
elapsed = Math.max(0, elapsed - audio.latency());
```

暂停/恢复/seek 都只需停掉 source、重设 offset，再按新 offset 起播。原曲模式下**不要**再调度阶梯音，否则会和原曲旋律叠成双声部；阶梯只负责画面与命中特效。

音频曲目的 `Performance.introBeats` 必须设为 `layout.pads[0].beat`，这样：

```text
hit.t = (beat - firstBeat + introBeats) * spb = beat * spb = 绝对秒
```

如果仍用普通曲目的 `introBeats = 1.2`，整条阶梯会晚 1.2 拍，且越到后面越像“错位”。

## 7. 切到阶梯音为什么没声音

典型现象：导入音频后先播原曲，点“阶梯音”按钮，画面在动但没有声音；再切回原曲又正常。

根因不是音色引擎，而是 **AudioContext 的 suspend/resume 竞态**：

1. 暂停时调用了 `await ctx.suspend()`。
2. 用户立刻点播放，`ctx.resume()` 开始执行。
3. 前一个 `suspend()` 的 Promise 稍后才落地，把已经 running 的 context 再次挂起。
4. 调度函数只在 `ctx.state === 'running'` 时创建音源；此刻不是 running，于是整首曲子一个音都没排上。

修复原则：

- **暂停只 `stopAll()`，不 `suspend()`。** 页面隐藏且确定不再播放时，才考虑挂起。
- `unlock()` 里如果 `state === 'suspended'` 就 `resume()`，然后用一个 1 帧静音 buffer 确认真的在跑。
- 调度前检查 `ctx.state`；若不在 running，本次播放降级为 `performance.now()` 动画并提示，而不是静默失败。
- 切原曲/阶梯音按钮只改增益与是否调度，不重建 context，也不 stop 伴奏以外的节点。

验证：先在原曲模式播放 2 秒，暂停，立刻切阶梯音并播放，`oscillator` 数量应持续增加（例如 0 → 数百），而不是一直为 0。

## 8. LRC 解析

支持格式：

```text
[ti:标题] [ar:歌手] [offset:+200]
[00:12.34]第一行
[00:15.00][00:45.00]副歌重复
[01:02.5]一位小数
[01:03.123]三位小数
```

规则：

- 一行可以有多个时间标签，展开成多条。
- `[offset:ms]` 累加到所有时间，负数也允许。
- 元数据标签（ti/ar/al/by/offset/length/re/ve）不产生歌词行。
- 小数位按 `0.xxx` 补齐：`.5` → 0.500 秒，`.05` → 0.050 秒。
- 时间钳制到 ≥ 0，最后按时间稳定排序。
- 没有时间标签的行直接忽略；文件里如果一行有效行都没有，导入时明确提示“没有找到 [mm:ss.xx]”。

去标点用 Unicode 属性，不要只写 `[，。！？]`：

```js
Array.from(text.replace(/[^\p{L}\p{N}]/gu, ''))
```

`Array.from` 保证中文与 emoji 按码点拆分，不会把代理对拆坏。

## 9. 逐字阶梯

标准 LRC 只有整行时间，没有逐字时间。可行的近似：

1. 每行字数 `n`，行时长 = 下一行开始 - 本行开始；最后一行用 `duration` 或“字数 × 0.26 秒”。
2. 行内均分：`t_i = start + i * span/n`。
3. 单行最长 18 秒，避免超长间奏把字拉得极稀。
4. 每个字一个 note，`beat = t/spb`，`dur = min(8, max(0.12, step))`。
5. 音高用五声音阶轮廓循环，按行做基音偏移，保证旋律平稳但不重复：

```js
const LYRIC_SCALE = [0,2,4,7,9,12,14,16,19,21,24,21,19,16,14,12,9,7,4,2];
base = 57 + (lineIndex % 7) * 2 + (lineIndex % 2 ? 5 : 0);
midi = clamp(base + LYRIC_SCALE[i % len] - 6, 45, 82);
```

6. 排序后强制严格递增（0.001 拍）。

纯 LRC 曲目的 `absoluteTime = true`，`introBeats` 取第一块 beat，播放头直接按 `beat * spb` 对齐。

## 10. 歌词套到已有旋律

有音频又有 LRC 时，不要用逐字阶梯替代旋律，而是把字贴到已有音符上：

```text
对每一行 [start, end)：
  收集 time 落在区间内的 note 下标
  把该行字符按比例切成 idx.length 段
  每段最多 2 个字写入 note.lyric（便于精灵渲染）
```

实现细节：

- 先把所有 `note.lyric` 清空，避免旧歌词残留。
- note 时间优先用 `note.time`，没有则 `beat * spb`。
- 行区间左闭右开，边界减 0.001 防重叠。
- 没有音符落入的行直接跳过；不要强行塞到最近音符，否则间奏后的第一句会错位。
- 返回被写入的音符数，用于 UI 提示“已套用 N 个字”。

## 11. 导入顺序与绑定

待转换项按“去扩展名 + trim + lowercase”的曲名合并：

```js
baseKey('晴天.mp3') === baseKey('晴天.lrc') === '晴天';
```

流程必须支持任意顺序：

- 先音频后歌词：歌词回填 `record.lrcText`，并尝试套用到同名的已转换记录。
- 先歌词后音频：已有 pending 项保留 `mode='lyric'`；导入音频后如果用户选择“按歌曲转换”，就用音频节奏，同时保留 `lyricNotes` 作为第二变体。
- 只导入 LRC：允许直接转换与生成，`source='lyric'`，没有 `audioId`。
- 重导：按钮文案变成“重新导入歌词/歌曲”，覆盖同一项，不新增卡片。

UI 上必须显示两个独立按钮与一个模式选择；不要用一个“导入”按钮猜用户意图。

## 12. 自测清单

- 一首 3 分钟 MP3：进度条总时长与播放器一致，误差 < 0.2 秒。
- 纯 LRC：生成后阶梯数量等于有效字数，首字时间与第一行时间一致。
- 音频 + LRC：切换“歌曲阶梯/歌词阶梯”两套布局都存在，播放都不静音。
- 暂停后立刻切阶梯音：有声音，振荡器数量增长。
- 原曲播放时拖动进度：伴奏与小球同时跳到新位置，不出现双重旋律。
- 超 15 分钟音频：只分析前 900 秒，UI 有截断提示，进度条仍完整。
