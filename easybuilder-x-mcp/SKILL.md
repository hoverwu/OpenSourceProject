---
name: easybuilder-x-mcp
description: >
  控制威纶通/威纶 EasyBuilder X（EBX）HMI 组态软件：UIA + Ribbon 坐标地图驱动启动、新建/打开/另存为、
  放置元件、修改属性、编译、离线模拟与停止、画面枚举/切换、页面 JSON 导入。配套专用 MCP 服务器（127.0.0.1:8788，24 个 ebx_* 工具）。
  触发场景：自动化操作 EasyBuilder X、处理 .ebxprj/.ebxobj 工程、威纶触摸屏画面批量编辑、
  编译与离线模拟验证、UIA 点不到 Ribbon 或画布、保存/打开原生对话框自动化。
argument-hint: <任务，例如 "打开示例工程并编译">
---

# EasyBuilder X（威纶通）MCP 控制 Skill

作者：hoverwu ｜ 版本：0.3.0 ｜ 建立：2026-11-06（2026-11-07 补画面导航；2026-11-07 补 UIA 树模型与 6 个新工具）
事实源：`references/EASYBUILDERX-UIA-AGENT-GUIDE.md`（与本 Skill 同目录的 `references/` 下，活文档，先读它）

## Overview

EasyBuilder X **没有官方 API**（无 COM/SDK/插件/工程 CLI），`.ebxprj` 是加密二进制容器。
唯一通用入口是 **UIA**，且存在关键不对称：

- 工作区面板 / 原生对话框：UIA 可读可点（面板 Name 齐全，AutomationId 为空）；
- Ribbon 区：UIA 完全不可见，只能坐标点击；
- 画布：元件内容不暴露，只能坐标放置/选中。

本 Skill 通过专用 MCP 服务器 `ebx_mcp_server.py` 把「坐标地图 + UIA 语义 + 对话框 AutomationId」固化成领域工具，避免每次重新摸索。

## 硬性前提

1. **不需要 UAC。** EBX 全系 `asInvoker` / Medium IL；服务与脚本都用普通权限。
2. **坐标一律用窗口内坐标。** 屏幕坐标 = 窗口内坐标 + 主窗 `BoundingRectangle` 左上角；窗口每次启动位置不同（见过 79,34 与 96,18），禁止硬编码屏幕坐标。
3. **Ribbon 只认坐标**：页签行 y=51，按钮行 y=100。
4. **对话框有三种宿主**：原生文件框/消息框是独立顶层 `#32770`；EBX 自己的 Qt 消息框（如「是否要保存该工程文件?」）是无标题顶层 `Qt5QWindowIcon`；还有些对话框以子 `WindowControl` 挂在主窗子树里。三种都要找，且要跳过 1×1 的 `Qt5QWindowToolSaveBits*`。
5. **画布操作只能坐标**；放完元件后属性面板可用 Name/ValuePattern 操作。
6. **编译是流式写大文件**（79 MB 量级），必须等大小/mtime 稳定再判成功。
7. **画面树/元件列表都是 `TreeControl` 的 `TreeItemControl` 行**：画面树在左区第一棵，元件列表在第二棵；**元件 dock 没有 TabControl**，不能按页签找。
8. **文档页签栏是自绘的**，UIA 读不到；判断"当前打开哪个画面"只能读属性面板「名称」的值。
9. **下拉弹层/右键菜单是异步渲染的独立 `Qt5QWindowPopupDropShadowSaveBits` 顶层**，展开后要轮询 ≤1.5 s 才能枚举到条目。

## UIA 树模型（v0.2.0 实测）

```
Root
└─ WindowControl  Qt5QWindowIcon  "<工程>.ebxprj - EasyBuilder X - V1.01.376s"   ← 主窗
   ├─ Ribbon 页签/按钮        → 自绘 shell，0 个可点节点，只能用坐标地图
   ├─ 检视 dock
   │  ├─ TabControl「画面 / 窗口」
   │  └─ TreeControl × N
   │     ├─ [0] 画面树   TreeItemControl 行 x=26 w=222 h=28，首行 y≈240
   │     └─ [1] 元件列表 TreeControl (0,420) 行 x=26 w=208 h=28
   ├─ 画布                    → 0 个 UIA 节点；原点 (245,309)，状态栏给 "(x, y) (x2, y2) W x H"
   ├─ 属性 dock               → 嵌套 depth >18；每行 = TextControl 标签(x≈1298) + EditControl/ComboBoxControl(x≈1365)
   └─ 文档页签栏              → 自绘，不可枚举
```

