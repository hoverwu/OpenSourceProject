# 时间轴与编辑器

作者 hoverwu · 版本 0.1.0

时间轴是这类项目的核心：**画面不是物理模拟，而是 `t -> 位置` 的确定性函数**。只要这一点成立，用户怎么拖阶梯都不会破坏音画同步；编辑器、撤销、变体、另存也都能围绕纯数据工作。

## 1. 从拍位置到命中秒数

```js
spb = 60 / song.bpm
firstBeat = pads[0].beat
hit[i].t = (pads[i].beat - firstBeat + introBeats) * spb
```

`introBeats` 的选择：

| 曲目类型 | introBeats | 结果 |
| --- | --- | --- |
| 音频分析曲目（`absoluteTime`） | `firstBeat` | `hit.t = beat * spb`，即原曲绝对秒 |
| 纯 LRC 曲目 | `firstBeat` | 同上，逐字时间即播放时间 |
| 内置/手写曲目 | `1.2` | 开头留 1.2 拍给小球下落 |

务必区分“相对拍”与“绝对秒”。音频分析出的 `beat` 已经是 `onsetSeconds / spb`，再叠前奏就会整体偏移。

尾部：

```js
duration = max(lastHit.t + tailBeats * spb, audioDuration)
```

`tailBeats` 取 2–2.4，让最后一块之后小球还有下落空间。音频曲目的 `duration` 用原曲完整时长，避免进度条在最后一个音处提前结束。

## 2. 采样函数

`Performance.sample(t)` 分四段：

### 前奏 `t < hit[0].t`

```js
u = t / hit[0].t
k = u * u
pos = lerp(start, firstHit, k)
pos.y += sin(pi * u) * 0.12
```

`start` 取第一块命中点上方约 4.6、侧向 1.6–2.4 的位置，形成“从空中落下”的观感。切线用 `t + 0.004` 的差分求，别对二次曲线手推公式，差分更不容易错。

### 尾奏 `t >= hit[last].t`

```js
u = (t - lastHit.t) / (tailBeats * spb)
k = u ** 1.4
pos = lerp(lastHit, end, k)
pos.y += sin(pi * u) * 0.15
```

`end` 在最后一块的外侧偏下 3.2，形成“飞出场景”的收尾。

### 主段

先用二分找 `i`，使 `hit[i].t <= t < hit[i+1].t`：

```js
let lo = 0, hi = hits.length - 1;
while (lo < hi) {
  const mid = Math.ceil((lo + hi) / 2);
  if (hits[mid].t <= t) lo = mid; else hi = mid - 1;
}
i = min(lo, hits.length - 2);
```

然后：

```js
span = max(1e-5, hit[i+1].t - hit[i].t)
flight = segments[i].flightTime || 0

if (flight > 0.04 && flight < span) {
  depart = hit[i+1].t - flight
  u = t <= depart ? 0 : clamp((t - depart) / flight, 0, 1)
} else {
  u = clamp((t - hit[i].t) / span, 0, 1)
}
```

### 位置

- 导轨：`RailPath.getPoint(u)` / `getTangent(u)`。
- 无导轨：抛射弧

```js
pos = lerp(p0, p1, u)
pos.y += arc * 4 * u * (1 - u)
// side 不为 0 时沿水平法线偏移 sin(pi*u)*side
```

`arc` 由距离、弹性、俯仰角决定，建议 `clamp(0.22 + dist*0.07 + elasticity*0.34 + |rx|*0.25, ..., 2.4)`；左右交替 `side` 让连续飞行不总在同一平面。

切线一律用 `u ± 0.004` 的两点差分再归一化。不要直接 `p1 - p0`，抛射弧和导轨的切线都不同。

## 3. 飞行时间

`flightTime` 是“从离开当前块到抵达下一块”的秒数，语义是**先停后飞**：

```text
depart = t1 - flight
t < depart   -> u = 0，小球停在当前块上方
t >= depart  -> u 线性到 1
```

约束：

