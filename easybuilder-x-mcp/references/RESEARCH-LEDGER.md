# EasyBuilder X 情报台账（已核实事实 + 来源）

作者：hoverwu ｜ 版本：0.3.0 ｜ 建立：2026-11-06 ｜ 更新：2026-11-06 ｜ 采集方式：官方站点直取 + 官方手册 PDF 解析 + 官方安装包实测元数据 + 本机 UIA 实测

本文件只记录**已经核实**的事实。任何未实测的推断一律写在末尾并标注"未验证"。

## 1. 产品与版本

| 项 | 值 | 来源 |
| --- | --- | --- |
| 软件名 | EasyBuilder X（威纶通/Weintek 新一代 HMI 图控编辑软件） | 官网产品页 `https://www.weinview.cn/EasyBuilderX` |
| 发布公告 | 2026-09-20（威纶通官网产品动态）/ 2026-09-15（Weintek 台湾新闻中心 Vol.68） | `https://www.weinview.cn/cpdt/3406.html`、`https://www.weintek.com/zh-TW/About/NewsDetail/ProductNews-Vol.68` |
| 最新版本 | **V1.01.376**，发布日期 2026-10-14 | 官网下载中心条目 `EasyBuilder-X-V1.01.376_20261014` |
| 官方直链 | `https://download.weinview.cn/Private/ProductFiles/Software/EBX/EBX-1.01.376-weinview.zip` | 下载中心 `https://www.weinview.cn/rj` |
| 下载校验 | CDN 有 **Referer ACL**：不带 `Referer: https://www.weinview.cn/` 直接 403（`X-Tengine-Error: denied by Referer ACL`） | 本机 curl 实测 |
| 包大小 | 284,311,195 B（与 CDN `Content-Length` 逐字节一致） | 本机实测 |
| zip SHA256 | `0b35da896b5fef864aefabbd28065f809c4c6788e69cfa538cd00dcefd7ebc1a` | 本机 certutil（官方未发布校验值，此值作为本机基线） |
| 包内容 | 单一 `setup.exe`（284,300,104 B，PE32 i386 GUI） | 本机解包 |
| setup.exe 元数据 | FileDescription/ProductName = `Weintek EasyBuilder X 1.01.376s`，FileVersion `1.01.376`，CompanyName `http://www.weintek.com` | `Get-Item .VersionInfo` |
| 打包器 | ~~WiX/Burn~~ **实为 Inno Setup**：安装目录含 `unins000.exe`，向导窗口类 `TWizardForm`（2026-11-06 安装实测修正） | 本机静态串特征 + 实际安装过程 |
| 官方手册 | 《EasyBuilder X 软件使用手冊》v1.01，188 页 PDF，`https://www.weinview.cn/storage/file/20260916/1789531034133550.pdf`（下载中心"操作手册"条目 id=3147） | 官网 `https://www.weinview.cn/czsc` |
| 版本更新说明 | `EasyBuilder-X-1.01-ReleaseNotes-chs.pdf`（7 页） | 官网下载中心 |
| 与 EBPro 并存 | 官网软件导航同时列 EasyBuilder X / EasyBuilder Pro / Weincloud；EBPro 最新 V6.10.02.421（2026-08-27） | 下载中心 + 产品页导航 |
| 适用机型 | cMT X 系列（Weintek 新闻中心表述"支援 cMT X 系列"）；手册第 12.5 章为「HMI 机型」，可按系列切换 | 新闻中心 + 手册 |

## 2. 界面结构（来自官方手册 + 官网截图）

Ribbon 选项卡：**文件 / 常用 / 工程文件 / 元件 / 资料/历史 / IIoT / 检视 / 工具**。

- 元件分页功能区面板可见：绘图（线/曲线/折线/圆弧/圆/扇形/矩形/星形/条形/文字 A）、Switch/Button（指示灯、开关、按钮、项目选单、滑动开关）、Input（数值、文本）、Illustration（棒图、嵌入窗口、2D 条码、PDF 检视器）、自定义。
- 设计工作区面板：**元件**（当前项目所有组件，可加分层）、**自定义模板**（可加分组）、**变量**（数值变量 / 算术变量）、**属性**（所选物件的属性/事件/方法）、**记录**（设计记录 + 编译记录，上限 1000 笔，双击错误可跳转）。
- 属性直接编辑：侧边面板改参数，不弹对话框（对自动化友好）。
- 智慧批次修改：多选元件一次改共用属性/事件/方法。
- 缩放快捷键手册只给出一条明确可用：`Ctrl + 0` 回到 100%。

