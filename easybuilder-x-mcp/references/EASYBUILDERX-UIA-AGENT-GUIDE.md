# EasyBuilder X V1.01.376s（威纶通）— UIA 操控知识库（给 Agent 读）

作者：hoverwu ｜ 版本：0.1.5 ｜ 建立：2026-11-06 ｜ 更新：2026-11-07 ｜ 适用：EasyBuilder X V1.01.376s（build 2026.10.14，WEINVIEW 版），默认安装位置 `%ProgramFiles%\EasyBuilderX\EasyBuilderX.exe`（可用环境变量 `EBX_EXE` 覆盖）

本文只写"怎么读、怎么点、哪里会失败"。所有坐标、AutomationId、尺寸均为本机实测；未实测的推断单独标注"未验证"，不得当结论用。

> **维护约定（2026-11-06 起）**：这是活文档。同一会话里每实测出一条新操控知识（新坐标/新 ID/新坑/新边界），立即写入对应小节、递增版本号并追加 §10 更新记录。专用 MCP 工具与 Skill 以本文为事实源。

---

## 0. 一分钟上手（先读，能省几小时）

1. **不需要提权。** EBX 全系 manifest `asInvoker`，以 Medium IL 运行；普通权限进程的 UIA 能完整读面板、点对话框。这点与 Sysmac Studio（High IL）相反。
2. **Ribbon 对 UIA 完全不可见。** 只能坐标点击；页签行 `y=51`，按钮行 `y=100`（窗口内坐标）。
3. **坐标是窗口内坐标。** 屏幕坐标 = 窗口内坐标 + 主窗 `BoundingRectangle` 左上角。窗口每次启动位置都可能不同（实测出现过 `(79,34)` 与 `(96,18)`），必须每次现读，禁止硬编码屏幕坐标。
4. **对话框不在主窗 UIA 子树里。** 保存/打开等 `#32770` 必须 `EnumWindows` 后 `ControlFromHandle`。
5. **画布内容不暴露。** 元件放置、选中、拖动只能坐标化；右侧属性面板可 UIA 语义操作。
6. **它没有任何编程接口。** 无 COM/SDK/插件/工程文件 CLI；`.ebxprj` 是加密二进制容器，不能离线生成或打补丁。UIA 是唯一通用入口。

---

## 1. 软件技术形态（决定能用哪些手段）

| 事实 | 依据 |
| --- | --- |
| Qt5 程序，主窗类名 `Qt5QWindowIcon` | UIA 实测 |
| UI 控件栈 | QtitanRibbon5（Ribbon）+ QtitanDocking3（停靠面板） |
| 进程完整性 | 全部 exe `asInvoker` / Medium IL（`IsUserAnAdmin=False` 下 UIA 正常） |
| 工作区面板 UIA | **可读**（中文 Name 齐全），但 `AutomationId` 基本为空 |
| Ribbon 区 UIA | **完全不可见**：只有一条 `MenuBarControl`（Name=`Minimize the Ribbon`）暴露 |
| 画布 | 单个 `TabControl N=画面` + 深嵌套 `CustomControl`，内容 0 节点暴露 |
| 工程文件 | `.ebxprj` 自定义二进制：magic `18 52 74 00` + `03 00 02 00 00 00 78 01`，熵 7.993 bit/byte，256 种字节全覆盖，strings 零命中（非 ZIP/tar/7z/gzip/xz/zstd） |
| 编译产物 | `.ebxobj`，与 `.ebxprj` 同目录同名；实测 79 MB 量级 |
| 官方 CLI | `ebxtool.exe` 1.0.0 仅 `audit` 子命令（CSV 校验），无工程操作能力 |
| 安装器 | Inno Setup（`unins000.exe` + `TWizardForm`） |

**架构结论**：驱动 = 「Ribbon 走坐标地图 + 面板/对话框走 UIA 语义」。L2 工程文件生成路径关闭。

---

## 2. 接入路径（按推荐顺序）

### 2.1 专用 MCP 服务器（推荐给会话）

```
<项目根>\
  ebx_mcp_server.py        # 24 个 EBX 专用工具，FastMCP HTTP（v0.2.0）
  start-ebx-mcp.bat        # 普通权限启动（无需 UAC），监听 127.0.0.1:8788
  ebx-mcp-smoke-test.py    # 自检：工具清单 + status + screen_list + uia_dump…
  SKILL.md                 # Skill 源稿（与 MCP 同目录）
  tools\sync_skill.py      # 源稿 → ~/.qoder-cn/skills 部署并校验 sha256
```

启动：双击 `start-ebx-mcp.bat`，或

```bat
cd /d "<项目根>"
start-ebx-mcp.bat
```

自检（`NO_PROXY` 含 `[::1]` 时 httpx 会抛 `InvalidURL`，先清空）：

```bat
cd /d "<项目根>"
set NO_PROXY=
set no_proxy=
python ebx-mcp-smoke-test.py 8788
```