- `flight <= 0.04` 视为自动，用满两拍间隔。
- `flight >= span` 无效，退回自动，否则会出现 `depart < t0` 的负停顿。
- UI 最大值取 `span`，并显示“本段可用 0.00–X.XX 秒”。
- 修改飞行时间不改变任何 `hit.t`，只改变视觉速度。这是“音画同步”的关键：音符触发由 beat 决定，与飞行时间无关。

需要“更快飞过去、多停一会”就把 `flight` 调小；需要“慢镜头”就调大，但不要超过间隔。

## 4. 导轨

`rail = { enabled, shape, curve, ratio }`：

- `shape`: `arc | wave | spiral | straight`
- `curve`: 0–1.4，弯曲幅度
- `ratio`: 0.35–1，中段曲线占整段的长度比

构建：

```js
a, b = 两块命中点
mid = (a+b)/2
dir = normalize(b-a)
side = normalize(cross(dir, UP))
```

- `arc`：中点沿 `side` 偏移 `dist*(0.1+curve*0.24)`，抬高 `dist*0.055`。
- `wave`：在 1/3、2/3 处左右各偏一次 `dist*0.16*(0.3+curve)`。
- `spiral`：围绕中点转约 0.8 圈，半径 `dist*(0.1+curve*0.14)`。
- `straight`：中点轻微下沉，接近直线。

用 `CatmullRomCurve3(points, false, 'catmullrom', 0.5)`。采样时裁掉两端 `(1-ratio)/2`，两端用短抛射弧接到阶梯：

```js
if (u < a)             flightPoint(p0, railStart, u/a, 0.1)
else if (u <= a + r)   curve.getPointAt(t0 + (u-a)/r * (t1-t0))
else                   flightPoint(railEnd, p1, (u-a-r)/(1-a-r), 0.1)
```

这样小球不会从阶梯边缘“瞬移”到曲线起点。

## 5. 命中与播放循环

每帧：

```js
elapsed = currentElapsed()
index = hitIndexAt(elapsed - 0.0001)   // 已命中到第几块
if (index > lastHit) {
  for (i = lastHit + 1; i <= index; i++) triggerHit(i)   // 补帧，不能只触发最后一个
  lastHit = index
}
sample = perf.sample(elapsed)
world.setBall(sample.pos, sample.tangent)
```

`hitIndexAt` 可以线性扫描（320 个元素足够），也可以二分。关键是**补帧**：低帧率或标签页恢复时可能一帧跨过多块，只触发最后一块会丢音。

`triggerHit(i)` 做三件事：

1. 场景特效：板发光、字放大、撞击环、粒子爆发。
2. 歌词条滚动到当前字。
3. 若有原曲伴奏，不额外发音；纯阶梯音模式下音源已经在调度阶段排好，这里不再 `scheduleNote`，避免重复。

音频模式不要在命中时才发音。用 `scheduleAll(fromElapsed, audioBase)` 一次性预约所有未来音符：

```js
when = audioBase + hit.t / speed
if (when < now - 0.16) return
audio.scheduleNote({ midi, type, when: max(when, now+0.015), ring, pan, velocity })
```

`ring` 按 `dur` 和倍速缩放；预约过于密集时让 WebAudio 自己排队，不要用 `setTimeout`。

## 6. 播放控制

### 播放

1. 若音频曲目且启用了原曲，等音频加载完成；失败则降级为阶梯音并提示。
2. `await audio.unlock()`，必须在用户手势的调用栈里。
3. 选时钟模式。
4. 若已到结尾，重置到 0。
5. `restartClock(state.elapsed)`。
6. 开启跟随相机。

### 暂停

```js
state.elapsed = currentElapsed()
state.playing = false
stopBackingSource()
backing.offset = state.elapsed
audio.stopAll()
world.setFollowing(false)
```

不 `suspend()`。详见 [audio-and-lyrics.md](audio-and-lyrics.md) 第 7 节。

### 跳转

```js
elapsed = clamp(target, 0, duration)
lastHit = hitIndexAt(elapsed - 0.0001)
syncBackingPosition(elapsed)
renderLyric(lastHit)
if (playing) restartClock(elapsed)
```

`restartClock` 在音频模式下会以 0.12 秒提前量重排未来音符；原曲模式重设 source 偏移；perf 模式重设 `performance.now()` 起点。

