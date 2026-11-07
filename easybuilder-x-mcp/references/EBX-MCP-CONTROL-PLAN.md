# EasyBuilder X（威纶通）MCP 控制方案

作者：hoverwu ｜ 版本：1.4.0 ｜ 建立：2026-11-06 ｜ 更新：2026-11-07 ｜ 依据：`RESEARCH-LEDGER.md` 与 `EASYBUILDERX-UIA-AGENT-GUIDE.md`（v0.1.5）

> 本文所有"已验证"条目均于 2026-11-06/07 在 EasyBuilder X V1.01.376s（默认装在 `%ProgramFiles%\EasyBuilderX`）上跑通；"未验证"条目见 §8，不得当作结论引用。

## 1. 结论先行

EasyBuilder X **没有任何官方编程接口**（无 COM/SDK/插件/工程 CLI；`ebxtool.exe` 仅审计 CSV 校验）。实测后，可行通路收敛为两条：

1. **L1 UIA 驱动（主力，已验证到端到端）**：普通权限 `uiautomation` + 已部署的 HTTP MCP 服务 `http://127.0.0.1:8786/mcp`（9 工具）。
2. **L4 运行时验证（已验证到进程/端口/诊断器）**：离线模拟拉起 cMTRemote + com-x(8000) + dserver-x(24763) + 诊断器对象树。

**L2 工程文件层已判定关闭**：`.ebxprj` 是自定义二进制容器，payload 高熵（7.993 bit/byte、256 种字节全覆盖、strings 零命中、非 ZIP/tar/7z/gzip/xz/zstd），无法离线生成或打补丁。
**L3 结构化导入**：仅字符串库 CSV 有手册依据（8.2.3）；`libxl.dll` 暗示报警/配方/表格可能有 Excel 通道，未逐个验证。

一个关键的不对称（决定方案形态）：**Ribbon 带完全不可 UIA 访问，而工作区面板完全可读**。所以驱动 = "Ribbon 走坐标地图 + 面板/对话框走 UIA 语义"。

## 2. MCP 落地形态（专用版已部署并自检通过）

主力：**EBX 专用 FastMCP 服务器**（24 个领域工具，`127.0.0.1:8788`，普通权限，v0.2.0）。

```
<项目根>\
  ebx_mcp_server.py        # 专用 MCP：24 个 ebx_* 工具（主力）
  start-ebx-mcp.bat        # 一键启动 8788（无需 UAC）
  ebx-mcp-smoke-test.py    # 自检：工具清单 + status + screen_list + uia_dump…
  SKILL.md                 # Skill 源稿（与 MCP 同目录，便于整体打包）
  tools\sync_skill.py      # Skill 源稿 → %USERPROFILE%\.qoder-cn\skills 部署 + sha256 校验
  EASYBUILDERX-UIA-AGENT-GUIDE.md  # 知识手册（活文档）
  serve-http.py            # 备用：通用 uiautomation-mcp → 127.0.0.1:8786/mcp
  start-mcp-http.bat       # 通用版启动
  mcp-smoke-test.py        # 通用版自检（9 工具）
  tools\ebx_probe.py       # 六探针：wins/mods/tree/find/shot/status
  tools\ebx_act.py         # 驱动：shot/click_name/click_xy/keys/find/tree
  tools\sendinput.py       # SendInput 真实按键（Ctrl/Alt/功能键组合）
  tools\ebx_saveas.py      # 保存对话框：ValuePattern 写路径 + Invoke 保存
  out\                     # 全部 UTF-8 探测结果（截图/树/端口/状态）
  work\                    # 样例工程 Project.ebxprj / Project.ebxobj
```

专用工具（实测可用）：`ebx_status / ebx_launch / ebx_windows / ebx_tree / ebx_find / ebx_click_name / ebx_click_xy / ebx_ribbon / ebx_ribbon_map / ebx_screenshot / ebx_keys / ebx_save_as / ebx_open / ebx_new_project / ebx_compile / ebx_offline_simulate / ebx_stop_simulation / ebx_artifacts / ebx_screen_list / ebx_screen_open / ebx_screen_elements / ebx_uia_dump / ebx_import_screen_json / ebx_import_status`。

MCP 注册：`{ "url": "http://127.0.0.1:8788/mcp" }`（需用户同意 + 新开会话）。EBX 全系 asInvoker（Medium IL），**不需要提权壳**。
备用通用版：`{ "url": "http://127.0.0.1:8786/mcp" }`，9 工具，适合临时探查。