属性面板的读法（`_prop_value`）：先找 `TextControl` 标签（x > 主窗左 + 600），再在同一行（中心 y 差 ≤18）找最左侧的 `EditControl`/`ComboBoxControl`，取 `ValuePattern.Value`（下拉退到 Selection）。**遍历深度必须 ≥30**，之前用 16 层永远读不到值。

## 六条铁律（踩过的坑）

1. **对话框三宿主**：`#32770`、`Qt5QWindowIcon`、主窗内子 `WindowControl` 都要认，别只按类名 `#32770` 过滤。
2. **弹层异步**：点开菜单后先 `sleep`/轮询再枚举，点完立刻读会得到空列表。
3. **绝不把主窗设成 `HWND_TOPMOST`**：之后所有对话框/弹层都会渲染在它下面；需要置前用 `HWND_NOTOPMOST` + 对弹窗 `HWND_TOP|SWP_NOACTIVATE`。
4. **下拉要先激活原生标题栏**：在 (L+W/2, T+15) 点一次，弹层才真正渲染。
5. **任务行自绘**：点「确定」后必须重开对话框读「画面」值确认落盘。
6. **删被引用画面会换内部 ID**：导航任务会失效，先备份 `.ebxprj`。

## 快速启动

```bat
cd /d "<项目根>"
start-ebx-mcp.bat
```

自检（若 `NO_PROXY` 含 `[::1]`，httpx 会抛 `InvalidURL: Invalid port: ':1]'`，先清空）：

```bat
cd /d "<项目根>"
set NO_PROXY=
set no_proxy=
python ebx-mcp-smoke-test.py 8788
```

单次调用任意工具：`python tools/mcp_call_once.py <tool> '{"k":v}' [port]`。

会话侧注册（需用户同意 + 新开会话）：`{ "url": "http://127.0.0.1:8788/mcp" }`

MCP 不可用时，直接用 `tools/` 下的脚本（导入器 / 导出器 / 校验器）。Python 依赖：`uiautomation`、`fastmcp`。

## 工具速查（24 个）

| 场景 | 工具 |
| --- | --- |
| 看状态 / 端口 | `ebx_status` |
| 启动 | `ebx_launch` |
| 窗口 / 树 / 查找 | `ebx_windows(include_related)` / `ebx_tree` / `ebx_find` |
| UIA 结构导出 | `ebx_uia_dump(scope=main\|dialogs\|popups\|all, max_depth, max_lines)` |
| 点击 | `ebx_click_name`（面板/对话框）、`ebx_click_xy`（窗口内坐标）、`ebx_ribbon`（页签/按钮/文件后台） |
| 截图 / 坐标图 | `ebx_screenshot` / `ebx_ribbon_map` |
| 按键 | `ebx_keys("ctrl+s")`（SendInput，真实按键） |
| 工程 | `ebx_new_project` / `ebx_save_as` / `ebx_open(path, discard_unsaved)` |
| 画面 | `ebx_screen_list` / `ebx_screen_open(name)` / `ebx_screen_elements` |
| 页面 JSON | `ebx_import_screen_json(...)` / `ebx_import_status` |
| 编译 | `ebx_compile`（稳定性判定 + 错误弹窗） |
| 模拟 | `ebx_offline_simulate` / `ebx_stop_simulation` |
| 产物核验 | `ebx_artifacts` |

## 坐标地图（窗口内）