MCP 注册（需用户点头且**新开会话**才生效）：`{ "url": "http://127.0.0.1:8788/mcp" }`

**24 个工具**（v0.2.0 新增标记 ★）：

| 工具 | 作用 |
| --- | --- |
| `ebx_status` | 运行状态、标题/工程名、矩形、相关进程与监听端口 |
| `ebx_launch` | 启动 EBX 并等主窗（普通权限） |
| `ebx_windows` | 全部可见顶层窗口（含 `#32770`）；`include_related=True` 连模拟器 |
| `ebx_tree` | 跨窗口 UIA 树文本（限深/限行） |
| `ebx_find` | 正则搜索 Name/AutomationId/ClassName |
| `ebx_click_name` | 按 Name 正则点控件（Invoke 优先） |
| `ebx_click_xy` | 点击；`relative=True` 为窗口内坐标 |
| `ebx_ribbon` | 坐标点页签/按钮/文件后台项 |
| `ebx_ribbon_map` | 返回坐标地图与注意事项 |
| `ebx_screenshot` | 只截主窗，返回路径 + rect |
| `ebx_keys` | SendInput 真实按键（如 `ctrl+s`） |
| `ebx_save_as` | 文件后台 » 另存为 » 写路径 » 保存 » 校验 |
| `ebx_open` | 文件后台 » 打开 » 写路径 » 确认；`discard_unsaved=True` 才点「否」丢弃未保存 |
| `ebx_new_project` | 欢迎页"创建"或 文件 » 新建 |
| ★ `ebx_screen_list` | 画面树全部行 `{name,x,y,w,h}` + 当前画面（读属性「名称」） |
| ★ `ebx_screen_open` | 双击画面行打开/切换，并回读属性「名称」验证 |
| ★ `ebx_screen_elements` | 当前画面元件列表（左区第二棵 TreeControl） |
| ★ `ebx_uia_dump` | 按 main/dialogs/popups/all 导出结构化 UIA 树 |
| ★ `ebx_import_screen_json` | 后台跑导入器，日志 `out/import_*.log`（支持 limit/no_save 等） |
| ★ `ebx_import_status` | 读导入日志：done/total/binds_ok/tasks_ok/finished/errors/tail |
| `ebx_compile` | 工程文件 » 编译；按产物稳定性 + 弹窗判定 |
| `ebx_offline_simulate` | 工程文件 » 离线模拟；回报进程/窗口/端口 |
| `ebx_stop_simulation` | `taskkill cMTRemote` 并查残留 |
| `ebx_artifacts` | 列工程目录 `.ebxprj/.ebxobj` 大小与时间 |

### 2.2 直接写 Python（批量/复杂流程）

| 脚本 | 用法 |
| --- | --- |
| `tools\ebx_probe.py` | `wins / mods / tree [深] [out] / find <正则> [out] / shot <png> / status` |
| `tools\ebx_act.py` | `shot / click_name <正则> / click_xy <x> <y> / keys / find / tree` |
| `tools\sendinput.py` | `sendinput.py "ctrl+s"`（SendKeys/WM_KEYDOWN 对 Qt 无效时用它） |
| `tools\ebx_saveas.py` | 保存对话框填路径（固定目标，参考实现） |

统一解释器：任意 Python 3.10+ 环境，装 `uiautomation 2.0.29`、`fastmcp 3.4.6`、`pillow`（见 `requirements.txt`）。

### 2.3 通用 uiautomation-mcp（备用）

`serve-http.py` → `http://127.0.0.1:8786/mcp`，9 个通用工具。适合临时探查；日常用 2.1 的专用工具。

---

## 3. 元素定位规则（按优先级）

1. **`AutomationId`**：仅原生对话框稳定（见 §4.6）；工作区面板 AutomationId 为空，不要依赖。
2. **`Name`**：工作区面板/页签/对话框文字可用（中文）。`ebx_click_name` / `ebx_find` 走这条。
3. **控件类型 + 矩形**：无 Name 的输入框、机型卡等，取矩形中心坐标点击。
4. **纯坐标**：Ribbon、画布、图标按钮。必须用窗口内坐标，且每次先截图复核。

搜索必须跨**该进程全部可见顶层 HWND**：`#32770` 对话框、下拉、菜单都可能不在主窗子树里。

---

## 4. 控件地图（实测）

### 4.1 坐标系与主窗

- 主窗类 `Qt5QWindowIcon`，标题 `<工程名>.ebxprj - EasyBuilder X - V1.01.376s`（欢迎页无 `.ebxprj` 段）。
- 实测矩形：`1722x919`；左上角会变（`79,34` / `96,18` 都出现过）。
- 截图坐标 = 窗口内坐标；屏幕坐标 = 截图坐标 + 矩形左上角。
- 状态栏含光标坐标、元件尺寸、缩放 `100%`、`CAP/NUM/SCRL`。

### 4.2 Ribbon 页签（y=51，窗口内）