自检实测：24 工具列出（v0.2.0；初版 18）；`ebx_status` 命中主窗；`ebx_find` 正常返回属性面板元素；`ebx_save_as / ebx_open / ebx_compile / ebx_offline_simulate / ebx_stop_simulation / ebx_screen_list / ebx_screen_open / ebx_import_screen_json` 全部端到端通过。

## 3. 控件地图（2026-11-06 实测）

### 3.1 坐标系（最容易翻车的点）

截图坐标 = **窗口内坐标**；屏幕坐标 = 截图坐标 + 窗口原点 `(79,34)`（主窗 rect `79,34 1722x919`，随窗口位置变化，必须每次从 `BoundingRectangle` 读）。`ebx_act.py shot` 保存的就是窗口内画面。

### 3.2 Ribbon（仅坐标，UIA 不可见）

页签行 y=51（窗口内）：`文件(33) 常用(97) 工程文件(163) 元件(230) 资料/历史(298) IIoT(363) 检视(417) 工具(465)`；选中态额外出现 `一般属性(565) 事件(615)` 上下文页签。

工程文件页签（y=100）：编译(33) 在线模拟(98) 离线模拟(167) 下载PC>HMI(240) | 工程设置(328) 系统元件(392) 设备列表(455) 服务器列表(522) UAC(590) 语言(658) | 图片(727) 字符串(787) 数据类型(852) 变量(913) JS resource(972) 宏指令(1036) | 条件(1093)。

元件页签（y=100）：绘图组（线/曲线/折线/圆弧/圆/扇形/矩形/星形/条形/文字 A，x≈28-110）｜指示灯(143) 开关(193) 按钮(240) 项目选单(286) 滑动开关(338)｜数值(428) 文本(475)｜日期/时间(545) 持续时间(605)｜棒图(665) 嵌入窗口(720) 2D条码(775) PDF检视器(825)｜自定义(880)。

> 坐标会随 Ribbon 折叠状态/DPI 变化，使用前先用 `ebx_act.py shot` 复核。

### 3.3 工作区（UIA 可读，AutomationId 为空，按 Name 定位）

- 检视面板页签：`画面 / 窗口`；变量面板：`数值 / 算术`（表头 `名称 / 类型`）。
- 属性面板：`属性 / 事件 / 方法` 三页签；字段 `元件类型 / 名称 / 注释 / 只读 / 数值 / 数据格式 / 显示限制 / 显示当前值 / 模式 / 格式`；`最近的颜色`、`属性信息`。
- 画布：单个 `TabControl N=画面` + 深嵌套 `CustomControl`，**内容不暴露**（元件只能靠坐标放置/选中）。
- 状态栏：光标坐标 `(x, y)`、元件尺寸 `(w x h)`、缩放 `100%`、`CAP/NUM/SCRL`。
- 主窗口类名 `Qt5QWindowIcon`；标题 = `<工程名>.ebxprj - EasyBuilder X - V1.01.376s`（可据此判断保存状态与工程名）。

### 3.4 文件对话框（原生 Win32，AutomationId 齐全）

保存：`EditControl A=1001`（ValuePattern.SetValue 写全路径）→ `ButtonControl A=1`（保存）→ 成功产文件。
打开：文件类型 `A=1136`（仅 `*.ebxprj; *.ebxobj` 三类，**无 EBPro**）；文件名 `A=1148`。
对话框是独立 `#32770` HWND，且**不在主窗的 UIA 子树里**——必须 Win32 `EnumWindows` + `ControlFromHandle` 发现。

## 4. 已验证的端到端配方

### 4.1 启动与就绪判定

```
Start-Process "$env:ProgramFiles\EasyBuilderX\EasyBuilderX.exe"
等待 ≤8s：Get-Process EasyBuilderX | MainWindowTitle -like 'EasyBuilder X*' 且 Responding=True
```

### 4.2 新建工程（欢迎页）

UIA 读机型卡（`cMT3075XH` 默认）→ 坐标点"创建"（窗口内 1645,884）→ 主窗标题变为 `Project.ebxprj - ...`。系列下拉 `ComboBox N=... Down`、机型 `ListItemControl`（Name 为空，靠坐标/卡片文字识别）、方向 `CheckBox 水平/垂直`。

### 4.3 保存 / 另存为