## 3. 数据/工程模型（手册要点，自动化生成时的语义层）

- 面向对象：每个元素是「物件」，由**属性 / 事件 / 方法**定义；支持**自定义模板**（自定义属性/方法/事件、实例概念、集中维护同步更新、可部署到外部环境复用）。
- 变量体系：**数值变量**（背景/全域层级，等同全局变量）与**算术变量**（作用域随算式引用对象动态收敛）。作用域三层由宽到窄：**背景 → 前端(Viewer，含 HMI 本地屏与 cMT Remote) → 特定画面**。规则：引用者不得依赖存活时间比自己短的源；跨画面一律经背景数值变量中转；违反则**编译期报错**。
- 数据类型：IEC 风格（BOOL/USINT/UINT/UDINT/ULINT/STRING/DateTime/IPv4…），手册明确 BYTE/WORD/DWORD/LWORD 可按位存取；支持结构体成员逐个绑定、Bool 属性用条件表达式绑定。
- 命名空间（5.1）+ 数据类型库（5.2）+ 变量库（5.3）+ 设备列表（4.1，含设备属性/事件/方法）+ 服务器列表（4.2）。
- 字符串库支持 `.csv` 导入/导出（8.2.3）——**这是唯一已证实的结构化批量导入/导出通道**。
- 宏指令（16 章）：`macro_command main() ... end macro_command`，读写变量走 URI 式路径：
  `GetVariable(value, "Variable://Namespace/Variable")` / `SetVariable(...)`；有子函数、内置函数列表、用户自定义函数库（工程内 `*.ebxprj` 级 vs 外部环境 External 级两种来源）。
- 其它子系统：条件（9）、UAC 用户权限（10）、资料取样/趋势图/资料显示（11）、工程文件设置（12：一般/远端/安全/HMI 机型）、报警（13）、配方（14）、Weincloud + EasyAccess 2.0 + 仪表板（15）、图片库（17）、cMT Remote（18）、**Modbus TCP/IP 服务器（19，HMI 侧把变量映射成 Modbus 寄存器，含地址浏览器视图）**、审计追踪（20）、系统元件（21：一般属性/网络/背光灯）、变量作用域（22）。

## 4. 官方命令行面（关键负面结论）

- 手册 20.5 节：`ebxtool.exe` **只做审计追踪 CSV 完整性校验**，命令面仅 `--version` 与 `audit verify "<file.csv>"`；退出码 0=完整 / 1=被改 / 2=路径或格式或输入不对 / 3=工具内部错误。手册要求从 PowerShell 或 CMD 运行，明确"不支持鼠标双击执行"。
- **没有**任何编译、下载、新建工程、批量改属性的 CLI；**没有** COM/OLE 自动化接口、**没有** SDK/插件/二次开发接口的记载（手册全文 `脚本`/`API`/`插件`/`二次开发` 命中数为 0）。
- 结论：EBX 的自动化入口只剩 ①UIA 界面驱动 ②工程文件本体（`.ebxprj`）③字符串表 CSV 导入 ④运行时侧（Modbus TCP Server / cMT Remote / 离线模拟器）。

## 5. 工程文件格式

- 可编辑工程 = **`.ebxprj`**；编译产物 = **`.ebxobj`**；`文件 » 反编译` 可把 `.ebxobj` 还原成可编辑 `.ebxprj` 并在 EBX 中打开。
- 官网"为什么选择 EBX"明确：**支持以旧版 EasyBuilder X 开启新版项目文件**（版本前向兼容策略）。
- `.ebxprj` 内部是单文件、ZIP 还是目录：**未验证**（待安装后实测）。

## 6. 本机接入条件（实测）