- 页签 y=51：文件 33 ｜ 常用 97 ｜ 工程文件 163 ｜ 元件 230 ｜ 资料/历史 298 ｜ IIoT 363 ｜ 检视 417 ｜ 工具 465 ｜ 一般属性 565 ｜ 事件 615
- 工程文件 y=100：编译 33 ｜ 在线模拟 98 ｜ 离线模拟 167 ｜ 下载PC>HMI 240 ｜ 工程设置 328 ｜ 系统元件 392 ｜ 设备列表 455 ｜ 服务器列表 522 ｜ UAC 590 ｜ 语言 658 ｜ 图片 727 ｜ 字符串 787 ｜ 数据类型 852 ｜ 变量 913 ｜ JS resource 972 ｜ 宏指令 1036 ｜ 条件 1093
- 元件 y=100：指示灯 143 ｜ 开关 193 ｜ 按钮 240 ｜ 项目选单 286 ｜ 滑动开关 338 ｜ 数值 428 ｜ 文本 475 ｜ 日期/时间 545 ｜ 持续时间 605 ｜ 棒图 665 ｜ 嵌入窗口 720 ｜ 2D条码 775 ｜ PDF检视器 825 ｜ 自定义 880
- 文件后台：新建 42,99 ｜ 打开 42,153 ｜ 保存 42,205 ｜ 另存为 42,253 ｜ 关闭 42,303 ｜ 反编译 42,355 ｜ 语言 42,408 ｜ 偏好设置 42,460 ｜ 关于 42,511 ｜ 退出 525,572
- 欢迎页"创建"：1645,884
- 保存对话框：`EditControl A=1001` → `Button A=1`；打开：`ComboBox A=1148` → `Button A=1`
- 文件类型只有 `*.ebxprj / *.ebxobj`，**不能导入 EBPro**

## 已验证配方

1. **新建**：`ebx_new_project()` → 标题出现 `.ebxprj`。
2. **另存为**：`ebx_save_as(全路径)` → 自动走文件后台 + 原生对话框 + 覆盖确认 + 产物校验。
3. **打开**：`ebx_open(全路径)`；若有未保存提示挡住，用 `ebx_open(全路径, discard_unsaved=True)`（工具只在明确要求时点「否」，并回读标题确认）。
4. **放元件**：`ebx_ribbon("元件","数值")` → `ebx_click_xy(x,y)` → 属性面板联动。
5. **编译**：`ebx_compile()` → 等 `.ebxobj` 稳定（实测约 5.7 s，79 MB），有错误弹窗则返回文本。
6. **模拟**：`ebx_offline_simulate()` → cMTRemote + com-x:8000 + dserver-x:24763（实测 4.6 s）；`ebx_stop_simulation()` 清场。
7. **画面导航**：放「按钮」→ 名称 → 任务行「新增...」(1355,433) →「切换画面」(1434,504) → 对话框里选目标画面 → 确定；再滚到属性面板底部「标签」组写按钮文本（粘贴中文）。详细坐标与坑见 Guide §11。
8. **模拟器逐页验证**：重启模拟后 16 s 内点击（被遮挡后前台锁会让 TOPMOST 失效）；页面坐标 = 白底包围盒 (x0,y0,w,h) 上按 (x0+cx·w/1024, y0+cy·h/600) 换算。
9. **枚举/切换画面**：`ebx_screen_list()` 返回每行 `{name,x,y,w,h}` 与 `current_screen`；`ebx_screen_open("主监控")` 双击行并回读属性面板「名称」确认；`ebx_screen_elements()` 读元件列表。
10. **页面 JSON 导入**：`ebx_import_screen_json(json_path="out/Alarm_Trend.screen.json", screen="临时_导入测试", limit=1, no_bind=True, no_nav=True, no_save=True, wait=170)` 先小样试跑，`ebx_import_status()` 看 `done/total/binds_ok/tasks_ok/finished/errors/tail`；试跑后删除临时画面并保存。

## 坑（务必遵守）