文件页签 » 另存为 → `#32770` 窗口 → `EditControl 1001` SetValue 全路径 → `Button 1` Invoke → 校验文件存在与大小。**注意**：工程未改动时 Ctrl+S 无动作（新工程不脏）。

专用工具 `ebx_save_as(path)` 已把整条链路封装：自动点开文件后台（另存为 = 窗口内 42,253）、填路径、保存、覆盖确认（第二个 `#32770` 自动点"是"）、产物校验并记录 `last_project`。实测 31,751 B 保存成功，标题即时切换。文件后台坐标：新建 42,99 ｜ 打开 42,153 ｜ 保存 42,205 ｜ 另存为 42,253 ｜ 关闭 42,303 ｜ 反编译 42,355 ｜ 语言 42,408 ｜ 偏好设置 42,460 ｜ 关于 42,511 ｜ 退出 525,572。

### 4.4 放元件

元件页签 » 输入组按钮（窗口内 428,100 数值 / 475,100 文本）→ 画布单击（如窗口内 621,366）→ 生成元件（实测：数值 100x40 @ 工程坐标 475,137）；右侧属性面板立即联动，可直接改 `数值`（如 0 → 100）与 `数据格式`。元件出现在左侧"元件"列表（Name=数值）。

### 4.5 编译（含结果判定）

工程文件页签 » 编译（窗口内 33,100）→ 等待 → 检查：同目录 `.ebxobj` 更新时间前进；若失败会出现错误对话框（`#32770`）。

**关键修正（2026-11-06）**：编译是流式写大文件，中途会抓到半成品（实测 14,141,440 B），最终 79,368,013 B。判据必须是「大小与 mtime 连续两次采样稳定」，不能一看到变化就判成功。`ebx_compile` 已按此实现，实测约 5.7 s 完成；不同次产物有几字节级差异（观测 79,368,008 / 013 / 016），禁止用精确大小相等判断。

**目前仍无文本级编译日志读取**（记录面板折叠不展开，见 §8）。

### 4.6 离线模拟（运行时验证）

工程文件页签 » 离线模拟（窗口内 167,100）→ 三个进程 + 诊断器：
- `cMTRemote.exe`：显示端窗口 `cMT Remote ( Offline Simulation )`（类 `Qt5QWindowOwnDCIcon`）
- `com-x.exe`：TCP 8000；`dserver-x.exe`：TCP 24763（均非 HTTP，协议未逆）
- 「诊断器」窗口（类 `Qt5QWindowIcon`）：对象树 `Global Objects → Screen → 画面 → 数值` + Watch 变量监视
- 实测启动 4.6 s；三段进程级联启动，`cMTRemote` 出现后还要等 `com-x/dserver-x` 与窗口创建（约 2 s）再采样，否则回报缺项
- 收尾：`taskkill /F /IM cMTRemote.exe`（com-x/dserver-x 随之退出；`ebx_stop_simulation` 会复查残留）

> 首次会弹 Windows 防火墙授权——按用户规则不代为放行，由用户决定。

## 5. 方法论继承（来自 Sysmac Studio 实战）

1. 先 `SetProcessDpiAwareness(2)` 再做任何矩形/坐标操作。
2. 弹窗/对话框一律独立 HWND：搜索必须跨全部顶层窗口。
3. Git Bash 不能直传 `/xxx` 参数（MSYS 重写），走 .bat/.ps1 或 `//` 前缀。
4. 控制台禁打中文（cp936），全部 UTF-8 落盘再读。
5. 前台锁：`SetForegroundWindow` 失败时先按一次 Alt（`keybd_event`）再置前。
6. 截图按窗口矩形抓（`ImageGrab.grab(bbox=...)`），抓前必须确认 `GetForegroundWindow == hwnd`。
7. 点击前查 `IsEnabled/IsOffscreen`；Invoke 优先于坐标点。
8. MCP 返回的 `elementId` 在 `list_windows` 后失效，必须重新 `inspect_element_tree`。

## 6. EBX 专属坑（本次实测新增）