### 循环

到结尾时保留最多 0.3 秒的溢出作为下一圈起点，重排音符，不要从头创建 AudioContext。

### 倍速

倍速同时影响时钟换算与音符调度：`when = audioBase + hit.t / speed`。改变倍速时先暂停再播放，或重新 `restartClock`，不要只改一个变量导致画面和声音速率不一致。

## 7. 布局生成

自动布局要满足三件事：音高可读、长曲不失控、同输入可复现。

```js
startAngle = -1.15
phraseSize = song.phraseSize || 7
long = count > 48
radiusBase = long ? min(11.5, 8 + count*0.012)
                  : 6.8 + max(0, count-24)*0.04
angleStep  = long ? clamp(0.42*48/count, 0.18, 0.42) : 0.42
spanY      = long ? min(18, 7 + count*0.06) : 7 + count*0.1
```

逐块：

```js
angle = startAngle + i*angleStep + sin(i*0.37)*0.06
radius = radiusBase + sin(i*0.83)*0.22 + clamp((midi-64)*0.03, -0.4, 0.7)
x = cos(angle)*radius
z = sin(angle)*radius
y = 7.4 - spanY*(i/(count-1)) + (midi-64)*0.12 + sin(i*1.7)*0.05
```

- `y` 同时承担“整体下降”和“音高起伏”，所以高音不一定在上方，但相对邻近块可读。
- 朝向 `ry = -angle - PI/2 + jitter`，让块面朝着盘旋方向的切线。
- 俯仰 `rx` 根据前后高度差 `atan2(dy, dxz)` 的 0.28 倍，并夹在 ±0.16。
- 长宽：`w = 1.7 + min(0.75, dur*0.3) + jitter`，`d = 0.95 + jitter`。
- 乐句首块 `bell`，句尾 `glass`，其余 `pad`；低音或每 17 块一次用深靛蓝，增加节奏分层。
- 随机数用 `sin(i*k + salt)` 的确定性伪随机，不要 `Math.random()`；否则每次刷新布局都变。

段：

```js
gap = b.beat - (a.beat + a.dur)
autoRail = gap > 0.08 || (b.beat - a.beat) >= 1.9
```

有停顿或长音时默认开导轨，让小球“走”过去；其余用抛射弧。段数与 pads 数恒为 `n-1`。

## 8. 编辑器事务

### 打开

```js
editSession = { baseline: cloneLayout(layout), dirty: false }
```

### 修改

滑杆/输入只改 `state.layout.pads[i]`，调用 `world.refreshPad(i)`、`world.refreshRails()`、`rebuildPerformance()`、`world.snapCamera()`（或保持视角），并 `markEditDirty()`。不要立即写 localStorage。

`rebuildPerformance()` 必须重建，因为修改 `beat/dur` 会改变 `hit.t` 和时长；只改 `x/y/z` 时理论上不必重建，但统一重建更不容易漏。

### 确定

```js
pushUndo(editSession.baseline)
saveLayoutNow()
editSession.dirty = false
```

`pushUndo` 入栈前先清空 redo，最多保留 40 步。

### 取消

```js
applyLayoutSnapshot(editSession.baseline, { save: false })
```

恢复时不能只替换 `state.layout`，还要重建时间轴、场景、选择、编辑器、歌词、进度条和标题元信息。

### 单块重置

用同一首歌重新 `createLayout(song)`，取同下标的 pad 与 segment 覆盖当前块。下标超出新布局时（曲目音符变少）回退为“保持当前值”。这一步仍处于编辑事务内，需要点确定。

### 整局重置

- 保存一份当前快照进 undo。
- 删除当前变体的布局键。
- 重新生成布局。
- 保持当前选中的下标（若存在）。
- 这是可撤销操作，不要清空 undo 栈。

## 9. 插入

插入位置 `at` 的范围是 `0..pads.length`，代表“插到第 at 块之前”。

### 中间插入