- `uiautomation 2.0.29` 无 `IsVisible`，`IsOffscreen` 是属性，不要加括号。
- `Ctrl+S` 对不脏的新工程无效，统一走"另存为"；SendKeys/WM_KEYDOWN 对 Qt 无效，必须 SendInput。
- 编译中途文件是半成品（实测抓到 14 MB，最终 79 MB），**必须等稳定**；不同次产物有几字节级差异，别用精确大小相等。
- Git Bash 终端把中文 JSON 显示成乱码是 cp936 显示问题，数据本身没问题。
- 模拟器首次可能弹防火墙授权：**不代点**，交用户决定。
- 记录面板折叠后双击不展开；编译日志文本暂不可读。
- 打开文件后台时点 Ribbon 先发 `Esc`（工具已内置）。
- 属性面板停在底部时 `pane_kind()` 读不到「元件类型」，会把成功的放置误判为失败并留下重叠残件；每次放置前先把面板滚回顶部，误判后用「元件」列表行收养/删除。
- 启动页恒为**最先创建**的画面，画面菜单/工程设置都没有「起始画面」，树行也不能拖动排序。
- 删除被其他画面按钮引用的画面会弹「正被其他功能使用」警告，重建会换内部 ID 使导航任务失效——先备份 `.ebxprj`。
- 模拟器被主窗遮挡后 `SetForegroundWindow`/`HWND_TOPMOST` 可能都不生效，截图会拍到主窗；重启模拟并在最前时操作。
- **别把 EBX 主窗设成 `HWND_TOPMOST`**：之后弹出的对话框/下拉弹层/右键菜单会生成在它下面，屏幕上"消失"、点击落空，UIA 却照样能枚举到。用 `HWND_NOTOPMOST` 恢复，再对弹窗单独 `HWND_TOP + SWP_NOACTIVATE`。
- 任务对话框里的画面下拉：**先在标题栏 (L+W/2, T+15) 点一次**再点箭头，弹层才会真正渲染；否则条目只在 UIA 树里，点/键盘都无效。
- 「新增...」的任务菜单异步绘制，要点完轮询 1.5 s；任务行自绘读不到文字，**点「确定」后必须重开对话框读「画面」值**才算落盘（否则会假成功）。
- 属性面板嵌套 depth >18：遍历给 16 层读到的永远是 `None`；同名 CustomControl 会与 EditControl 叠在同一矩形，按控件引用取值，别按矩形比对。
- 文档页签栏自绘，`TabItemControl` 永远是空的；判断当前画面请读属性面板「名称」（`ebx_screen_list().current_screen`）。
- 若 `NO_PROXY`/`no_proxy` 里含 `[::1]`：任何 httpx/fastmcp 客户端都要先 `NO_PROXY= no_proxy=`，否则 `InvalidURL: Invalid port: ':1]'`。
- `python.exe` 启动后出现两个同名进程是正常现象（venv 启动器 + 子解释器），别当成重复实例全部杀掉。

## 页面 JSON 导入 / 导出

**官方没有页面级 JSON 通道。** 打开对话框只认 `.ebxprj/.ebxobj`；「反编译」只把 `.ebxobj` 还原成 `.ebxprj`。官方导入导出只有：字符串表 CSV/XLSX、宏指令 `.ebm`、审计 CSV、图片。

已落地的桥（`ebx-screen/1.0`）：

- **导出**：`tools/export_screen_json.py <画面名>` → `out/<screen>.screen.json`；顶层含 `target`/`device`/`tags[]`/`used_tags[]`/`import{style_policy}`，`elements[]` 用 `type`(static_text/numeric_display/indicator/button) + `ebx_kind`(中文原件名) + x/y/w/h + 可选 `text`/`tag`/`readonly`/`label`/`task`。
- **导入**：`tools/ebx_screen_importer.py <json> [--screen 名称] [--force] [--no-bind] [--no-nav] [--limit N] [--no-save]`；找主窗 → 新建画面 → 两次拖拽标定原点 → 逐元件「点 Ribbon 图标 → 画布拖框 → 写名称 → 文本/绑标签/建任务/写按钮字」。MCP 侧用 `ebx_import_screen_json` 后台跑 + `ebx_import_status` 查进度。
- **实测**：2026-11-07 从 `Alarm_Trend.screen.json` 重建整页 **40/40 元件、17/17 标签、3/3 切换画面任务、3/3 按钮文字全部 ok**（≈29 min）；同日晚 MCP 通道 `limit=1 + --no-bind + --no-nav + --no-save` 重建 1 个元件、`finished=true`，临时画面已删除、工程仍 4 页。样式为 EBX 默认值，报警条目/趋势图对象/动画/宏不在 schema 内。
- **前提**：目标机同版本 EBX、已最大化 1920×1080(100%)、已有同名设备与 CIP 标签；否则先导标签或加 `--no-bind`。
- 交付包：`out/Alarm_Trend.screen.json` + `out/ebx_screen_importer.py` + `out/IMPORT_README.md` + `out/EXPORT_IMPORT_RUNBOOK.md`。
- **不要逆向 `.ebxprj`**：高熵加密，无官方格式。详细盘点见 Guide §10 / §10.5。