| 页签 | x |
| --- | --- |
| 文件 | 33 |
| 常用 | 97 |
| 工程文件 | 163 |
| 元件 | 230 |
| 资料/历史 | 298 |
| IIoT | 363 |
| 检视 | 417 |
| 工具 | 465 |
| 一般属性（选中元件后出现） | 565 |
| 事件（选中元件后出现） | 615 |

### 4.3 工程文件页签（y=100）

编译 33 ｜ 在线模拟 98 ｜ 离线模拟 167 ｜ 下载PC>HMI 240 ｜ 工程设置 328 ｜ 系统元件 392 ｜ 设备列表 455 ｜ 服务器列表 522 ｜ UAC 590 ｜ 语言 658 ｜ 图片 727 ｜ 字符串 787 ｜ 数据类型 852 ｜ 变量 913 ｜ JS resource 972 ｜ 宏指令 1036 ｜ 条件 1093

### 4.4 元件页签（y=100）

绘图组 x≈28–110（线/曲线/折线/圆弧/圆/扇形/矩形/星形/条形/文字 A）｜指示灯 143 ｜ 开关 193 ｜ 按钮 240 ｜ 项目选单 286 ｜ 滑动开关 338 ｜ 数值 428 ｜ 文本 475 ｜ 日期/时间 545 ｜ 持续时间 605 ｜ 棒图 665 ｜ 嵌入窗口 720 ｜ 2D条码 775 ｜ PDF检视器 825 ｜ 自定义 880

### 4.5 文件后台（点"文件"页签后）

| 项 | x,y |
| --- | --- |
| 新建 | 42,99 |
| 打开 | 42,153 |
| 保存 | 42,205 |
| 另存为 | 42,253 |
| 关闭 | 42,303 |
| 反编译 | 42,355 |
| 语言 | 42,408 |
| 偏好设置 | 42,460 |
| 关于 | 42,511 |
| 退出 | 525,572 |

### 4.6 工作区面板（UIA 可读，Name 定位）

- 检视：页签 `画面` / `窗口`；树下 `画面`。
- 元件：列表（放入的元件以 Name 呈现，如 `数值`）。
- 自定义模板。
- 变量：页签 `数值` / `算术`；表头 `名称 / 类型`。
- 属性：页签 `属性 / 事件 / 方法`；字段 `元件类型 / 名称 / 注释 / 只读 / 数值 / 数据格式 / 显示限制 / 显示当前值 / 模式 / 格式`；`最近的颜色`、`属性信息`。
- 记录：Qt dock，折叠时双击标题不展开（编译日志文本暂不可读，见 §7）。

### 4.7 原生文件对话框（`#32770`）

| 控件 | 保存 | 打开 |
| --- | --- | --- |
| 文件名输入 | `EditControl A=1001` | `ComboBox A=1148`（优先）/ `A=1001` |
| 保存/打开按钮 | `Button A=1` | `Button A=1` |
| 取消 | `Button A=2` | `Button A=2` |
| 文件类型 | `ComboBox A=1136` | 同 |
| 类型选项 | 仅 `工程文件 (*.ebxprj; *.ebxobj)` / `Binary Project (*.ebxprj)` / `Object Project (*.ebxobj)`，**无 EBPro** | 同 |

文件名可用 `ValuePattern.SetValue(全路径)`；失败时退到"聚焦 → Ctrl+A → 删 → 剪贴板粘贴"。

### 4.8 欢迎页

- 机型卡默认 `cMT3075XH`（`cMT3075XH2 / cMT3075XH2 (V2)`，1024×600）。
- "创建"按钮：窗口内 `(1645,884)`（实测可用；窗口尺寸变化时需重采样）。
- 系列下拉 `ComboBox ... Down`；机型 `ListItemControl`（Name 为空）；方向 `CheckBox 水平/垂直`。

---

## 5. 已验证的端到端配方

> 以下全部通过专用 MCP 工具实测（2026-11-06，窗口原点 `96,18` 的会话）。窗口移动后坐标仍有效，因为全部是窗口内坐标。

### 5.1 启动与就绪

`ebx_launch()` → 返回 `started/title/rect/pid`；或 `ebx_status()` 先看是否已在跑。

### 5.2 新建工程

`ebx_new_project()`：欢迎页直接点"创建"；已有工程时走 文件 » 新建。若弹未保存确认，工具返回按钮清单，不替你决定。

### 5.3 另存为

`ebx_save_as(r"<项目根>\work\<工程名>.ebxprj")`：
- 自动打开 文件 » 另存为，找到 `#32770`；
- `ValuePattern` 写入全路径 → 点 `Button A=1`；
- 校验文件存在且大小 > 0；记录 `last_project` 供编译用。
- 实测：31,751 B 工程保存成功，标题立即变为新文件名。
- 目标已存在时会出现第二个 `#32770`，工具自动点"是/Yes"并回报 `overwrite_confirmed`。

### 5.4 打开工程

`ebx_open(path)`：文件 » 打开 » 原生对话框写路径 » `Button A=1`；按标题等待切换。实测通过。

### 5.5 放元件