1. `uiautomation 2.0.29` 无 `IsVisible`；`IsOffscreen` 是**属性**不是方法（调用会 `'bool' object is not callable`）。
2. `EnumProcessModulesEx` 必须从 `psapi.dll` 取，且 `argtypes` 必须显式声明（否则 64 位指针截断 `OverflowError`）。
3. 截图坐标 ≠ 屏幕坐标（差窗口原点）；坐标地图随窗口位置/DPI/Ribbon 折叠变化。
4. `#32770` 对话框不在主窗 UIA 子树里 → `EnumWindows + ControlFromHandle`。
5. Ctrl+S 对新工程无效（不脏不存）；必须走"另存为"或先改内容。
6. 纯图标 Ribbon 按钮 `Name` 为空，只能坐标点击；且整个 Ribbon 对 UIA 不可见。
7. 编译产物 `.ebxobj` 79 MB 量级，注意磁盘与拷贝耗时。
8. 模拟器首次启动触发防火墙提示；不点"允许"不影响本机回环测试。

## 7. 方案编排建议

- **纯 UIA 路径**（推荐起步）：L1 完成"模板工程打开 → 页面/元件/属性操作 → 编译 → 模拟验证"，坐标为辅、UIA 为主。
- **批量文本/多语言**：走字符串库 CSV（L3，手册 8.2.3）。
- **工程骨架生成**：不可行（L2 关闭）。替代：把一个"母版工程"作为模板，用 UIA 复制画面/元件并改属性。
- **闭环反馈**：编译 = 产物时间戳 + 错误弹窗；运行 = 诊断器对象树/Watch（UIA 可读）；端口 8000/24763 待逆向后可升级为协议级回读。

## 8. 局限与未验证

- `com-x:8000` / `dserver-x:24763` 应用层协议未逆（裸 TCP 连接立即关闭、无数据）。
- 「记录」面板为折叠 Qt dock，双击标题不展开；编译记录文本读取未打通。
- 报警/配方/表格的 Excel（`libxl.dll`）导入导出入口未验证。
- 画布内容完全不暴露，元件选中/拖动只能坐标化；高 DPI 或 Ribbon 折叠时需重新采样坐标。
- 机型/系列/方向的非默认选择、画布拖动/多选/对齐、未保存工程的新建确认分支未验证。
- **官方没有页面级 JSON 导入/导出**：打开对话框只认 `.ebxprj/.ebxobj`；官方结构化交换仅字符串表 CSV/XLSX、宏 `.ebm`、审计 CSV、图片。需要 JSON 只能在 UIA 之上自建"外部描述 ↔ UI 操作"桥（详见 Guide §10）。
- 本方案所有实测基于 cMT3075XH / 1024x600 / 中文界面的单机环境。

## 9. 复现步骤

```bat
rem 1) 启动专用 MCP 服务（普通权限）
cd /d "<项目根>"
start-ebx-mcp.bat

rem 2) 自检（24 工具；若 NO_PROXY 含 [::1]，先清空）
set NO_PROXY=
set no_proxy=
python ebx-mcp-smoke-test.py 8788

rem 3) 启动 EBX 并探测
"%ProgramFiles%\EasyBuilderX\EasyBuilderX.exe"
python tools\ebx_probe.py status
python tools\ebx_act.py shot out\shot.png
```

## 10. 画面导航能力（2026-11-07 追加，已实测）

- **按钮 + 切换画面**是 EBX 唯一的跨页跳转方式：按钮 任务行「新增...」→ 切换画面 → 目标画面 → 确定。菜单与对话框坐标见 Guide §11.1；任务保存后显示「元件方法: 切换画面 "X"」。
- **按钮文字**在属性面板底部「标签」组，文本字段支持粘贴中文（Guide §11.2）。
- **启动页不可配置**：画面右键菜单、工程设置四页都没有「起始画面」；实测启动页恒为画面树中**最先创建**的那一页，树行也不能拖动换序（Guide §11.4）。要在主监控启动，只能在建工程时先建该画面（或在接受导航失效风险的前提下删页重建，并重配所有指向它的任务）。
- **批量生成导航键的正确顺序**：放元件 → 名称 → 任务 → 文本；每次放置前把属性面板滚回顶部，否则 `pane_kind()` 误判会留下重叠残件（Guide §11.3）。
- **模拟器截图**：被主窗遮挡后前台锁会让 TOPMOST/SetForegroundWindow 失效；重启模拟后 16 s 内操作，或 PostMessage 点击；页面坐标用近白包围盒换算（Guide §11.5）。
- 落地样例：管道加热工程 4 页 × 3 键右对齐导航条（Guide §11.6），离线模拟逐页点击通过。

## 11. 页面 JSON 迁移（2026-11-07 追加，已实测 40/40）

