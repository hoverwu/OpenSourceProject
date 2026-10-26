# 测试与验收

作者 hoverwu · 版本 0.1.0

这类项目的 bug 大多不是“代码报错”，而是“看起来在动，但时间/声音/数据不对”。所以验收要同时覆盖：**结构不变量、音频真实发声、数据落盘、视觉不溢出、长曲帧率**。下面是一套已经跑通的矩阵和脚本骨架。

## 1. 测试矩阵

| 链路 | 输入 | 必须验证 |
| --- | --- | --- |
| 内置曲目 | 无 | 生成、播放、暂停、seek、倍速、循环 |
| 纯 LRC | `.lrc` | 待转换卡片、逐字数量、生成、无音频也能播 |
| 音频 | `.wav/.mp3` | 全曲时长、起音数量、BPM、阶梯数量、伴奏 |
| 音频 + LRC | 同名两文件 | 合并为一项、两种模式、双变体、歌词套用 |
| 编辑器 | 任意曲目 | 选中、改字、飞行时间、确定/取消、单块重置 |
| 结构编辑 | 任意曲目 | 插入、删除首/中/尾、自动连接、撤销/重做 |
| 另存 | 我的曲库 | 新曲独立、原曲不变、音频复制、布局复制 |
| 声音切换 | 音频曲目 | 原曲 ↔ 阶梯音都发声，振荡器增长 |
| 长曲 | ≥300 秒音频 | 320 块、实例化、合并导轨、FPS |
| 移动端 | 390×844 | 无横向溢出、编辑器可滚动、按钮可点 |

## 2. 测试环境

### 启动开发服务

```bash
npm install
npm run dev          # http://localhost:5173/
```

### 连接真实浏览器

优先用系统里已登录的 Chromium 系浏览器，通过 CDP 连接，避免再下载一套 Playwright 浏览器：

```bash
# 先完全退出浏览器，再带调试端口启动
"C:\Program Files\Quark\Quark.exe" --remote-debugging-port=9222
```

> 路径按实际安装位置调整。`--remote-debugging-port` 会让本机任意进程可以控制这个浏览器配置，测试期间不要登录敏感站点；测完关闭该实例。

Playwright 侧：

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page = context.new_page()
    page.goto("http://localhost:5173/", wait_until="networkidle")
    page.wait_for_selector("#loading.done", timeout=20000)
```

运行（项目内无 Python 依赖时）：

```bash
uv run --no-project --with playwright python tools/test_v4.py
```

### 测试音频

不要下载版权音乐。用标准库合成一段可重复的旋律：

```bash
python tools/make_test_wav.py runs/audio-fixture/long-melody.wav
```

生成的 WAV 每个音 0.42 秒、间隔 0.12 秒、16 个音循环；配一个同名 `.lrc` 就能覆盖整条链路。长曲测试可以把旋律重复拼接成 5–6 分钟。

## 3. 关键选择器

参考实现的 DOM id（自建项目可换名，但测试要一一对应）：

```text
#loading.done                应用就绪
#btnLibrary                 打开曲库
#libraryTabs button[data-tab="import"]
#midiFile                   文件输入（音频/LRC/MIDI 共用）
#panel-pending.active       待转换面板
#pendingList .result-card   待转换项
[data-action="import-song"] / "import-lrc" / "convert"
.media-mode select          模式选择（song/lyric）
#panel-localMusic.active    本地音乐面板
#localMusicList .result-card
[data-action="generate"]    生成阶梯
#libraryModal               曲库弹窗
#songTitle / #songMeta      当前曲目标题/元信息
#btnVariant                 变体切换
#btnBacking                 原曲/阶梯音切换
#btnPlay / #timeNow / #progress
#btnMode                    进入/退出编辑
#editor                     参数面板
#padTitle / #padLyric / #flightTime
#editState                  “有未保存的修改”
#btnConfirmEdit / #btnCancelEdit / #btnResetPad / #btnDeletePad
#btnInsertBefore / #btnInsertAfter
#btnUndo / #btnRedo
.mini-save                  曲库卡片上的另存
#toast                      提示文本
```

E2E 里不要用中文按钮文本做定位，改成 `data-action` 或 id；文案会变，选择器不应变。

## 4. 数据断言

### 找布局

结构编辑后 localStorage 里可能有多个布局，按 pads 数量找当前那条：

```python
def find_layout(page, pads):
    return page.evaluate("""(pads) => {
      for (let i = 0; i < localStorage.length; i += 1) {
        const key = localStorage.key(i);
        if (!key || !key.startsWith('musicstair:layout:')) continue;
        const raw = JSON.parse(localStorage.getItem(key));
        const layout = raw?.layout;
        if (layout?.pads?.length === pads) return { key, layout };
      }
      return null;
    }""", pads)
```

### 不变量

```python
assert len(layout["segments"]) == len(layout["pads"]) - 1
for i, seg in enumerate(layout["segments"]):
    assert seg["from"] == layout["pads"][i]["id"]
    assert seg["to"] == layout["pads"][i + 1]["id"]
    assert layout["pads"][i]["beat"] <= layout["pads"][i + 1]["beat"]
```

### 必须点“确定”

插入/删除只改内存，点 `#btnConfirmEdit` 后才写盘。测试顺序永远是：操作 → 断言 UI 数量 → 点确定 → 读 localStorage。直接读会得到上一次的布局，误判为“编辑无效”。

## 5. 声音验证

不要靠录音或人耳。给 `AudioContext.prototype.createOscillator` 打计数器：