- Windows-MCP（`windows_mcp` v0.8.8，uv tool 装在 `%USERPROFILE%\AppData\Roaming\uv\tools\windows-mcp`，HTTP `http://localhost:18000/mcp`，手动启动 `%USERPROFILE%\.windows-mcp\start-server.cmd`）：**本会话端口 18000 未监听**，且本会话 MCP 目录快照里没有 Windows-MCP ⇒ 本会话调不到，需新会话或走 PowerShell/Python UIA 通路。
- 可复用资产：项目虚拟环境（Python 3.13，已装 `uiautomation 2.0.29` + `fastmcp 3.4.6` + `pywin32` + `pillow`，实测 import 通过）。
- 方法论资产：另一个 Omron Sysmac Studio UIA 项目沉淀的同类手册（UIPI/IL、DPI、弹窗独立 HWND、cp936、MSYS 斜杠参数等 12 类坑全部实测过，不在本仓库）。
- 官方站点/CDN 域名：`www.weinview.cn`、`download.weinview.cn`（下载用途，无凭据、无本机数据外发）。

## 7. 未验证清单（必须实测后才能进方案正文）

1. EBX 的 UI 技术栈（Qt / .NET WPF / Win32+MFC / Electron / WebView2）→ 决定 UIA 树质量与坐标策略。
2. EBX 进程的完整性级别：是否需要管理员运行 → 决定 Medium-IL 的 MCP 能否看到它的 UIA 树（Sysmac 就是因为 High IL 才卡住）。
3. `.ebxprj` 的真实形态与可解析性（ZIP? 目录? 二进制?）→ 决定"文件级生成"这条路能不能走。
4. 离线模拟器是独立进程还是内嵌、监听哪些端口 → 决定运行时验证通路。
5. Ribbon/侧边面板的 UIA 暴露粒度（有没有 AutomationId、画布是否只暴露成一个 Pane）。
6. 是否支持导入 EBPro（`.emtp`/`.cmtp`）工程——手册未见记载，需在 UI 里确认。
7. `ebxtool.exe` 在安装目录的实际位置与是否还有未写进手册的子命令（跑 `--help` 看）。

## 8. 实测回填（2026-11-06，安装后全部验证）

安装落点：`%ProgramFiles%\EasyBuilderX`（注意无空格）；版本 `V1.01.376s` / build `2026.10.14`（`Version.xml`）；edition `WEINVIEW`（`edition`，UTF-16LE）。安装器实为 **Inno Setup**（`unins000.exe` + `TWizardForm`），不是 WiX/Burn。

### 8.1 第 7 节七项未决事实的结论

| # | 问题 | 实测结论 |
| --- | --- | --- |
| 1 | UI 技术栈 | **Qt5 + QtitanRibbon/QtitanDocking**。目录内 `Qt5Core/Gui/Widgets/Quick/Qml.dll` + `QtitanRibbon5.dll` + `QtitanDocking3.dll`；主窗 UIA 类名 `Qt5QWindowIcon` |
| 2 | 进程完整性级别 | 全部 **asInvoker（Medium IL）**：`EasyBuilderX.exe` / `com-x.exe` / `dserver-x.exe` / `cMTInspector.exe` 的 manifest 均为 asInvoker ⇒ 普通权限 UIA 可直接操作，无需提权服务 |
| 3 | `.ebxprj` 真实形态 | **单文件自定义二进制容器，payload 加密/高熵**：魔数 `18 52 74 00`，随后 `03 00 02 00 00 00 78 01`；全文件熵 7.993 bit/byte、256 种字节全覆盖、`strings` 零命中；非 ZIP/tar/7z/gzip/xz/zstd。⇒ **不可离线生成或直接打补丁**（L2 文件级方案关闭） |
| 4 | 离线模拟器形态 | 由「工程文件 » 离线模拟」拉起三进程：**cMTRemote.exe**（显示端，窗名 `cMT Remote ( Offline Simulation )`）+ **com-x.exe**（监听 `0.0.0.0:8000`）+ **dserver-x.exe**（监听 `0.0.0.0:24763`）；另开「**诊断器**」（cMTInspector 窗口）实时显示对象树 `Global Objects → Screen → 画面 → 数值` 与 Watch 变量表。两端口不响应 HTTP（裸 TCP 连接无数据，协议未逆） |
| 5 | Ribbon/侧栏 UIA 暴露粒度 | **两极分化**：Ribbon 带（Qtitan 自绘）只暴露 139px 的 `MenuBarControl` + 唯一项 "Minimize the Ribbon"，**8 个页签与按钮全部不可见**；而工作区面板（检视/属性/变量/记录页签、属性字段、状态栏、画布 Tab）Name+矩形完整可读，AutomationId 全为空。文件对话框是原生 Win32（`#32770`/Shell），AutomationId 齐全（文件名 `1001`、保存 `1`、取消 `2`、文件类型 `1136`） |
| 6 | EBPro 工程导入 | **不支持**。打开对话框文件类型仅三项：`工程文件 (*.ebxprj; *.ebxobj)` / `Binary Project (*.ebxprj)` / `Object Project (*.ebxobj)` |
| 7 | ebxtool 实际子命令 | `1.0.0`，`--version` 返回 `1.0.0`；`--help` 只有 `audit -- verify the check code of an Audit Trail backup CSV`；裸执行打印用法并退出码 2。**无隐藏子命令**（与手册一致） |