`ebx_ribbon("元件", "数值")` → `ebx_click_xy(621, 366)`（画布任意点）→ 生成元件，右侧属性面板联动。实测：数值元件 100×40 @ 工程坐标 475,137；属性 `数值` 0→100、`数据格式` 可改。

### 5.6 编译

`ebx_compile(timeout=120)`：
- 工程文件 » 编译；
- 判定 = `.ebxobj` 更新且**连续两次采样大小/时间稳定**（编译是边写边变大：实测中途抓到 14,141,440 B，最终 79,368,013 B）；同时监视 `#32770` 错误弹窗。
- 实测耗时约 5.7 s，产物 79,368,0xx B（多次观测到 …008 / …013 / …016）。
- 注意：不同次编译产物字节数有几字节级差异，**不要用精确大小相等做判据**。

### 5.7 离线模拟 / 停止

`ebx_offline_simulate(timeout=45)`：
- 实测 4.6 s 拉起三进程：`cMTRemote.exe`、`com-x.exe`（TCP 8000）、`dserver-x.exe`（TCP 24763）；
- 返回模拟器窗口：`cMT Remote ( Offline Simulation )`（类 `Qt5QWindowOwnDCIcon`）与一个中文名窗口（类 `Qt5QWindowIcon`，即诊断器）；
- 8000/24763 裸 TCP 非 HTTP，协议未逆；
- 首次可能弹 Windows 防火墙授权：**不代点**，由用户决定。

`ebx_stop_simulation()`：`taskkill /F /IM cMTRemote.exe`，1.5 s 后查残留；实测 com-x/dserver-x 随之退出，`leftovers=[]`。

### 5.8 面板操作

`ebx_find("属性")` → `ebx_click_name(...)` / `ebx_click_xy`。属性输入框可直接 `ValuePattern.SetValue` 或用 `ebx_keys`。

---

## 6. 坑清单（EBX 实测）

1. `uiautomation 2.0.29` **没有** `IsVisible`；`IsOffscreen` 是**属性**（`not c.IsOffscreen`），调用会 `'bool' object is not callable`。
2. `EnumProcessModulesEx` 必须从 `psapi.dll` 取，且显式声明 `argtypes`（`c_void_p`），否则 64 位指针截断 `OverflowError`。
3. 截图坐标 ≠ 屏幕坐标；窗口每次启动位置不同（实测 79,34 与 96,18）。所有点击走"窗口内坐标 + 现读 rect"。
4. 对话框有两种宿主：原生文件框/消息框是独立顶层 `#32770`（`EnumWindows + ControlFromHandle`）；EBX 自己的 Qt 消息框（如「是否要保存该工程文件?」）是无标题顶层 `Qt5QWindowIcon`；另一些对话框以子 `WindowControl` 挂在主窗子树里。找对话框时要同时覆盖三处，并跳过 1×1 的 `Qt5QWindowToolSaveBits*` 隐层窗口。
5. Ribbon 完全不可 UIA；纯图标按钮 Name 为空，只能坐标。
6. `Ctrl+S` 对新工程无效（不脏不存）；统一走"另存为"。`SendKeys` 与 `WM_KEYDOWN` 对 Qt 无效，必须 `SendInput`。
7. 编译大文件是**流式写入**：不能一看到文件变化就判成功，必须等大小/mtime 稳定。
8. 记录面板折叠后双击标题不展开；编译日志文本暂无读取通道。
9. 文件后台打开时点 Ribbon 页签，先发 `Esc` 关后台，避免点在遮罩上（专用工具已内置）。
10. Git Bash 控制台按 cp936 解码会把 MCP 返回的中文 JSON 打成乱码；**数据本身是正确的 Unicode**，看文件或 Python 对象，不要以终端显示判断。
11. 模拟器三段进程级联启动，`cMTRemote` 出现后还要等 `com-x`/`dserver-x` 与窗口创建（约 2 s），否则回报缺项。
12. **不要把主窗设成 `HWND_TOPMOST`**。设上之后 EBX 后续弹出的对话框 / 下拉弹层 / 右键菜单都生成在它**下面**：屏幕上"凭空消失"，点击打在主窗上，而 UIA 仍能枚举到这些控件（极难排查）。提权只用 `SetForegroundWindow` + `SetWindowPos(HWND_NOTOPMOST, SWP_NOSIZE|SWP_NOMOVE)`；弹窗本身再单独 `to_front`（`HWND_TOP` + `SWP_NOACTIVATE`）。
13. **组合框弹层要先"原生激活"对话框**：先在标题栏点一次 `(L+W/2, T+15)`，再点下拉箭头，列表才会真正渲染出来。不点标题栏时条目只存在于 UIA 树，`TreeItem` 点击、方向键 + Enter、`SelectionItemPattern` 全部无效。
14. 「新增...」弹出的任务菜单是**异步绘制**的，点完立刻扫通常扫不到；要在 1.5 s 内轮询 `MenuItemControl`，并准备几个 x 偏移重试。
15. 任务行、元件列表都是自绘，**读不到文字**。点「确定」返回成功不等于落盘：必须重新打开任务对话框、读「画面」组合框的 `ValuePattern`，再取消退出，才算验证通过。
16. 属性面板嵌套很深：标签/输入框都在 **depth >18**，用 16 层 DFS 读到的永远是 `None`。工具里的默认遍历已统一为 `max_depth=30 / max_nodes=20000`。同名 CustomControl 会和 EditControl 叠在同一矩形，取值要按控件引用而不是按矩形比较。
17. **元件 dock 没有 `TabControl`**，只有一个 `CustomControl + TreeControl`；按页签找元件列表会永远返回空。正确做法：左区所有 `TreeControl` 按 y 排序，`[0]` 是画面树、`[1]` 是元件列表。
18. **文档页签栏是自绘的**：`TabItemControl` 恒为空，无法枚举已打开画面。判断当前画面只能读属性面板「名称」行（`_prop_value`），别指望页签 UIA。