```js
window.__oscCount = 0;
const proto = (window.AudioContext || window.webkitAudioContext).prototype;
const original = proto.createOscillator;
proto.createOscillator = function (...args) {
  window.__oscCount += 1;
  return original.apply(this, args);
};
```

流程：

1. 播放原曲模式 1 秒，记录 `before`（应接近 0，因为原曲不走合成器）。
2. 点击 `#btnBacking` 切到阶梯音。
3. 等 1.8 秒，记录 `after`。
4. 断言 `after > before + 10`，且按钮文案变为“阶梯音/原曲”中的正确一项。

这条测试专门抓 “暂停后切阶梯音无声” 的竞态。只断言“按钮可点”没有意义。

## 6. 编辑器与结构编辑

- 用网格点击找一块可选的阶梯：

```python
for y in range(240, 760, 30):
    for x in range(140, 1120, 40):
        page.mouse.click(x, y)
        if not page.locator("#editor").evaluate("el => el.classList.contains('hidden')"):
            break
```

- 插入后数量 +1，`#padLyric` 可编辑。
- 改字、设飞行时间 → `#editState` 应出现“有未保存” → 点确定。
- 读布局，确认新块 `lyric` 与对应段 `flightTime` 落盘。
- 删除后数量回到原值，toast 含“删除”，段数仍为 pads-1。
- 撤销回到插入后的数量，重做回到删除后的数量。
- 删除首/尾时额外确认：新首/尾块的选择下标正确，段连接没有断。

撤销/重做后必须刷新 `#songMeta` 与变体按钮；参考实现曾因为漏掉 `updateSongUI()` 导致测试看到数量不变。

## 7. 另存

用 `page.on("dialog", lambda d: d.accept("新标题"))` 接管 `window.prompt`。

```python
before = page.locator("#mineGrid .song-card h3").all_inner_texts()
page.locator("#mineGrid .song-card").first.locator(".mini-save").click()
page.wait_for_timeout(1500)
after = page.locator("#mineGrid .song-card h3").all_inner_texts()
assert "新标题" in after
assert any(t == 原标题 for t in after)   # 原曲还在
```

再检查 `localStorage` 中 `musicstair:layout:copy-` 开头的键至少有一条，且原曲布局键的值未变。

## 8. 长曲与 FPS

```text
输入：5–6 分钟音频
期望：noteCount <= 320，densityReduced 或 truncatedAudio 标记正确
      桌面集显 >20 FPS（预热后取三次最好值）
```

采样脚本要点：

1. `page.bring_to_front()`，避免后台节流。
2. 注入 rAF 计时器，统计 1 秒内调用次数。
3. 先等 800ms 预热，再连续测三次，取最大值。
4. 不把首次加载的 9–12 FPS 当回归；查看 `renderer.info.render.calls` 更可靠。
5. 如果三次都低，再排查实例化/导轨合并/DPR。

参考数据（Intel UHD 630，1440×900）：320 块预热后 26.8 / 23.9 / 26.8 FPS，判定通过。

## 9. 移动端探针

```python
context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
```

检查：

```js
document.documentElement.scrollWidth <= window.innerWidth + 1
```

并截图编辑器顶部与底部。滚动容器是 `.editor-body`，不是 `#editor`；滚错元素会截到重复画面。

重点看：

- 待转换卡片的“导入歌曲/重新导入歌词/转换”三行按钮不挤压。
- 滑杆标签“飞行时间”不换行（`white-space: nowrap`）。
- 播放条时间、变体按钮、模式按钮不重叠。
- 底部抽屉内部可滚动，页面本身不横移。

## 10. 控制台与构建

```python
page.on("console", lambda m: console.append({"type": m.type, "text": m.text}))
page.on("pageerror", lambda e: errors.append(str(e)))
```

结束时断言 `pageerror` 为空。console 里允许出现浏览器扩展的 `getTopURL` 与 favicon 404，其余 error/warning 都要看。

构建：

```bash
npm run build
```

构建后再用 `npm run preview` 走一遍首屏与播放，避免只在 dev 模式下正确（尤其是相对路径、资源哈希、动态导入）。

## 11. 发布前清单

- [ ] 内置曲目、纯 LRC、音频、音频+LRC 四条链路都能生成并播放。
- [ ] 原曲 ↔ 阶梯音切换有声，振荡器计数增长。
- [ ] 暂停→立即切声→播放，不静音。
- [ ] 任意结构编辑后 `segments == pads - 1`。
- [ ] 撤销/重做数量与布局都正确，标题元信息同步。
- [ ] 另存后原曲布局字节级不变（至少 JSON 深比较相等）。
- [ ] 刷新页面后曲库、布局、歌词、音频都还在。
- [ ] 390px 无横向溢出，编辑器可滚动到底。
- [ ] 320 块长曲预热后 >20 FPS。
- [ ] `npm run build` 通过，preview 无报错。
- [ ] 页脚作者与版本号正确。

## 12. 常见假失败

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 数量一直不变 | 没点确定就读 localStorage | 先点确定 |
| 找不到布局 | 按 songId 找但另存/变体换了 id | 按 pads 数量找 |
| FPS 只有 10 | 页面在后台或被遮挡 | `bring_to_front` + 预热 + 取最好值 |
| 删除断言失败 | 读到了旧布局或同名多份 | 用 count_deleted 而不是 count_before |
| 音频只播十几秒 | 分析/渲染被截断 | 检查 decoded.duration 与 OfflineAudioContext 长度 |
| 切阶梯音没声 | suspend/resume 竞态 | 暂停不要 suspend |
| 移动端截图重复 | 滚错容器 | 滚 `.editor-body` |