### 8.2 新增事实（安装后实测）

- 主程序 `EasyBuilderX.exe` 44.7 MB；辅助 exe：`cMTInspector.exe` 63 MB（诊断器）、`cMTRemote.exe` 89 MB、`com-x.exe` 10 MB、`dserver-x.exe` 17.7 MB、`DisplaySetting.exe`。
- 自带 `libxl.dll`（Excel 读写引擎）⇒ 报警/配方/表格类可能存在 Excel 导入导出（未逐个验证）；`ebpro-project`（29 KB 文本）、`device-type.json`（12 KB 机型库，机器可读）、`Config.xml`（18 KB）。
- 用户配置：`%APPDATA%\Weintek\EasyBuilder X\{config.ini,ui-state.ini,Macro\}`；config.ini 仅语言项，未存工程路径。
- 新建工程默认机型 cMT3075XH / 水平 / 1024x600；保存对话框默认目录为安装目录（`driver/firmware/...` 可见）。
- 编译产出 `.ebxobj` 与被选中工程**同名同目录**（本次 79.4 MB，含全部固件与资源）；编译同时 `.ebxprj` 自动回写（25,416 → 31,751 B）。
- `uiautomation 2.0.29` 在本机的三个 API 坑（实测）：① 没有 `IsVisible` 属性；② `IsOffscreen` 是**属性**不是方法；③ `EnumProcessModulesEx` 需从 `psapi.dll` 取且必须给 `argtypes`（否则 64 位指针截断报 OverflowError）。
- MCP 服务：`uiautomation-mcp` 经 `serve-http.py` 跑成 `http://127.0.0.1:8786/mcp`（普通权限即可），自检 9 工具全通，`list_windows` 可见 EBX，`inspect_element_tree` 前 6 层 93 节点。

### 8.3 端到端已跑通的控制原语（普通权限 UIA，全部实测）

1. 启动：`Start-Process EasyBuilderX.exe` → 8 秒内主窗就绪（PID 19812，Responding=True）。
2. 欢迎页：UIA 读机型卡片/系列下拉/"创建"按钮；坐标点在"创建"（screen 偏移 = 截图坐标 + 窗原点 79,34）→ 工程创建成功。
3. 保存：文件页签 » 另存为 → 原生对话框 `EditControl A=1001` 用 ValuePattern 写全路径 → `ButtonControl A=1` Invoke → `.ebxprj` 落盘。
4. 放元件：元件页签 » 输入组按钮（坐标）→ 画布单击（坐标）→ 数值元件生成（100x40 @ 475,137），属性面板立即联动（元件类型/名称/数值/数据格式 LREAL 等全部可读）。
5. 编译：工程文件页签 » 编译（坐标）→ 无错误弹窗，`.ebxobj` 与 `.ebxprj` 同步落盘。
6. 运行验证：工程文件页签 » 离线模拟 → cMTRemote + com-x(8000) + dserver-x(24763) 三进程 + 诊断器对象树。

### 8.4 仍未验证（不进方案正文，作为下一轮）

- `com-x:8000` 与 `dserver-x:24763` 的应用层协议（非 HTTP，需逆向或抓包）。
- 「记录」面板（Qt dock 折叠条双击不展开）内编译记录的可读性；目前用「文件产物时间戳 + 有无错误弹窗」间接判断编译结果。
- 报警/配方/表格的 Excel（libxl）导入导出入口。
- `device-type.json` / `ebpro-project` 的完整语义。