---

## 7. 已验证 / 未验证边界

**已实测**
- 启动、欢迎页新建、另存为、打开、放元件、改属性、编译、离线模拟、停止模拟（均通过专用 MCP 工具跑通）。
- 按钮放置与「切换画面」任务、按钮标签文本、按元件列表选择/删除、画面树滚动选页（本次 4 页 105 元件工程跑通）。
- 从 `ebx-screen/1.0` JSON 重建整页：40 元件 / 17 标签 / 3 导航任务 / 3 按钮文字全部成功（§10.5）。
- 专用 MCP 24 工具可用；`ebx_status/screenshot/find/compile/save_as/open/offline_simulate/stop_simulation/artifacts/screen_list/screen_open/screen_elements/uia_dump/import_screen_json/import_status` 实测返回正确（v0.2.0，2026-11-07）。
- 模拟器三进程与端口、模拟器窗口类名。
- `.ebxprj` 为高熵加密容器；无官方 API；打开对话框不支持 EBPro。

**未验证（不得当结论）**
- 报警/配方/表格的 Excel（`libxl.dll`）导入导出入口。
- `com-x:8000` / `dserver-x:24763` 应用层协议。
- 编译「记录」面板文本读取。
- 高 DPI / Ribbon 折叠 / 不同语言界面下的坐标地图（需重新采样）。
- 新建工程时"系列/机型/方向"的非默认选择（目前只验证默认机型卡）。
- 元件多选/对齐、画面复制、画面拖动排序（实测拖动只改选中，不换序）。
- `ebx_new_project` 在"已有未保存工程"时的确认弹窗分支（工具只回报按钮，不自动点）。

---

## 8. 红线与授权

- 防火墙授权、UAC、系统级设置：**不代点**，交由用户。
- 覆盖已有工程前先确认目标路径；工具会回报 `overwrite_confirmed`。
- 不修改 `~/.qoder-cn/memory`、`settings.json`、`mcp-router.json`、既有 `AGENTS.md` 条款（除非用户当轮点名）。
- MCP 注册到 Qoder 需要用户同意并新开会话；不在本会话内偷偷改配置。
- 批量删除/跨目录写入：按用户级 `AGENTS.md` 执行。

---

## 9. 复现清单

```bat
rem 1) 启动专用 MCP（普通权限）
cd /d "<项目根>"
start-ebx-mcp.bat

rem 2) 自检
python ebx-mcp-smoke-test.py 8788

rem 3) 启动 EBX（或让 MCP 的 ebx_launch 做）
"%ProgramFiles%\EasyBuilderX\EasyBuilderX.exe"
```

会话侧注册：`http://127.0.0.1:8788/mcp`。

---

## 10. 页面 JSON 导入 / 导出（官方能力盘点与替代方案）

### 10.1 结论：官方不支持页面级 JSON

- 文件菜单只有：新建 / 打开 / 保存 / 另存为 / 关闭 / **反编译** / 语言 / 偏好设置 / 关于（手册 §2.1）。
- 打开对话框只认 `*.ebxprj` / `*.ebxobj`，**没有 JSON/XML 选项**（实测，§4.7）。
- 「反编译」只是把 `.ebxobj` 还原成可编辑 `.ebxprj`，不是导出 JSON。
- 工程文件本身是加密高熵二进制（§1），不存在官方文本中间格式。

官方手册里全部的"导入/导出"能力只有：

| 能力 | 格式 | 说明 |
| --- | --- | --- |
| 字符串表 | `.csv` / `.xls` / `.xlsx`（运行时也可 `.txt`） | 多语言文本，不含画面结构（手册 §8.2.3） |
| 宏指令 | `.ebm` | 只导出宏代码，不含画面 |
| 审计追踪 | `.csv` | 运行时备份，`ebxtool audit` 校验 |
| 图片 | 常见位图 | 图片库资源 |

手册中 JSON 只出现在授权/证书/设备类错误码（100202、100205、100304、100308 等），与工程/画面无关。

### 10.2 可行的三条替代路径