```js
x = (prev.x + next.x)/2
y = (prev.y + next.y)/2 - 0.12
z = (prev.z + next.z)/2
gap = next.beat - prev.beat
beat = gap > 0.002 ? prev.beat + gap/2 : prev.beat   // 防止零间隔导致不递增
midi = round((prev.midi + next.midi)/2)
dur = max(0.2, (next.beat - prev.beat)/2)
```

`beat = prev.beat` 的零间隔分支之后要保证严格递增；如果 `prev.beat` 已经等于 `next.beat`，插入块的 `beat` 必须写成 `prev.beat` 且后续 `refreshLayoutRefs` 不做重排，否则会与 next 同拍。更稳妥的做法是给 next 及之后整体加 `0.001`，或者直接不允许在零间隔处插入。参考实现允许插入但不重排，因此视觉上两块同拍命中，测试时要接受这一点。

### 尾部插入

用前两块的方向外推：

```js
anchor = pads[at-2] || { x: prev.x-1.2, y: prev.y+0.5, z: prev.z }
x = prev.x + (prev.x - anchor.x)*0.55
y = prev.y - 0.5
z = prev.z + (prev.z - anchor.z)*0.55
beat = prev.beat + max(0.5, prev.dur || 0.8)
```

### 头部插入

镜像处理，`beat = max(0, next.beat - max(0.5, next.dur || 0.8))`，`y = next.y + 0.55`。

### 段

插入 pad 后插入一段，模板取 `segments[at-1] || segments[at]`，复制其 `flightTime` 与 `rail`；没有模板用默认 `{enabled:false, shape:'arc', curve:0.6, ratio:0.82}`。然后 `refreshLayoutRefs()` 把段 id/from/to 全部重排。

### 收尾

```js
applyStructuralEdit(at, message)
```

它会修复引用、重建时间轴、重设场景、重置播放头、选中新块、打开编辑器、标记 dirty。结构变化仍要用户点“确定”才保存。

## 10. 删除

```js
const wasFirst = i === 0;
const wasLast = i === pads.length - 1;
pads.splice(i, 1);
segments.splice(min(i, segments.length - 1), 1);
```

- 删中间：同时删掉 `i` 这一段，前后块通过新的 `segments[i]` 相连（由自身连接，或继承被删段的导轨）。
- 删首：`segments[0]` 被删，第二块成为起点，后续连接不变。
- 删尾：`segments[last]` 被删，倒数第二块成为终点。
- 选择跳到 `min(i, pads.length - 1)`；空布局则关闭参数面板。

注意“角色继承”：删首后新首块的 `beat` 不变，`Performance.introBeats` 使用新首块 beat（音频曲目）或 1.2（普通曲目），因此命中时刻整体平移是预期行为。不要试图保留旧首块的时间锚点。

删完必须满足 `segments.length === max(0, pads.length - 1)`。如果原布局的 segments 数量已经不一致，先以 pads 为准重建段。

## 11. 撤销/重做

- 只保存完整 layout 快照，不做命令模式的反向操作。数据量小（320 块约几百 KB 内存），实现简单且不会漏字段。
- `undo` 与 `redo` 互斥栈；新编辑清空 `redo`。
- 应用快照时 `save !== false` 会防抖写盘；撤销本身也应当持久化。
- 若有未确认的编辑，撤销/重做前提示“先确定或取消”，不要悄悄丢弃。
- 恢复选择后重建 `editSession.baseline`，否则下一次取消会跳回旧状态。

## 12. 另存为

复制顺序见 [architecture.md](architecture.md) 第 9 节。验收点：

- 原曲的布局键内容在另存前后完全一致。
- 新曲的 `audioId` 指向自己的 Blob 副本；删除新曲不影响原曲。
- 新曲两个变体都能切换，布局数量与原曲对应变体一致。
- 新曲标题不能与原曲相同，最长 60 字。

## 13. 验收公式

写测试时直接断言这些量，不要只看截图：

```text
pads.length - 1 === segments.length
segments[i].from === pads[i].id
segments[i].to === pads[i+1].id
pads[i].beat < pads[i+1].beat
hit[i].t === (pads[i].beat - pads[0].beat + introBeats) * spb
duration >= lastHit.t
```

结构编辑后读 localStorage 前先点「确定」；否则读到的是上一次保存的布局，测试会误判。