## 9. 专用 MCP 与知识固化（2026-11-06 追加，全部实测）

### 9.1 专用服务器

- `ebx_mcp_server.py`（FastMCP HTTP，`127.0.0.1:8788`，普通权限），`start-ebx-mcp.bat` 启动，`ebx-mcp-smoke-test.py` 自检；24 个 `ebx_*` 领域工具（v0.2.0，初版 18）。
- 工具清单：status / launch / windows / tree / find / click_name / click_xy / ribbon / ribbon_map / screenshot / keys / save_as / open / new_project / compile / offline_simulate / stop_simulation / artifacts / screen_list / screen_open / screen_elements / uia_dump / import_screen_json / import_status。
- 与通用 `uiautomation-mcp`（8786，9 工具）并存，专用版把坐标地图与对话框 ID 固化，减少每次探索。

### 9.2 工具实测结果

| 工具 | 结果 |
| --- | --- |
| `ebx_status` | 命中主窗 PID 19812；窗口矩形 `96,18 1722x919`（本轮与上一轮 `79,34` 不同 ⇒ 原点会漂移，必须现读） |
| `ebx_save_as` | `ValuePattern` 写路径 + `Button A=1`；`.ebxprj` 31,751 B 落盘；标题即时切换；记录 `last_project` |
| `ebx_open` | 文件后台 » 打开 » 原生对话框；标题按 basename 等待切换，实测通过 |
| `ebx_compile` | 约 5.7 s；中途抓到半成品 14,141,440 B，最终 79,368,0xx B（观测到 …008/013/016）⇒ 必须等大小/mtime 连续稳定；产物有几字节级差异，禁止精确大小判等 |
| `ebx_offline_simulate` | 4.6 s 拉起 cMTRemote / com-x(8000) / dserver-x(24763)；模拟器窗口 `cMT Remote ( Offline Simulation )` 类 `Qt5QWindowOwnDCIcon`，另有中文名窗口 类 `Qt5QWindowIcon`（诊断器）；`include_related` 可列模拟器窗口 |
| `ebx_stop_simulation` | `taskkill cMTRemote` 后 `leftovers=[]` |

### 9.3 文件后台坐标（窗口内）

新建 42,99 ｜ 打开 42,153 ｜ 保存 42,205 ｜ 另存为 42,253 ｜ 关闭 42,303 ｜ 反编译 42,355 ｜ 语言 42,408 ｜ 偏好设置 42,460 ｜ 关于 42,511 ｜ 退出 525,572。

### 9.4 新坑

- Git Bash 终端按 cp936 解码，MCP 返回的中文 JSON 在终端显示为乱码；数据本身是正确 Unicode（看文件/Python 对象，别以终端显示判断）。
- 文件后台打开时点 Ribbon 页签会点在遮罩上 ⇒ 先 `Esc` 关后台（专用工具已内置）。
- 模拟器三段进程级联启动，`cMTRemote` 出现后需再等约 2 s 才有 `com-x/dserver-x` 与窗口。

### 9.5 页面 JSON 导入/导出（2026-11-06 核实）

- **官方无页面级 JSON**：文件菜单仅新建/打开/保存/另存为/关闭/反编译/语言/偏好设置/关于；打开对话框仅 `*.ebxprj`/`*.ebxobj`；反编译只做 `.ebxobj → .ebxprj`。
- 官方全部导入导出：字符串表 `.csv/.xls/.xlsx`（运行时 `.txt`）、宏指令 `.ebm`、审计 CSV、图片。手册中 JSON 仅出现在授权/证书/设备错误码，与画面无关。
- 替代路径：JSON→EBX 用 UIA 驱动（已验证放元件/改属性原语）；EBX→JSON 用检视面板枚举画面 + 元件面板枚举元件 + 属性面板/状态栏回读（适合清单/审计，不是备份）；自定义模板仍是加密工程内对象，不能导出 JSON。

### 9.6 固化产物