**A. JSON → EBX（导入）：外部描述 + UIA 驱动生成**
- 自定义 JSON schema 描述「画面 + 元件 + 属性」；
- 由专用 MCP 执行：新建/切换画面 → 点元件页签 → 画布落点 → 属性面板写值；
- 已验证原语：放数值元件、改 `数值/数据格式`、另存为、编译；
- 适合批量生成标准页面；**不是 100% 还原**（事件、绑定、动画、自定义模板嵌套等复杂对象需逐项扩展）。

**B. EBX → JSON（导出）：UIA 读取 + 结构化清单**
- 画面清单：检视面板的 `画面 / 窗口` 树；
- 元件清单：元件面板会列出当前画面全部元件（手册 §2.3.1.3，实测出现 `TreeItemControl 数值`）；
- 属性：选中元件后读属性面板的 `属性/事件/方法`，配合状态栏的坐标与尺寸；
- 产出适合做版本差异、迁移清单、审计；**不是官方备份**，权威备份仍用 `.ebxprj`/`.ebxobj`。

**C. 自定义模板（自定义元件）**
- 手册 §7 的模块化设计可把一组元件做成模板复用，但模板仍存在加密工程内，不能导出 JSON。
- 跨工程复用目前只能走工程文件/模板的复制粘贴，未验证 JSON。

### 10.3 建议的 JSON schema（草案）

```json
{
  "schema": "ebx-page/0.1",
  "screen": { "name": "画面1", "width": 1024, "height": 600 },
  "elements": [
    {
      "type": "数值",
      "name": "温度",
      "rect": { "x": 100, "y": 80, "w": 100, "h": 40 },
      "properties": { "数值": "0", "数据格式": "LREAL" }
    }
  ]
}
```

落地时建议：导入用「幂等 upsert」（按 name 找已有元件 → 改属性；找不到 → 新建），导出按同样 schema 回读，便于 round-trip 对比。

### 10.4 明确边界

- 画布内容 UIA 不可见 ⇒ 导入落点/导出位置必须靠坐标与状态栏，精度受缩放/DPI 影响。
- 属性面板字段多、部分需滚动才实例化 ⇒ 导出不能保证一次读全。
- 不要尝试逆向 `.ebxprj`（高熵加密，L2 已判定关闭）；JSON 桥只做"外部描述 ↔ UI 操作"，不改工程文件。

### 10.5 已落地实现：`ebx-screen/1.0` + UIA 重建（2026-11-07 实测 40/40）

**导出**：`tools/export_screen_json.py` 读 `work/hmi_spec.json` + `work/tags/PipeTags.txt`，产出 `out/Alarm_Trend.screen.json`（20,274 B，UTF-8 无 BOM）。字段：

| 层级 | 字段 | 说明 |
| --- | --- | --- |
| 顶层 | `schema` / `generator` / `source_project` | `ebx-screen/1.0`；generator 带 tool/version/author/exported_at |
| 顶层 | `target` | 软件版本、机型 cMT3075XH、1024×600、zoom 100 |
| 顶层 | `device` | 设备名 PLC_NX502、驱动、IP、寻址方式（CIP 变量名） |
| 顶层 | `tags[]` | 38 个变量：name / data_type / address / comment / rw / scope / addressing |
| 顶层 | `used_tags[]` | 本画面实际用到的 17 个（导入前先核对标签存在） |
| 顶层 | `import` | `native_json_support: false` + 前提 + `style_policy`（样式取 EBX 默认值） |
| `screen` | name / width / height / background / element_count | — |
| `elements[]` | id / type / ebx_kind / name / x / y / w / h | `type` ∈ static_text / numeric_display / indicator / button；`ebx_kind` 是中文原件名 |
| 元素可选 | `text` / `tag` / `readonly` / `label` / `task{type,target}` | 文本内容、绑定变量、只读、按钮文字、切换画面任务 |

**导入**：`tools/ebx_screen_importer.py`（便携副本 `out/ebx_screen_importer.py`，用法见 `out/IMPORT_README.md`）。
流程：找主窗 → 校验画面名 → 新建画面 → 两次拖拽标定画布原点（实测 (245,309)）→ 逐元件「点 Ribbon 图标 → 画布拖框 → 写名称 → 写文本 / 绑标签 / 建任务 / 写按钮文字」。

**实测结论（2026-11-07 20:18）**：把 `Alarm_Trend.screen.json` 重建到「报警与趋势_导入验证」，
**40/40 元件放置成功，17/17 标签绑定 ok，3/3 切换画面任务 ok（含语义复核），3/3 按钮文字 ok**，耗时约 29 min；
截图与原件布局一致。验证后已删除该画面并保存工程（工程仍为 4 页：报警与趋势 / 主监控 / 参数设定 / 手动维护）。

**边界**：本页只含静态文本、指示灯、数值、按钮四类；报警条目、趋势图对象、事件/宏/动画、文字样式（字体/颜色/边框）都**不在** JSON 内，重建后是 EBX 默认样式。跨机器导入前必须先有同名设备与标签（CIP 变量名一致），否则绑定会失败。