## 未验证边界

- 报警/配方/表格的 Excel（`libxl.dll`）导入导出入口；
- com-x:8000 / dserver-x:24763 应用层协议；
- 编译记录文本读取；
- 高 DPI / Ribbon 折叠 / 非中文界面下的坐标（需重采样）；
- 机型/系列/方向的非默认选择；已有元件的移动/多选/对齐；未保存工程的新建确认分支。

## 更新协议

本 Skill 与 `EASYBUILDERX-UIA-AGENT-GUIDE.md` 是配套活文档。本会话内每获得一条新知识：

1. 写入 Guide 对应小节 + 追加 §10 更新记录，递增版本号；
2. 若涉及新操作路径，新增/修改 `ebx_mcp_server.py` 工具并跑 `ebx-mcp-smoke-test.py`；
3. 同步本 Skill 的配方/坑清单；
4. 同步 `EBX-MCP-CONTROL-PLAN.md` 与 `RESEARCH-LEDGER.md`；
5. 未实测内容只能写进"未验证边界"。

## 文件位置

- 项目根：本文件所在目录（`easybuilder-x-mcp/`，与 MCP 同仓，打包以目录根为准）
- **本 Skill 源稿**：`SKILL.md`（唯一事实源；部署副本放 `%USERPROFILE%\.qoder-cn\skills\easybuilder-x-mcp\SKILL.md`，Windows 上也可换成对应平台的 skills 目录）
- **部署/校验**：`tools/sync_skill.py`（改完源稿跑一次）；`tools/sync_skill.py --check` 只校验 sha256，不一致返回 1
- 手册：`references/EASYBUILDERX-UIA-AGENT-GUIDE.md`
- 方案：`references/EBX-MCP-CONTROL-PLAN.md` ｜ 台账：`references/RESEARCH-LEDGER.md`
- 服务：`ebx_mcp_server.py` ｜ 启动：`start-ebx-mcp.bat` ｜ 自检：`ebx-mcp-smoke-test.py` ｜ 单次调用：`tools/mcp_call_once.py`
- 页面 JSON：`examples/Alarm_Trend.screen.json` ｜ 导入器：`tools/ebx_screen_importer.py`
- 交付说明：`examples/IMPORT_README.md`（导入前提/排错）｜ `examples/EXPORT_IMPORT_RUNBOOK.md`（导出与导入全过程）
- 运行产物：脚本默认写 `out/`，工程放 `work/`（两者都不入仓库）

## 打包清单

打包整个工具集时（项目根 zip）：

- **必带**：`SKILL.md`、`README.md`、`ebx_mcp_server.py`、`start-ebx-mcp.bat`、`ebx-mcp-smoke-test.py`、`requirements.txt`、`tools/`（去掉 `__pycache__`）、`examples/` 下的 `Alarm_Trend.screen.json` + `IMPORT_README.md` + `EXPORT_IMPORT_RUNBOOK.md`、`references/` 三份知识文档（Guide / PLAN / Ledger）。
- **不带**：`__pycache__`、`out/`、`work/`（工程与 `.ebxobj` 体积大且可能含现场数据）、调试截图与日志、任何本机绝对路径配置。
- 打包前先跑 `python tools/validate_screen_json.py examples/Alarm_Trend.screen.json` 与 `python tools/sync_skill.py --check`。