官方仍然没有页面级 JSON 通道，因此采用「自描述 JSON + UIA 重建」：

- **导出**：`tools/export_screen_json.py <画面>` → `out/<screen>.screen.json`，schema `ebx-screen/1.0`（`target` / `device` / `tags[]` / `used_tags[]` / `import` / `screen.elements[]`）。
- **导入**：`tools/ebx_screen_importer.py <json> [--screen 名] [--force] [--no-bind] [--no-nav] [--limit N]`；新建画面 → 拖拽标定画布原点 → 逐元件点 Ribbon 图标、画布拖框、写名称/文本/绑标签/建切换画面任务/写按钮文字。
- **实测**：`Alarm_Trend.screen.json` 重建整页 **40/40 元件、17/17 标签绑定、3/3 导航任务、3/3 按钮文字 ok**（≈29 min，截图核对布局一致），验证画面随后已删除，工程保持 4 页。
- **关键前提**：目标机同版本 EBX、主窗最大化 1920×1080(100%)、已有同名设备 PLC_NX502 与同名 CIP 标签；否则先导标签或 `--no-bind`。
- **交付包**：`out/Alarm_Trend.screen.json`、`out/ebx_screen_importer.py`、`out/IMPORT_README.md`、`out/EXPORT_IMPORT_RUNBOOK.md`。
- **边界**：样式取 EBX 默认值；报警条目、趋势图对象、动画、宏不在 schema 内；坐标为 1024×600 绝对像素。原生替代仍是同工程内画面全选复制粘贴。

### 11.1 MCP v0.2.0 通道（2026-11-07 追加）

页面级操作已固化进服务端（18 → 24 工具），不再需要直接跑脚本：

| 工具 | 用途 |
| --- | --- |
| `ebx_screen_list` | 画面树全部行 + `current_screen`（读属性「名称」，页签自绘不可读） |
| `ebx_screen_open` | 双击画面行 + 回读属性确认 |
| `ebx_screen_elements` | 当前画面元件列表（元件 dock 是左区第二棵 TreeControl） |
| `ebx_uia_dump` | 按 main/dialogs/popups/all 导出结构化 UIA 树（排查对话框宿主） |
| `ebx_import_screen_json` | 后台跑导入器，日志 `out/import_*.log`；参数 `screen/force/no_bind/no_nav/limit/no_save/wait` |
| `ebx_import_status` | 读日志尾部：`done/total/binds_ok/tasks_ok/finished/errors/tail` |

实测（2026-11-07）：4 行画面、`current_screen="主监控"`、`screen_open` `ok`、元件 7 行；导入 `limit=1,no_bind,no_nav,no_save` → `finished=true, done=1/40, errors=[]`，随后删除临时画面并保存，工程仍 4 页。修复点：`_prop_value` 遍历深度 16→30 才能读到 depth >18 的输入框。

## 12. 更新记录

| 日期 | 版本 | 内容 |
| --- | --- | --- |
| 2026-11-06 | 1.0.0 | 初版：L1 UIA + L4 运行时验证，坐标地图与 6 条配方 |
| 2026-11-06 | 1.1.0 | 专用 MCP 服务器 8788（18 工具）上线并实测；文件后台坐标；编译改稳定性判定（半成品 14 MB → 最终 79 MB）；模拟器级联等待与窗口类名；知识手册与 Skill 建立 |
| 2026-11-07 | 1.2.0 | 新增 §10 画面导航能力：按钮任务（切换画面）、按钮标签、启动页不可配置、批量生成顺序与 pane_kind 误判、模拟器截图前台锁与白底包围盒换算；管道加热工程 4 页 105 元件 + 12 导航键编译/模拟通过 |
| 2026-11-07 | 1.3.0 | 新增 §11 页面 JSON 迁移：`ebx-screen/1.0` schema、导入器实现与 40/40 实测；记录 HWND_TOPMOST 压窗、弹层需标题栏原生激活、任务菜单异步轮询、任务落盘需 ValuePattern 复核四个坑 |
| 2026-11-07 | 1.4.0 | MCP v0.2.0（24 工具）：§11.1 页面级通道 `screen_list/screen_open/screen_elements/uia_dump/import_screen_json/import_status`；修 `_prop_value` 深度；补 UIA 树模型、对话框三宿主、元件 dock 无 TabControl、文档页签自绘、NO_PROXY `[::1]` 与双进程说明 |