### 10.6 UIA 树模型与 MCP v0.2.0 新增工具（2026-11-07 实测）

**树模型**（已写进 `ebx_mcp_server.py` 文件头，作为唯一事实源）：

```
Root
└─ WindowControl  Qt5QWindowIcon  "<工程>.ebxprj - EasyBuilder X - V1.01.376s"   ← 主窗
   ├─ Ribbon 页签/按钮        → 自绘 shell，0 个可点节点，只能用坐标地图
   ├─ 检视 dock
   │  ├─ TabControl「画面 / 窗口」
   │  └─ TreeControl × N
   │     ├─ [0] 画面树   TreeItemControl 行 x=26 w=222 h=28，首行 y≈240
   │     └─ [1] 元件列表 TreeControl (0,420) 行 x=26 w=208 h=28
   ├─ 画布                    → 0 个 UIA 节点；原点 (245,309)；状态栏给 "(x, y) (x2, y2) W x H"
   ├─ 属性 dock               → 嵌套 depth >18；行 = TextControl 标签(x≈1298) + EditControl/ComboBoxControl(x≈1365)
   └─ 文档页签栏              → 自绘，不可枚举
```

**新增 6 个工具**（总数 18 → 24）：

| 工具 | 作用 | 实测 |
| --- | --- | --- |
| `ebx_screen_list()` | 画面树全部行 `{name,x,y,w,h}` + `current_screen` | 4 行，`current_screen="主监控"` |
| `ebx_screen_open(name)` | 双击画面行并回读属性「名称」确认 | `{"ok":true,"opened":"主监控","attempt":0}` |
| `ebx_screen_elements()` | 当前画面元件列表 | 7 行（标题/标签×4/出口温度/设定温度） |
| `ebx_uia_dump(scope)` | 按窗口分组导出结构化树（main/dialogs/popups/all） | `popups` 未展开时返回空数组（符合预期） |
| `ebx_import_screen_json(...)` | 后台跑导入器，日志落 `out/import_*.log` | `limit=1,no_bind,no_nav,no_save` → `finished=true` |
| `ebx_import_status()` | 读日志尾部统计 done/binds_ok/tasks_ok/errors/tail | `done=1,total=40,errors=[]` |

**本轮修掉的缺陷**：`_prop_value` 第三段用 `_iter(w, 16)` 去找输入框，而属性面板深度 >18，导致值恒为 `None`，`ebx_screen_list().current_screen` 与 `ebx_screen_open()` 验证全部失败。改为：标签定位后在同一行（中心 y 差 ≤18）收集 `EditControl/ComboBoxControl` 候选（遍历 30 层），直接对控件引用取 `ValuePattern.Value`（下拉退到 `Selection`）。

**新增的坑**：
- 本机 `NO_PROXY/no_proxy` 含 `[::1]`，`httpx` 会抛 `InvalidURL: Invalid port: ':1]'`。任何 fastmcp/httpx 客户端启动前都要清空这两个变量；`ebx-mcp-smoke-test.py` 与 `tools/mcp_client_test.py` 已在脚本内自动清除。
- 用 venv 的 `python.exe` 启动服务会看到两个同名进程（启动器 + 子解释器），不是重复实例，别一起杀掉。
- `ebx_import_screen_json` 会新建画面（默认用 JSON 里的名字，可用 `screen=` 覆盖）；试跑后要么删除该画面并保存，要么用 `no_save=true` 再丢弃。

## 11. 按钮导航与画面切换（2026-11-07 实测）

### 11.1 按钮任务的建立
- 放好「按钮」后，在属性面板 一般属性 → 任务 行点「新增...」（1355,433），弹出任务菜单：设置数值 / 呼叫元件方法 / **切换画面** / 弹出窗口 / 关闭弹出窗口 / 键盘输入 / 导入导出字符串表 / 新增 if 条件 / 新增 while loop / 等待 / 延迟。
- 「切换画面」菜单项在 (1434,504)。点开是 358×267 对话框（本次出现在 781,392）：类型（默认即“切换画面”）、画面下拉（885,479..1117,505）、动画、确定（1022,608..1066,637）、取消。
- 画面下拉的列表是 `Qt5QWindowPopupDropShadowSaveBits`，条目**不能 UIA 枚举**；按行高几何点击：行高 = popup.h / 画面数，顺序 = 画面树顺序。
- 完成后任务行显示「元件方法: 切换画面 "目标画面"」。

### 11.2 按钮文字
- 属性面板继续往下滚有「标签」组：文本 / 字体 / 字体尺寸(默认 16) / 粗体 / 斜体 / 下划线 / 颜色 / 对齐(3×3)。
- 文本是 ComboBox（空时占位“请输入”）：点字段 → Ctrl+A → 剪贴板粘贴 → Enter。中文不要用 SendInput 逐字打。