- 知识手册：`EASYBUILDERX-UIA-AGENT-GUIDE.md`（v0.1.5，活文档，含更新记录与更新协议）。
- 方案：`EBX-MCP-CONTROL-PLAN.md`（v1.4.0，含 §11.1 MCP v0.2.0 页面级通道）。
- Skill：源稿 `SKILL.md`（与 MCP 同目录，作者 hoverwu，v0.3.0，24 工具 + UIA 树模型）；部署副本 `%USERPROFILE%\.qoder-cn\skills\easybuilder-x-mcp\SKILL.md`，用 `tools\sync_skill.py` 同步、`--check` 校验。
- 更新协议：新知识 → 手册对应小节 + 更新记录 → 必要时加 MCP 工具并自检 → 同步 Skill / 方案 / 本台账；未实测只进"未验证边界"。

## 10. 按钮导航 / 切换画面 / 启动页（2026-11-07 实测）

| 事实 | 证据 |
| --- | --- |
| 按钮「任务」行「新增...」(1355,433) 弹出任务菜单，含 设置数值/呼叫元件方法/切换画面/弹出窗口/关闭弹出窗口/键盘输入/导入导出字符串表/新增 if/while/等待/延迟 | out/taskdlg2.png |
| 「切换画面」菜单项 (1434,504) → 358×267 对话框（781,392）：类型、画面下拉(885,479..1117,505)、动画、确定(1022,608)/取消 | out/switch_menu.png、switch_combo.png |
| 画面下拉列表为 Qt5QWindowPopupDropShadowSaveBits，条目不可 UIA 枚举；按 popup 行高几何点选 | out/switch_combo.png、switch_picked.png |
| 配置成功后任务行显示「元件方法: 切换画面 "参数设定"」 | out/switch_done.png |
| 按钮「标签」组（面板底部）：文本/字体/字体尺寸(16)/粗体/斜体/下划线/颜色/对齐；文本 ComboBox 可粘贴中文 | out/props_bottom.png、nav_主监控.png |
| 属性面板停在底部时 pane_kind() 读不到元件类型 → 成功的放置被误判 place_failed，留下重叠未命名按钮 | nav_build 日志 + 元件列表截图 |
| 元件列表行可作为重叠元件的选择入口，选中后 Delete 可删 | nav_clean/nav_fix3 日志 |
| 画面属性行：名称 345 / 注释 379 / 底层 413；画面右键菜单无「设为起始画面」；工程设置四页也无该选项 | out/projset.png、probe_screen_events.png、start_menu.png |
| 启动页 = 画面树最先创建的画面（报警与趋势），树行拖动不换序 | sim_start.png、sim_tour_boot.png、reorder.png |
| 删除被导航任务引用的画面弹「所选窗口正被其他功能使用…是否仍要删除」；重建会换内部 ID，导航任务可能失效 → 先备份 .ebxprj | out/screen_del1.png |
| 模拟器被 EBX 遮挡后 SetForegroundWindow/TOPMOST 均可能失效，截图拍到 EBX；可靠做法是重启模拟并在 16s 内操作 | sim_page_param.png、list_sim.py 输出 |
| 模拟器客户区含渐变边框，页面等比缩放居中；用近白包围盒换算 canvas→客户区 | sim_pw.py 输出 page box、sim_tour_*.png |

### 10.1 本次交付（管道加热 HMI）

- 工程：`work/PipeHeating_HMI.ebxprj`（备份 `work/PipeHeating_HMI.backup_before_reorder.ebxprj`），编译产物 `work/PipeHeating_HMI.ebxobj`（81,500,378 B，2026-11-07 17:28）。
- 画面：主监控 29 / 参数设定 18 / 手动维护 21 / 报警与趋势 37 元件，全部绑定 PLC 全局变量；每页右下 3 个导航键（共 12 个）。
- 模拟验证：启动页 报警与趋势 → 主监控 → 参数设定 → 手动维护 → 报警与趋势 逐页点击通过（out/sim_tour_*.png）。

## 11. 页面 JSON 迁移实测（2026-11-07）