### 11.3 批量生成的顺序与陷阱
- 每个按钮：放元件 → 名称 → 任务 → 文本。文本要滚到底，任务要滚到顶。
- 每次放置前必须把属性面板**滚回顶部**（指针停在 1300,620，WheelUp×16）；面板停在底部时 `pane_kind()` 读不到「元件类型」，成功的放置会被误判成 place_failed，重试后留下重叠的未命名按钮。
- 误判后的补救：在左下「元件」列表里点最后一条未命名「按钮」收养，继续配名称/任务；或点行 → Delete 清掉。**元件列表行是比画布更稳的选择入口**（重叠元件也能选中）。
- 切画面后第一次放置最容易失手：先点一次「元件」页签预热 1 s 再放。

### 11.4 画面级事实
- 画面属性行与元件不同：画面 名称 345 / 注释 379 / 底层 413（元件 名称 357）。改画面名点 (1400,345)。
- 画面右键菜单只有：插入画面 / 插入群组 / 开启编辑器 / 关闭编辑器 / 选择全部 / 剪切 / 复制 / 粘贴 / 删除；**没有「设为起始画面」**。工程设置四页（一般属性 / 远端 / 安全 / HMI 型号）也没有起始画面选项。
- **启动页 = 画面树中最先创建的那一页**（实测「报警与趋势」先建，离线模拟每次都从它开始）。树行不支持拖动排序（拖动只改选中）。
- 删除被其他画面按钮引用的画面会弹警告「所选窗口正被其他功能使用……是否仍要删除」，是/否；删除后重建会换内部 ID，指向旧画面的导航任务可能失效。改动前先复制 `.ebxprj` 备份。

### 11.5 离线模拟的截图与点击
- 模拟器被 EBX 盖住后，`SetForegroundWindow` 与 `SetWindowPos(HWND_TOPMOST)` 都可能失效（前台锁 / 提升进程关系），截图会拍到 EBX 主窗 → 误以为“模拟器没反应”。
- 可靠做法：关闭模拟 → 从 EBX「离线模拟」重启（新窗口天然在最前）→ 16 s 内完成点击/截图；或对模拟器窗口 PostMessage 鼠标消息（lParam 用客户区坐标）。
- 客户区不等于画面 1:1：外围有渐变边框，页面等比缩放并居中。用「近白像素包围盒」求页面 (x0,y0,w,h)，换算 canvas→客户区：(x0 + cx·w/1024, y0 + cy·h/600)。

### 11.6 本次落地的导航条
- 4 页 × 3 键，右对齐 y=548 / h=38 / w=140 / x=520,672,824，标签与目标画面同名，每页不含自身。
- 报警与趋势页底部指示灯占到 y=574，左对齐会压灯，因此统一右对齐。

## 12. 更新记录

| 日期 | 版本 | 内容 |
| --- | --- | --- |
| 2026-11-06 | 0.1.0 | 建立：技术形态、接入路径、坐标地图、8 条配方、11 条坑、边界清单 |
| 2026-11-06 | 0.1.1 | 补专用 MCP 18 工具实测结果；编译改为"稳定性判定"（中途 14 MB → 最终 79 MB）；补文件后台坐标、模拟器窗口类名、窗口原点漂移、控制台乱码说明 |
| 2026-11-06 | 0.1.2 | 新增 §10 页面 JSON 导入/导出：官方无 JSON 通道（仅字符串表 CSV/XLSX、宏 .ebm、审计 CSV、图片）；给出 JSON→UIA 导入、UIA→JSON 导出、自定义模板三条替代路径与 schema 草案 |
| 2026-11-07 | 0.1.3 | 新增 §11 按钮导航与画面切换：任务菜单/切换画面对话框坐标、按钮标签文本、批量放置顺序与 pane_kind 误判补救、启动页=最先创建的画面、删除被引用画面的警告、模拟器前台锁与白底包围盒坐标换算；管道加热工程 4 页 105 元件 + 12 个导航键编译通过 |
| 2026-11-07 | 0.1.4 | 新增 §10.5 `ebx-screen/1.0` 落地实现与 40/40 实测（17 标签绑定、3 导航任务、3 按钮文字全 ok）；§6 追加 4 条坑：HWND_TOPMOST 把后续弹窗压到主窗下面、组合框弹层必须先点标题栏原生激活、任务菜单异步绘制需轮询、任务落盘必须重开对话框读 ValuePattern 才算验证 |
| 2026-11-07 | 0.1.5 | MCP 升到 v0.2.0（24 工具）：新增 §10.6 UIA 树模型与 `screen_list/screen_open/screen_elements/uia_dump/import_screen_json/import_status`；修 `_prop_value` 深度 16→30；§6 改坑 4 为对话框三宿主，追加坑 16–18（属性面板深度、元件 dock 无 TabControl、文档页签自绘）；补 NO_PROXY `[::1]` 与双进程说明 |

> 之后每次在本会话获得新知识，追加一行并把改动写进对应小节；同时同步 `EBX-MCP-CONTROL-PLAN.md`、`RESEARCH-LEDGER.md` 与 Skill。