| 事实 | 证据 |
| --- | --- |
| `ebx-screen/1.0` 导出：`out/Alarm_Trend.screen.json`（20,274 B，UTF-8 无 BOM），40 元件 / 38 标签清单 / 17 实际使用 / `import.native_json_support=false` | 文件本身；`tools/export_screen_json.py` |
| 导入器从 JSON 重建整页：40/40 元件成功（20 文本 / 9 灯 / 8 数值 / 3 按钮） | 作业日志 elev_out.txt「[ok] 已重建 40 个元件到画面 报警与趋势_导入验证」 |
| 标签绑定 17/17 ok（doAlarm、xTripLatched、xOverTemp、diOverTemp、xFlowBad、xPermit、rTempMeas、rTempIn、rFlow、rPowerCmd、ai*Raw、diHeaterReady、diFlowOk、doHeaterEnable） | 日志逐条「[bind] … : ok」 |
| 3 个导航任务 ok（主监控/参数设定/手动维护）且经重开对话框复核；3 个按钮文字 ok | 日志「[task] … : ok」「[label] … : ok」；out/now3.png |
| 重建画面布局与原页一致；验证后删除该画面并保存，工程仍为 4 页 | out/now3.png；del_screen.py 输出 after 列表 |
| 主窗 HWND_TOPMOST 会让后续对话框/弹层/右键菜单生成在其下方（UIA 可见、屏幕不可见、点击落空） | out/fore.png、probe_topmost 日志 |
| 切换画面下拉必须先点对话框标题栏激活，弹层才渲染；否则点击/键盘/SelectionItemPattern 全无效 | out/tm1.png、probe_switchdlg* 日志 |
| 「新增...」任务菜单异步绘制，需 1.5 s 轮询；任务行自绘不可读，落盘须重开对话框读「画面」ValuePattern | task_once 日志、out/task_once.png |
| 完整重建耗时 ≈29 min（40 元件，每件 30~60 s） | 19:49→20:18 作业日志 |

### 11.1 交付包

- `out/Alarm_Trend.screen.json`（数据）、`out/ebx_screen_importer.py`（便携导入器）、`out/IMPORT_README.md`（前提/步骤/排错）、`out/EXPORT_IMPORT_RUNBOOK.md`（导出与导入全过程）。
- 源工具：`tools/export_screen_json.py`、`tools/ebx_screen_importer.py`、`tools/del_screen.py`、`tools/open_target.py`、`tools/mcp_call_once.py`。

## 12. MCP v0.2.0 / UIA 树模型实测（2026-11-07）

| 事实 | 证据 |
| --- | --- |
| 服务端 24 工具全部注册 | `ebx-mcp-smoke-test.py` 输出 `tools(24): ...` |
| 画面树 = 左区第一棵 `TreeControl`，4 行（报警与趋势 240 / 主监控 268 / 参数设定 296 / 手动维护 324，x=26 w=222 h=28） | `ebx_screen_list` 返回 |
| 当前画面只能读属性面板「名称」；文档页签是自绘，`TabItemControl` 恒空 | `current_screen="主监控"`；out/dump_left.py 输出无 TabItem |
| 元件 dock **没有 TabControl**，是左区第二棵 `TreeControl`（x=26 y=420 w=208 h=28） | `ebx_screen_elements` 返回 7 行 |
| 属性面板嵌套 depth >18，16 层遍历读不到值；`_prop_value` 改 30 层 + 控件引用取值后恢复 | 修复前后 `ebx_screen_open` 由 `ok=false` 变为 `{"ok":true,"opened":"主监控","attempt":0}` |
| 对话框三种宿主：子 `WindowControl` / 顶层 `#32770` / 无标题顶层 `Qt5QWindowIcon`；要跳过 1×1 `Qt5QWindowToolSaveBits*` | `_find_dialog` / `_find_visible_dialog` 实现；out/mcp_state4.png |
| `ebx_import_screen_json` 后台通道可用：`limit=1,no_bind,no_nav,no_save` → `finished=true, done=1/40, errors=[]` | out/import_20261107_204815.log |
| 试跑临时画面删除后工程仍 4 页，保存成功 | del_screen 输出 `[after] ['报警与趋势','主监控','参数设定','手动维护']` |
| 本机 `NO_PROXY` 含 `[::1]` → httpx `InvalidURL: Invalid port: ':1]'`，客户端须先清空 | 实测报错与修复后 `CLIENT OK` |
| venv `python.exe` 启动服务出现父子两个同名进程，属正常 | `Get-CimInstance Win32_Process` 显示 ParentProcessId 指向同名进程 |
