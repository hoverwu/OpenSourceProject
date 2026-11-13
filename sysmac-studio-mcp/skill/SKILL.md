---
name: sysmac-studio-control
version: 0.11.0
description: 非官方 Sysmac Studio（欧姆龙 PLC 编程软件）UIA 操控 Skill。用 Windows UI Automation 读取该软件的控件树，并执行识别实例、新建工程、按路径导航工程树、读出树节点名与每种节点的右键菜单、按树路径打开各类编辑器并测绘其内部控件（含展开后的 POU 变量表逐格读取）、批量复制/粘贴程序与功能块、挂接 .slr 库、在已有库 FB 上按轴开关加新功能（默认 OFF、不破坏存量调用）并重建 .slr、离线把新库接口对齐到目标所依据的已编译库（形参名漂移改名 + Id 归一化校验）、删旧引用行重加同路径强制重载库缓存、把程序分配到任务、编辑变量表、建数据类型命名空间、逐个创建运动控制轴并按参数写入轴设置（含轴↔EtherCAT 从站绑定与 PDO 过程数据映射）、在 EtherCAT 拓扑里按计划表逐个"选中端口 → 搜型号 → 右击插入(I)"复刻整套从站组态（含 ESI 描述文件安装、成对插入 Main+Sub、倒序搭链、最后统一改节点号、设备名写入、以归档逐条比对验收）、编译并全量读取错误列表、以文件 sha256 为判据真正落盘保存（Ctrl+S 会被残留弹层吃掉，走 UIA 菜单）、导入/另存为/导出 .smc2 并做 digest 校验。当用户要求自动化操作 Sysmac Studio、批量搬运或导出 Sysmac 工程、读取其窗口与控件结构、查某类工程树节点或编辑器页能做什么、照抄参数重建轴组态或 EtherCAT 从站拓扑、给已封装的库功能块加功能再换进目标工程、或让 Agent 在 Sysmac Studio 里完成组态与编程操作时使用。
metadata:
  author: hoverwu
  unofficial: true
  tested_against: 'Sysmac Studio V1.68 (1.68.0.64010) 64bit / Windows 11 / 125% DPI'
  emoji: '🏭'
  requires:
    python: '>=3.10'
    pip: ['uiautomation>=2.0', 'pillow']
---

# Sysmac Studio 操控 Skill（非官方）

作者：hoverwu ｜ 版本：0.11.0 ｜ 建立：2026-10-30 ｜ 本版更新：2026-11-13（在已有库 FB 上按轴开关加功能 → 重建 .slr → 离线对齐接口 → 换引用强制重载库缓存 → 重编译 → 菜单保存，端到端实测；新增 §78~§80 坑、offline-surgery §10 离线补丁配方、library-and-tasks §7 端到端配方；ss_libref.py 0.2.0 增 replace/warn 模式）

## 0. 非官方声明（先读）

- 本 Skill **不是 OMRON 官方产物**，与 OMRON 无任何隶属或背书关系；不包含、不调用任何 OMRON 私有 SDK。
- OMRON **没有公开** Sysmac Studio 的脚本 / COM / API 接口。本 Skill 的全部能力来自对软件界面（WPF + WinForms 宿主 + UI Automation）的**外部逆向观察**，因此：
  - 控件 ID、名称、层级都可能随版本变化，**升级 Sysmac Studio 后必须重新校验**（见 [references/extending.md](references/extending.md)）。
  - 属于"模拟人操作界面"的自动化，**不具备软件内部语义**：它不知道你的程序对不对，只知道控件有没有被点下去。
- 本 Skill 里的结论都标注了"实测"或"未验证"。**未验证的条目不要当事实用**，先按 [references/extending.md](references/extending.md) 自己测一遍。
- 请自行确认在当地对商业软件做界面自动化是否符合其最终用户许可协议（EULA）；本 Skill 不代替该判断。

## 1. 适用与局限

**实测基线**：Sysmac Studio V1.68 64 位（`1.68.0.64010`），Windows 11，125% 缩放。32 位版本（如 1.30）控件层级不同，未验证。

| 能做（实测） | 不能做（实测确认不行） |
| --- | --- |
| 识别同机多个实例、读标题/工程名/控制器名/在线状态 | 用消息/`PostMessage` 打开页面（`TVM_*` 能选中、能配合真实 `VK_RIGHT` 展开，但打开编辑器要**真实**单击+回车或双击） |
| 新建工程（填工程名/作者/注释/设备型号/版本） | `配置和设置` 分支跨工程复制（菜单可点但剪贴板不变） |
| 工程树：`TVM_SELECTITEM` 消息选中到**任意深度**（不需要前台，最小化/锁屏也可用，`TVIS_SELECTED` 实测会一起给）；`treelabels` 读全部节点文字；按可见行点击（行高 26px + caret/选中态回读校验）定位 | 双击**已选中**的树行（会变行内重命名）；`TVM_EXPAND` 只对根节点有效（深层要 caret + 真实 `VK_RIGHT`，见 project-tree.md §3.2） |
| `编辑>复制/粘贴/删除` 搬运 POU、批量多选复制 | 从配置节点复制——它的右键菜单里**根本没有** `复制(C)`（只有 `编辑(E)` 等；`控制器设置`/`运动控制设置`/`主机连接设置`/`数据`/`任务`/两个根**连菜单都没有**）。全量菜单表见 [references/tree-node-menus.md](references/tree-node-menus.md) |
| 挂 `.slr` 库引用（`工程>库>显示索引` → 库索引 → `+`） | 把程序/变量**拖**到任务或表格上（合成拖拽不产生拖动影像，实际不生效） |
| **在已有库 FB 上按轴开关加功能（默认 OFF）→ 创建库 → 离线对齐接口 → 换引用强制重载 → 重编译到 0 错 → 菜单保存**（`ss_libref.py open/replace/warn` + `ss_build.py` + `ss_save.py --menu`，端到端见 [library-and-tasks.md §7](references/library-and-tasks.md)） | 改磁盘 `.slr` 后指望 Sysmac 自动重载或点刷新(↻)键重读（**刷新键恒灰**，唯一可行是删旧引用行+重加同路径，[pitfalls §79](references/pitfalls.md)）；从仍开着库源的 Sysmac 实例保存/创建库（它持**陈旧内存副本**，会把磁盘离线补丁打回原形；被开着的 `.smc2`/`.slr` 还**写锁定**，`os.replace` 报 WinError 5，[§80](references/pitfalls.md)） |
| 任务分配（`任务设置` → `程序分配设置` 逐行 `+` + 组合框选程序） | 删除变量表 / 数据类型里"名为空"的行（多种写法全失败，且已写进 `.smc2`） |
| 变量表单元格打字 / 数据类型表右键菜单 | 把设备、EtherCAT、安全组态**用剪贴板**搬到另一个工程（5 条跨工程路径全失败，见 [project-tree.md §7](references/project-tree.md)）——改用文件移植，见 [offline-surgery.md](references/offline-surgery.md) |
| **在文件层面移植实体子树**（EtherCAT、NX 总线/安全 CPU、数据类型页），改完能被软件打开并编译到 0 错误 | 改**加密 `PouBody`** 的文本（一个字节就废），只能改调用点 |
| 建数据类型命名空间（子空间），可消掉 `数据名称中含有无效值。` | 梯形图/功能块画布内部元件的读写（GoWPF 画布不暴露子元素） |
| **导出 `.smc2`**：中文文件名 + 覆盖确认全自动，可复现 | 读**命名空间树**的行文字（行上没有 Name，只能按几何点）；数据类型表的行文字**可读**（`DataItem` 的格子里有 `Text`，实测 `st_Balluff`） |
| **编译并全量读取错误列表**（`N 错误/M 警告` + 每行说明/程序/位置，UTF-8 落盘） | 锁屏/无前台会话时的坐标鼠标、键盘注入与截图 |
| `文件>导入` / 另存为 / `.smc2` 字节级校验、截图（需真实桌面会话） | 弹窗未关时的菜单点击（有残留 `#32770` 时全部失效，见 pitfalls §23） |
| **全量测绘主窗口骨架**（`ss_uimap.py panels`：菜单栏 / 6 条工具栏逐按钮 / 4 个停靠容器 / 状态栏 / 编译面板 / 工具箱，带 id、HelpText、灰置与 `off` 状态，实测表见 [control-tree.md §3.1](references/control-tree.md)） | 把矩形当跨机器常量用（分辨率/缩放/窗口位置一变全变；停靠容器**只能靠矩形认身份**但矩形必须现读）；屏外区域（状态栏、输出/编译页签、`筛选器`）真实点击 |
| **按树路径真开编辑器并逐页测绘**（`ss_uimap.py open 1.0.2.3 0.3.0 … [--close]`：15 类页面的控件链、页签/关闭契约、设置页节锚、参数表行类名↔读写方式，见 [control-tree.md §16](references/control-tree.md)） | 打开"没有对应实体"的容器节点（`轴设置`/`轴组设置`/`Cam数据设置`/`数据跟踪设置`/`PrimaryTask`/`TempCtrlTask` 在本工程里 Enter 与真双击都不开页，§16.6）；靠默认遍历判"这页是空的"（`off` 子树会被裁掉，要加 `--all` 重采，§16.1） |
| **读任意 POU 的变量表**（`open <POU路径> --expand`：`DefaultGroupDataGrid` 的 名称/数据类型/初始值/分配到/保持/常量/注释 逐行逐格可读，"格子为空"有专门的机器可读形态，见 [control-tree.md §16.7](references/control-tree.md)） | 读**未选中**的变量页签（`输入/输出`/`外部`/`返回值` 的网格只在切过去之后才实化；切页签的通道未测）；把设置页 `--expand` 当救星（实测 6 个 `subsectionExpander` 本来就已展开，`Expand()` 无变化——读不到项是**节没切对**） |
| **逐个添加轴并按参数写入轴设置文档**（`ss_axis.py add/nav/set/apply` + `ss_axisparams.py`：左侧导航 8 个子页（轴基本设置/单位换算设置/操作设置/其它操作设置/限位设置/原点返回设置/位置计数设置/伺服驱动设置）的参数可读可写，写完用 `ss_axcmp.py` 对两份 `.smc2` 逐参数验收，见 [recipes.md §Q/§R](references/recipes.md)） | 用 UIA 直接点 `轴设置表` 的单元格（那张表是 WinForms，UIA 全盲；只能走 `ss_axtable.py` 的真 Win32 组合框 + 像素几何，[control-tree.md §17.1](references/control-tree.md)）；把轴页顶部那个 `输出设备1` 组合框当写入通道（**只显不写**，5 种机制全失败，[pitfalls.md §59](references/pitfalls.md)） |
| **改轴↔EtherCAT 从站绑定并逐行写 `过程数据` PDO 映射**（`ss_axpdo.py expand/collect/apply`：先设备后过程数据、按位文本 `startswith`、弹层中心滚轮 + 键入兜底，实测 17 行/轴全部落进模型；只读看折叠态用 `toggles`，认控件形状用 `peek`，[recipes.md §R](references/recipes.md) · [control-tree.md §17.2~17.3](references/control-tree.md)） | 让编译把空的 `PDOPathName`/`ODBitLocation` 补出来（不会，[pitfalls.md §65.1](references/pitfalls.md)）；换 `输出设备` 后指望原 PDO 映射还在（**换绑即清空该轴全部映射**，§61）；对 `IsEnabled=False` 的参数（`NexAxisStartDirection`、未使用轴的型号/单位/速度）在界面上找开关（没有开关，只能如实报告，[control-tree.md §17.4](references/control-tree.md)）；**把 `NexAxisPDOMappingTable` 改回去**（真点了折叠/展开、保存、连页签都关掉再保存，三种做法之后归档那串**一字不变**——它是"提交过 PDO 单元格"的只增不减历史标记，界面没有清除通道，§65.2） |
| **真落盘**（`ss_save.py --menu`：`文件(F)>保存` 走 UIA 展开+点击，以 `.smc2` 的 sha256 变化为唯一判据，实测 +1s 落盘） | 指望裸 `Ctrl+S`：表格里没关的下拉是独立顶层 `HwndWrapper[...]` 小窗，会**吃掉键盘**，文件纹丝不动（§66）；指望菜单项名字是干净中文：真实 `Name` 带访问键后缀（`保存(S)`），必须先剥再比 |
| **在 EtherCAT 拓扑里按计划表逐个右击插入从站**（`ss_ecat_build.py` 0.3.0：`<pid> <plan.json> <logdir> --save-each` → 每步"选端口 + 搜型号 + 右键 `插入(I)` + 改名"，建完 `renumber` 统一写节点号；21 个从站/16 步在某 EtherCAT 组态工程上端到端跑通，全程无 drag，归档 `RESULT EXACT`，见 [recipes.md §O](references/recipes.md)） | 把"位置"当从站行本身（必须先 `Expand` 父行、点**端口行**；行矩形是整棵子树高度，点中心会落到子行，[pitfalls §70](references/pitfalls.md)）；在关键字框里敲带端口/`Main device` 的整串型号（只匹配设备名，0 结果，§71）；同一端口按源顺序正序插（插入落在**头部**，必须倒序，§69）；插入阶段就写节点号（每插一个都自动重排，§69.3）；建完不保存（组态只在内存里，进程一走全丢，§72） |
| **装 ESI 描述文件**（`ss_esi.py master/open/installbtn/filedlg/find/close`：主设备右键 `显示ESI库` → `installFileButton` → Win32 文件框 `Edit id=1148` → `find` 复核型号出现） | 多实例时安装 ESI：会弹「因为正在运行多个Sysmac Studio，无法执行安装」，且这个框 `ClassName` 只是 `Window`、`AutomationId='MessageBoxView'`（§68） |

**硬边界**（细节见 [references/pitfalls.md](references/pitfalls.md)）：

1. **进程完整性要对得上**：Sysmac 本体实测可中权限运行（无 `requireAdministrator` 清单）；中权限注入到**提权**窗口会被 UIPI 静默丢弃。要么两边都中权限，要么两边都提权（提权→中权限的注入是允许的）。UIA 的 Pattern（如 `WindowPattern.Close`）跨完整性仍可用。见 pitfalls §35。
2. 控制进程**启动时必须声明 DPI 感知**，否则坐标全部偏移。
3. **一个动作序列要在同一个进程里跑完**——弹出菜单的生命周期只在当前调用内。
4. 会话锁屏时 `GetForegroundWindow()` 返回 0，**鼠标/键盘注入与截图无效**（`ImageGrab` 直接抛 `screen grab failed`，UAC 也会自动取消）；消息驱动（`TVM_*`）、UIA Invoke 仍可用。**工程树的选中/打开依赖真实鼠标**，锁屏时做不了。
5. **菜单点不开先查残留模态窗**：主菜单项本身是 `MenuItemControl`（`ss.py menu` 实测可用）；点不开几乎总是因为有个没关的 `#32770`，或该实例进了"菜单罢工"状态（pitfalls §20）。残留的 `库索引/引用库` 还会让树双击"看起来完全没反应"（`当前选项卡：（无）`）。兜底做法是坐标点菜单栏 + 助记符键（pitfalls §23）。`ss.py grab` 的截图里**没有**菜单和对话框（PrintWindow，见 §24）。

## 2. 环境准备

```bash
python -m pip install "uiautomation>=2.0" pillow
```

- 用**独立 venv** 装依赖，别污染系统解释器。纯标准库 + 这两个包即可，无需 OMRON SDK。
- 必须**提权**运行脚本。最省事的做法是一次 UAC 起一个常驻高权限解释器，之后按行投递命令（协议示例见 [references/architecture.md](references/architecture.md#51-推荐形态常驻高权限解释器)）。
- 每次运行先自检：`python <SKILL_DIR>/scripts/ss.py wins`，能列出 `SysmacStudio.exe` 的窗口才算接上。

## 3. 30 秒上手

```bash
S=<SKILL_DIR>/scripts

python $S/ss.py wins                 # 1. 找实例：pid / hwnd / 标题 / 矩形
python $S/ss.py state auto           # 2. 读状态：工程名、控制器、在线/离线、编辑器数
python $S/ss_uimap.py treelabels <pid> tree.txt  # 3. 看结构 + **每个节点的名字**（path/名字/子节点数，锁屏也可用）
python $S/ss_tree.py goto <pid> 1.0.2     # 4. 光标定位：编程>POUs>功能块（锁屏也可用）
python $S/ss.py menu <pid> 编辑(E) 复制(C)  # 5. 走菜单（弹出菜单自动在独立窗口里找）
```

第 3 步的 `treelabels` 建议**永远先跑**：树的下标随工程内容变化，只有名字能确认 `1.0.2` 真的是"功能块"。想知道某类节点有哪些右键动作，查 [references/tree-node-menus.md](references/tree-node-menus.md)，不要现场试。

`<pid>` 可以写 `auto`，脚本会挑面积最大的可见 Sysmac 主窗口所属进程。**同机开两个实例时必须显式给 pid**，否则会操作错工程。

## 4. 脚本参考

脚本都是"一个命令做一件事、成功打印 OK、失败打印原因并返回非 0"，方便被 Agent 串起来。全部路径无关，只依赖 `uiautomation`/`pillow`。

### 4.1 `scripts/ss.py`（核心：窗口 / 控件 / 输入）

| 命令 | 作用 |
| --- | --- |
| `wins` | 列出 SysmacStudio 进程的所有顶层窗口（pid/hwnd/标题/矩形/可见/最小化） |
| `state <pid\|auto>` | 读标题、工程名、控制器名、`MainDockSite` 模式（Online/Offline）、编辑器数量、是否忙 |
| `dump <pid> <文件\|-> [深度] [每层上限]` | 导出该 pid 所有顶层窗口的 UIA 树（ControlType/Name/AutomationId/ClassName/矩形） |
| `find <pid> <AutomationId\|Name>` | 定位一个元素并打印类型/矩形/是否可用 |
| `click <pid> <AutomationId\|Name>` | 依次尝试 Invoke/Select/Toggle/Expand/Collapse，兜底 Click |
| `at/dbl/rclick <pid> <x> <y>` | 物理像素单击/双击/右击（先抢前台；锁屏时无效） |
| `keys <pid> <SendKeys 串>` | 例：`{ADD}` `{ENTER}` `{ESC}` `^a` |
| `type <pid> <文本>` | 输入文本（`{` `}` 会被转义） |
| `menu <pid> <菜单名> <菜单项名>` | 点开主菜单，在**新出现的独立弹窗**里按 Name 找项并点 |
| `popups <pid> [深度]` | 导出所有非主窗口的弹窗（菜单/对话框）UIA 树 |
| `grab <pid> <png> [x1 y1 x2 y2]` | 截图（先抢前台；被遮挡会截到别的窗口） |
| `flow <pid> "步骤;步骤"` | 动作序列，步骤：`at:x,y` `dbl:x,y` `rclick:x,y` `cat:x,y`(Ctrl+点) `sat:x,y`(Shift+点) `drag:x1,y1,x2,y2` `wheel:x,y,n` `click:KEY` `menu:M>I` `keys:K` `type:T` `wait:ms` `dump:FILE` `grab:FILE` |

### 4.2 `scripts/ss_tree.py`（工程树：路径 / 展开 / 复制粘贴）

| 命令 | 作用 |
| --- | --- |
| `struct <pid> [最大深度]` | 只读结构：句柄、深度、子节点数。**不读文字，绝对安全** |
| `rows <pid>` | UIA 能看到的行——**实测只有根节点**（带矩形）。用来点根行，不能用来定位深层节点 |
| `count <pid> <路径>` | 某节点的子节点数（**确认节点身份的可靠指纹**） |
| `goto <pid> <路径>` | 逐级展开祖先 → `TVM_SELECTITEM` 移动光标 → 回读校验 → 打印子节点数。**任意深度、不需要前台** |
| `select <pid> <路径>` | 只移动光标，不打印（`goto` 的简版） |
| `expand <pid> <路径>` | `TVM_EXPAND` 展开。**只有根节点会真的展开**，深层返回 0 且视觉不变。深层要展开用 `ss_uimap.py` 的 `expand_node()`（caret + 真实 `VK_RIGHT`，需前台，见 project-tree.md §3.2） |
| `copy <pid> <路径>` | 定位 → 抢前台 → `编辑(E)>复制(C)` |
| `paste <pid> <路径> [--yes]` | 定位 → 抢前台 → `编辑(E)>粘贴(P)`，自动应答覆盖确认 |
| `del <pid> <路径> [--yes]` | 定位 → 抢前台 → `编辑(E)>删除(D)`，自动应答确认 |

路径写法：**从根开始的子节点下标，点分隔**。`0`=配置和设置，`1`=编程，`1.0`=POUs，`1.0.2`=功能块。详见 [references/project-tree.md](references/project-tree.md)；**下标随工程内容变**，用之前先 `ss_uimap.py treelabels` 把名字读出来对一遍。每种节点的右键菜单见 [references/tree-node-menus.md](references/tree-node-menus.md)。

### 4.3 `scripts/ss_clip.py`（剪贴板：验证复制是否真的发生）

| 命令 | 作用 |
| --- | --- |
| `list` | 枚举剪贴板全部格式与字节数 |
| `dump <格式名> <文件>` | 落盘某个自定义格式 |
| `set <格式名> <文件>` | 回放某个自定义格式 |

用途：`编辑>复制` 是**可点但可能无效**的，判定"到底复制成功没有"只能看这个。

### 4.4 `scripts/ss_build.py`（编译 + 全量读错误）

| 命令 | 作用 |
| --- | --- |
| `totals <pid\|auto>` | 只读编译面板头部：`errors=385 warnings=0` |
| `list <pid\|auto> <out.txt>` | 全量抓错误网格（`ScrollPattern` 逐屏），写 UTF-8，列 = `编号/说明/程序/位置` |
| `run <pid\|auto> [out.txt]` | 点 `编译控制器(B)` → 轮询到数字稳定 → 可选接着导出列表 |

### 4.5 `scripts/ss_export.py`（导出 .smc2）

| 命令 | 作用 |
| --- | --- |
| `<pid\|auto> <文件名> [--keep-dir]` | 点 `文件` 菜单栏坐标 → 键 `E` → 抢对话框前台 → 文件名（aid `1001`，中文走剪贴板）→ `保存(S)`（aid `1`）→ 覆盖确认 `是(Y)` |

细节与三个必踩的坑见 [recipes.md §L](references/recipes.md) 与 [pitfalls.md §25](references/pitfalls.md)。

### 4.6 `scripts/ss_record.py`（录制手工操作 → JSON）

界面路径"知道要做什么、但脚本做不出来"时，让人手工做一遍并录下来。**必须提权**（Sysmac 以 High 运行）。

| 命令 | 作用 |
| --- | --- |
| `--out DIR` | 输出 `rec_<时间>.json` / `.jsonl`；默认 `./recordings` |
| `--pid N` / `--all` | 只录指定实例 / 录所有应用（默认只录发往 Sysmac 的） |
| `--note TEXT` | 写进 meta，标注这段录的是哪一步 |
| `--seconds N` | 自测：N 秒后自动停 |

停止热键 `Ctrl+Alt+F12`。记录 click/drag/wheel、键盘/粘贴/快捷键、焦点、顶层窗口及其控件树；
每个点击在**按下前**解析元素路径（含祖先与行内文本），因此能还原“展开树节点 → 选中插入点 →
右键插入”这类手工路线。详细 schema、限制与“JSON → 脚本”的映射见
[references/recording.md](references/recording.md)。

**架构铁律（v0.2.0）**：低级钩子回调里只准入队，UIA / 剪贴板 / 写盘 / 打印全部在 worker 线程做。
钩子里调 UIA 会让“钩子等目标 UI 线程、目标 UI 线程等钩子返回”互锁，按一下 Win 键就能把整个
控制台卡死（亲身踩过，见 [pitfalls.md §41](references/pitfalls.md)）。改这个文件时别把任何
UIA 调用挪回 `_mouse_proc` / `_key_proc`。

### 4.7 `scripts/ss_uimap.py`（UIA 全树测绘：面板 / 菜单 / 弹层 / 编辑器 / 工程树）

只读测绘工具（开菜单、开编辑器、按 Esc，**从不 Invoke 菜单项、不输入、不保存**）。**必须提权**；除 `tree`/`treelabels` 外都要真实桌面（不能锁屏）。所有命令第一参数是 `<pid|auto>`，第二参数是输出文件。

| 命令 | 作用 |
| --- | --- |
| `scan [--all] [--depth N] [--pat]` | 主窗口全树落盘：`缩进 \| Type \| Name \| AutomationId \| ClassName \| HelpText \| rect \| E/F/K \| patterns`。默认剪掉 `IsOffscreen` 子树 |
| `panels` | 每个停靠区一行：菜单栏项、工具栏按钮、选项卡条、树头、状态栏文本、文档选项卡。看骨架最省时间。窗口底边超出屏幕时加 `--fit`（先把窗口滑进屏内，结束时还原）——状态栏、输出/编译页签、`筛选器` 默认都在屏外，读得到点不到 |
| `menus [--only A,B]` | 打开**每一个**顶级菜单（含二级），记录 文字/加速键/可用态/有无子菜单/勾选态 |
| `ctx <x> <y> [label]` | 在物理坐标真实右键，落盘弹层，Esc 关闭 |
| `editor` | 当前开了哪些文档选项卡（`TabbedMdi`）+ 各自内部选项卡 + 左侧导航 + 工具条 |
| `open <路径…> [--fit] [--depth=N] [--all] [--pat] [--expand] [--close]` | **按工程树路径真开编辑器并逐页落盘**：展开祖先 → `TVM_SELECTITEM` 选中 → 真实点击行 + 真实 `VK_RETURN`；不开就"取消选中 + 真双击"兜底，再不开就留取证行（`tree focus / row hit by click / caret kept / rows n->m / kids / new windows / ancestors`）。开成功时把该 `DocumentWindow` 的子树整棵 walk 出来；`--pat` 在每行尾附该元素真的支持的 UIA 模式（`SyntaxEditor=Text` 无 `Value`、`closeButton=Invoke` 却调不动，都是它测出来的）；`--expand` 再对页内每个 `ExpandCollapse` 调 `Expand()` 后重走一遍（**POU 变量表只有展开后才在树里**）；`--close` 在同一轮里用 `closeButton` 关掉。15 页实测形状见 [control-tree.md §16](references/control-tree.md) |
| `close <pid\|auto> <out> [--all] [Name…]` | 关编辑器：不给名字就 `--all`；`# before:` / `# after:` 是两次的文档名列表。**一轮测绘收尾必跑**，脏页会污染下一轮 `panels`/`--fit` |
| `tree [--expand]` | 工程树**结构**：路径下标、子节点数、展开态、caret（`TVM_*` 消息，不需要前台） |
| `treelabels` | 全树 `path  节点名  kids=N`。名字用 `TVM_GETITEMW(0x113E)` + **远端** `TVITEMW`/文本缓冲读，安全；不需要前台，锁屏可用。**动手前先跑它**（见 [project-tree.md §2](references/project-tree.md)、[pitfalls.md §54](references/pitfalls.md)） |
| `treectx --fit 0.0 1.0.2.0 ...` | 逐个路径：caret+真实 `VK_RIGHT` 展开祖先 → 远端 `TVM_GETITEMRECT` 算行中心 → 真实点击并让树回读句柄证明点中 → 右键弹层落盘。菜单阶梯 `RCLICK → RCLICK2(+80px) → VK_APPS`；结果表见 [tree-node-menus.md](references/tree-node-menus.md) |
| `treerows [--max N] [--depth N]` | 真实点击 `+/-` 走完棵树，记录可见行的 path/缩进/标签宽/子节点数（行几何标定用） |
| `diff <a> <b>` | 两份落盘的行差（什么被打开/关闭/新出现） |

四个必知前提：① 目标窗口常整块悬在屏幕外，`treectx`/`treerows` 要加 `--fit`（结束后自动还原窗口位置）；② `import uiautomation` 会把 `SendMessageW` 的原型改成 32 位 `LPARAM`，**64 位 `HTREEITEM` 被截断**，本文件在 import 后立刻恢复原型（见 [project-tree.md §2](references/project-tree.md)）；③ 弹出菜单是独立顶层 HWND，"打开 + 读取"必须在同一次调用里完成；④ `open`/`close` 是这套工具里**唯一真的改变界面状态**的命令——实测关掉"没编辑过"的页不弹保存框、不冒新窗口，所以用完一定要 `--close` 或 `close --all`，别把页留给下一轮。

### 4.8 `scripts/probe_select.py`（消息选中的语义探针，回归用）

`python scripts/probe_select.py <pid|auto>` —— **只发消息**（不点鼠标、不抢前台、不敲键盘），对若干不同深度的节点回答四个问题：`TVGN_CARET` 是否等于目标、目标是否真拿到 `TVIS_SELECTED`、上一行是否被取消选中、软件是否滚进视野；最后把主窗口最小化再测一遍。输出 `scripts/logs/select.txt`。

升级 Sysmac 或怀疑"消息到底管不管用"时先跑它，结论见 [pitfalls.md §56](references/pitfalls.md)——这条结论历史上反转过两次，别再用推理代替测量。它会让主窗口最小化一次，别在它跑的时候手工动窗口。

### 4.9 运动控制轴家族（`ss_axis` / `ss_axtable` / `ss_axpdo` / `ss_axisparams` / `ss_axisplan` / `ss_axcmp` / `ss_crashdlg`）

一条龙：**建轴 → 写轴设置文档 → 写那张 WinForms 表 → 绑从站 → 写 PDO → 离线验收**。完整顺序与判据在 [recipes.md §R](references/recipes.md)。

| 脚本 | 命令 | 作用 |
| --- | --- | --- |
| `ss_axis.py` | `add <pid> <out> <树路径> [--name 名] [--item 文本] [--list]` | 按实测路线建一个轴：右键 `轴设置` 节点 → `添加` → 子菜单第一项，回读新行，`--name` 走 F2 行内重命名；`--list` 只记录菜单不改任何东西 |
| | `nav <pid> <out> <树路径>` / `read <pid> <out> <树路径> <aid,…>` / `dump <pid> <out> <文档名> [节aid]` | 打开某轴的轴设置文档（左侧节 aid：`axes_scale`/`axes_dynamics`/`axes_io`/`axes_limit`/`count_mode_set`/`servo`）、按 aid 读该节参数、把整个文档或某一节转储 |
| | `set <pid> <out> <树路径> <aid> <标签> <值>` / `apply <pid> <out> <plan.json> [路径过滤]` | 写一个参数；按 `plan.json`（`[{"path":"0.4.0.0","sets":[{"section","label","value"}]}]`）**一根轴一个进程**批量写——同一次 UIA 会话里写完该轴全部字段，不逐字段重开页 |
| | `probe <pid> <out> <树路径> <aid> <键>` / `rename` / `close` | 单个控件的全量取证（patterns / Name / HelpText / `GetSelection()` / 开下拉后的每一项及其 selected）；行内改轴名并回读；按文档名关页 |
| `ss_axtable.py` | `get <pid> <out> <列> <行>` | **读**轴设置表某格的模型真值（`CB_GETCURSEL` + `CB_GETLBTEXT`） |
| | `set <pid> <out> <列> <行> <子串>` | **写**一格：真点开会浮出真 Win32 组合框，用关闭态 `{UP}`/`{DOWN}`（触发 `CBN_SELCHANGE`）+ `{ENTER}` 提交；`CB_SETCURSEL` 禁用（不发通知），离开格子后重开复读才算数 |
| | `probe <pid> <out> [列] [行]` / `geom <png> [y0 y1]` | `EnumChildWindows` 列 COMBOBOX/EDIT 子句柄与全部条目；像素找列/行分隔线（换分辨率必跑） |
| `ss_axpdo.py` | `expand` / `collect` / `apply` / `rows` / `fold` / `toggles` / `peek` | PDO 网格三组展开、**只读**转储（不碰 toggle）、按 plan 逐行写 `设备`+`过程数据`、列当前行、折回三组（`fold`/`expand` 的**点击是真的**，但改不动归档里的 `NexAxisPDOMappingTable`，§65.2）；`toggles` 只读报三组 `+`/`-`（含 `IsOffscreen` 原文与 `ToggleState`），`peek` 把组行整棵子树打出来认形状 |
| `ss_axisparams.py` | `<file.smc2> [--num N] [--diff] [--all] [--csv f.csv]` | 离线（只读文件）把轴 XML 摊平成 `(段, 参数, 当前值, 默认值, 可用, 可见, 选项)`——界面读不到的以这里为准 |
| `ss_axisplan.py` | `<源.smc2> <轴号> <collect.txt> [-o plan.json]` | 由**源归档**出 `pdkey`、由**目标网格转储**出 `label`/`device`，生成逐行写计划；collect 全 `＜未分配＞` 时报"绑定还没落进模型" |
| `ss_axcmp.py` | `<A.smc2> <B.smc2> [轴号…]` | **唯一验收口**：两份工程同名轴逐参数对比，末行 `#### total shared=N differing=M`；差异分三类处置（见该文件头注释） |
| `ss_crashdlg.py` | `<pid> <out> [click]` | 发现 .NET 未处理异常框（它会冻住后面所有 UIA）；默认**只报告**，`click` 时**只点 `继续(C)`**，`详细信息`/`关闭` 永不碰 |
| `ss_save.py` | `<pid\|auto> [前缀] --file <目标.smc2> [--out <目录>] [--esc N] [--menu]` | **真落盘**（`--file` 必填，缺失直接退出码 2）：记目标文件 sha256 →（`--esc`，默认 2）关掉残留弹层 → `force_foreground` + 真 `Ctrl+S` → +1/3/5/8 s 各截图 + 枚举弹层，**文件 sha 一变就停**；不变就 `--menu` 走 `文件(F)>保存`（UIA `Expand()` + 按剥掉访问键后缀的名字点 `保存(S)`，实测 +1s 落盘）。末行 `#### SAVED (+Ns)` / `#### FILE UNCHANGED`（退出码 1 = 没变）。弹层**只记录不动手**（连它的 `IsWindowVisible`/`GWL_EXSTYLE` 都打出来，用来认出"那个吃掉键盘的 93×31 小窗"），提到 许可/序列号 的窗口一律不碰并标注 |

坐标类常量（`ss_axtable.py` 的 `COL`/`ROW`/`Y0`/`PITCH`）是本机 1920×1080 最大化下量出来的，`COL` 的键名还是**具体工程的列头**（每个轴一列）；换机器先 `geom` 重量、换工程先 `probe` 对齐。

### 4.10 EtherCAT 组态家族（`ss_ecat` / `ss_ecat_build` / `ss_ecat_archive` / `ss_ectree` / `ss_esi` / `ss_ecat_name`）

一条龙：**装 ESI → 选端口 → 搜型号 → 右击 `插入(I)` → 改设备名 → 最后统一写节点号 → 归档验收**。完整顺序与判据在 [recipes.md §O](references/recipes.md)。除归档读取（普通权限即可）外都要**提权**。

| 脚本 | 命令 | 作用 |
| --- | --- | --- |
| `ss_ecat.py` | `<pid> rows <out> [--expand]` / `search <out> <关键字>` | 拓扑行清单（主设备/从站/端口/耦合器/NX 单元，含 rect、节点号、选中态）/ 往工具箱 `SearchTextBox` 剪贴板粘贴关键字并落盘结果行（判据是结果列表，框里的字读不回） |
| | `insert <out> <关键字> [--pick 子串] [--at 位置] [--allrev]` | 单步插入：先选位置 → 再选硬件结果行 → 右击 `插入(I)`，**全程无 drag**，插不进就如实返回 False 并落盘证据；`--at` = `master\|last\|slave:<行序号>\|port:<行序号>:<端口标签>`；`--pick` 多条命中时挑行；`--allrev` 先勾「显示所有版本」 |
| | `delete` / `name` | 从站行右键 `删除(D)`（无确认框）/ 写设备名 |
| `ss_ecat_build.py` | `<pid> <plan.json> <logdir> [--save-each]` | 按计划表批量执行"选位置 → 选硬件 → 右击插入 → 改名"，每步各自落盘；`--save-each` 每步走 `文件(F)>保存`（组态只在进程内存里，不保存进程一走全丢，§72）；2 次重试读回、`sweep_expand` 后再校验 |
| | `<pid> renumber <plan.json> <logdir> [--only "名1\|\|名2"]` | **最后**统一写节点号（每插一个都自动重排全网络，插入阶段写号必被冲掉，§69.3） |
| `ss_ecat_archive.py` | `<archive.smc2> [tree\|flat\|diff <other.smc2>] [--sub 关键字]` | **只读归档真值**：tree=实体嵌套（subtype/name/DN/SDName）、flat=单链（序号\|subtype\|name\|节点标签\|设备名）、diff=逐条比节点标签序列；`.oem` 要 `utf-8-sig` 解码，耦合器节点标签在 SDName 不在 DN |
| | `<A.smc2> cmp <B.smc2>` | **跨工程验收口**：只比 `(subtype, 节点标签)`、不比实体 `name`（name 每工程各自分配，`diff` 因此天然全红），末行 `RESULT EXACT` / `RESULT DIFF` |
| `ss_ectree.py` | `<pid\|auto> dump <out> [--expand] [--passes N]` | 拓扑树深度展开 + 层级落盘（`ExpandCollapsePattern` 逐节点 `Expand()`，默认 6 轮）——"某从站挂在哪个端口下"是选插入位置的唯一定位依据 |
| | `<pid\|auto> subtree <out> <行名子串> […]` | 按行名定位 → `ScrollIntoView` → 只展开该行子树 → 从该行递归落盘；拓扑树按视口实化、整树 walk 会缺段，核局部结构用它（§73），找不到的子串记 `# NOT FOUND` |
| `ss_esi.py` | `<pid> master/open/dump/installbtn/filedlg <xml路径>/find <关键字>/close/msgbox [按钮名]` | ESI 库路线：主设备右键 `显示ESI库` → `installFileButton` → Win32 文件框（`Edit id=1148`）→ `find` 复核型号出现；**多实例时安装必被拒**（§68） |
| `ss_ecat_name.py` | `<pid> <out> <设备名>` | 给选中从站行写设备名：点单元格 → 真 `Ctrl+A` → 剪贴板粘贴 → `Enter`（不全选会插成脏值） |

### 4.11 零散补充

- `scripts/ss_ctx.py <pid> <x> <y> list | click "<项>"` —— 驱动**工程树行的右键菜单**。为什么要单独一个脚本：功能区 `编辑(E)` 那个下拉是自绘 WPF 弹层，UIA 只给一个 `PaneControl`，`粘贴(P)` 还可能被静默灰掉；而右键树行弹出的是**真菜单**，`MenuItem` 全部暴露（`复制(C)`/`粘贴(P)`/`删除多个项目`/`重命名(N)`…），能按名字找、按名字点。需要提权 + 前台。
- `scripts/ss_dlg.py <pid> list [标题包含串] | bind <AutomationId|按钮名> [标题包含串] | text [标题包含串]` —— 通用对话框通道：`list` 枚举该 pid 全部可见顶层窗及每个窗里的 Button（Name/aid/rect/enabled）；`bind` 在匹配窗里点该按钮（Invoke 优先、失败退真实点击，**只点一个、不猜第二个**，找不到如实失败）；`text` 读消息框正文。许可/序列号窗口一律不碰（§7 红线）。
- `scripts/ss_libref.py <pid> <out.txt> <open|select|delete|add|confirm|replace|warn> [slr路径]`（0.2.0）—— 库索引 `.slr` 引用管理。`open` 走 `工程(P)>悬停 库(L)>显示索引(S)` 打开库索引（全程鼠标绕 IME）；`add` 走 `+`→`引用库文件`→剪贴板贴完整路径→**校验 `Value==目标` 才点 `打开(O)`**→消警告；`replace`（需传 slr 路径）= `select→delete→消警告→add→warn→confirm` 一步换库/**强制重载库缓存**（改磁盘 `.slr` 后刷新键恒灰，只有删旧行+重加同路径才会重读，[pitfalls §79](references/pitfalls.md)）；`warn` 补消可能 >2s 才冒出来的「引用库」/「重命名」模态。**替换不是追加**（同名库不删旧行直接 `+` 会撞名出两行）；库索引改动**点「确定」才提交**，中途「关闭」可整体放弃。端到端配方见 [library-and-tasks.md §7](references/library-and-tasks.md)。必须提权 + 前台。

## 5. 软件布局与控件地图

完整清单见 [references/control-tree.md](references/control-tree.md)，这里只给骨架：

```
SysmacStudio.exe (High IL)
├─ 启动页 StartPageView         ← 新建/打开/导入/连接设备/许可（**工程打开后仍以 disabled+off 留在树里**，按 id 找元素要过滤）
├─ 新建工程向导 NewSolutionControl ← 工程属性 + 插入设备
└─ ControllerView                ← 工作区整页（MenuControl/ToolBarControl/MainDockSite/StatusBar 都挂在它下面）
   ├─ MenuControl/MainMenu       ← 10 个主菜单（弹出项在独立顶层窗口）
   ├─ ToolBarControl             ← 6 条 ToolBar、33 个命令按钮（build/device_build/online/download/…）
   ├─ MainDockSite (Name=Online|Offline)
   │  ├─ 左：ToolWindowContainer  ← 多视图浏览器（工程树，WinForms 宿主）
   │  ├─ 中上：TabbedMdiContainer ← 编辑器（LD/FB/ST/设备设置…）；0 个编辑器时容器仍在但 IsOffscreen=True
   │  │     每个编辑器 = `Pane(cls='DocumentWindow')`，`Name` 就是文档名，页面根 `ClassName` 决定类型（`StructuredTextView` / `LadderProgramView` / `ConfigurationView` / `MainEditorWindow` / `IOMapBaseView` / `NamespaceDataTypeView` / `GlobalVariablesView`…），实测链见 [control-tree.md §16](references/control-tree.md)
   │  ├─ 中下：ToolWindowContainer ← 输出 / 编译
   │  └─ 右：ToolWindowContainer  ← 工具箱
   └─ StatusBar（ProgressBar **空闲时 IsOffscreen=True**，变 False = 正在忙）
```

- 弹出菜单、下拉、对话框、文件对话框都是**独立顶层 HWND**，必须按 pid 枚举全部顶层窗口去找。
- `ToolWindowContainer-*` / `TabbedMdiContainer-*` 的后缀是**每次运行随机的 GUID**，只能前缀匹配；**四个容器谁是谁只看矩形**（左 `x<30 宽≈250` / 右 `x>屏宽-280` / 中下 `宽≈1390 且 top 大`）。
- 元素定位优先级：`AutomationId` > `Name` > `ClassName`+相对矩形 > 物理坐标。
- **带实测矩形的骨架图**（菜单栏 / 6 条工具栏逐按钮 / 树容器链 / 编译面板 / 状态栏 / 工具箱）在 [control-tree.md §3.1](references/control-tree.md)、[§5](references/control-tree.md)、[§6.1](references/control-tree.md)、[§9.1](references/control-tree.md)、[§10.1](references/control-tree.md)。坐标本身不可复用，用处是**判"这块在不在屏幕内"**；要坐标就现读（必要时 `panels --fit`）。

## 6. 常用配方

| 目标 | 看 |
| --- | --- |
| 新建工程（含设备型号/版本） | [references/recipes.md](references/recipes.md#a-新建工程) |
| 读当前状态 / 多实例分辨 | [references/recipes.md](references/recipes.md#b-读状态与分辨实例) |
| 批量搬运程序与功能块 | [references/recipes.md](references/recipes.md#d-批量搬运-pou) |
| 组态（设备/轴/CAM/EtherCAT）入口 | [references/recipes.md](references/recipes.md#e-组态入口) |
| 写程序（新建 POU / 打开编辑器） | [references/recipes.md](references/recipes.md#f-写程序) |
| 编译 / 全量读错误 / 分类 | [references/recipes.md](references/recipes.md#g-编译--构建) · [#M](references/recipes.md#m-全量读编译错误并分类) |
| 导出 `.smc2`（含覆盖确认） | [references/recipes.md](references/recipes.md#l-导出成-smc2含覆盖确认) |
| 建数据类型命名空间（子空间） | [references/recipes.md](references/recipes.md#n-建数据类型命名空间子空间) |
| 新建运动控制轴并逐个填参数 | [references/recipes.md §Q](references/recipes.md#q-新建运动控制轴并填参数工程树--轴页) |
| **改轴↔从站绑定 / 逐行写 PDO 过程数据 / 按参数验收两份工程** | [references/recipes.md §R](references/recipes.md#r-轴从站绑定与-pdo-过程数据映射2026-11-07-实测唯一可行界面路线) |
| **照抄一整份 EtherCAT 组态（ESI 安装 → 右击插入 → 改名/节点号 → 归档验收）** | [references/recipes.md §O](references/recipes.md#o-在-ethercat-编辑器里组态从设备右击插入路线2026-11-08-端到端实测) |
| 导入 / 另存为 / 导出 / 校验 | [references/project-files.md](references/project-files.md) |
| 挂库 / 分配任务 / 改变量表 | [references/library-and-tasks.md](references/library-and-tasks.md) |
| **在已有库 FB 上加功能 → 重建 .slr → 离线对齐接口 → 换引用强制重载 → 重编译 → 菜单保存（端到端）** | [references/library-and-tasks.md §7](references/library-and-tasks.md) · [offline-surgery.md §10](references/offline-surgery.md) · [pitfalls.md §78~§80](references/pitfalls.md) |
| 工程树路径与展开边界 / 哪些东西搬不动 | [references/project-tree.md](references/project-tree.md) |
| 每种树节点的**右键菜单全表**（84 节点实测，含"哪些节点根本没有菜单"） | [references/tree-node-menus.md](references/tree-node-menus.md) |
| 某类**编辑器页里有什么控件**（ST/LD/数据类型/全局变量/设置页/EtherCAT/机架/I-O 映射/事件），以及哪些节点**打不开页** | [references/control-tree.md §16](references/control-tree.md#16-编辑器内部形状2026-11-06-ss_uimap-py-open-实测-15-页) |
| **轴设置表（WinForms）与 PDO 网格的真实形状**：格子→真 Win32 组合框契约、像素几何、`过程数据` 按位下拉文本、UIA 灰置不可达的参数 | [references/control-tree.md §17](references/control-tree.md#17-轴设置表winforms与轴-pdo-过程数据2026-11-07-实测) |
| 界面搬不动的组态怎么补（`.smc2` 实体移植） | [references/offline-surgery.md](references/offline-surgery.md) |
| 踩坑清单 | [references/pitfalls.md](references/pitfalls.md) |
| 新版本重新校验 / 补充知识 | [references/extending.md](references/extending.md) |

## 7. 安全红线（不可协商）

1. **绝不读取、输入、导出任何序列号 / 授权文件 / 凭据。** 许可页只允许"看"，不允许填。
2. `online` / `download` / `upload` / `reset` / `drive_mode` / `program_mode` / `sync` 会改变**真实控制器**状态 —— 没有用户当轮明确同意，一个都不要点。
3. 用户正在使用的工程：`删除` / `重命名` / `另存为` / `导出覆盖` 之前必须确认，并且**先确认目标工程已保存到磁盘**。
4. `文件>导入` 会**先关闭当前工程**，未保存的内存工程会丢失（实测踩过）。导入前必须先保存。
5. 删除确认框显示的是**内部名**，可能与树上显示名不同（实测 `复制1_Buzzer_Config` 内部名是 `Buzzer_Config`）。名字对不上就按"否"。
6. 不要为了让自动化跑起来去改 Sysmac 的兼容性设置（如 `RunAsInvoker` 降权）——很可能废掉驱动/通信组件。

## 8. 维护约定

- 本 Skill 是活文档。**同一会话里每实测出一条新的操控知识（新 ID / 新坑 / 新验证边界），立即写进对应 reference 并递增 `version`**，同时在文末表格记一行。
- 未实测的推断一律写进 [references/extending.md](references/extending.md) 的"待验证清单"，不得混进正文当事实。
- 换机器 / 换版本后，先跑 [references/extending.md](references/extending.md) 的"版本回归清单"。

## 9. 更新记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| 0.11.0 | 2026-11-13 | **在已有库 FB 上加功能 → 换进目标工程，整条端到端打通并验收**（某轴控库工程：给已封装的轴 FB 按轴开关加末端振动抑制分支、默认 OFF，重建 `.slr` 后换进目标工程，重编译从 12 错收敛到 **0 错 / 0 警告**，菜单保存落盘）。① **改库源用"按轴开关、默认 OFF"形态**（[offline-surgery §9](references/offline-surgery.md)）：在已有轴 FB 的配置结构体里加 `xVibEnable : BOOL := FALSE`，FB 体内 `IF … THEN <新分支> ELSE <原逻辑> END_IF`，不启用时对所有轴零行为变化、不破坏存量调用；注入 DUT/改源 FB 的三条编译硬规则（DUT 字段 IV 要带类型前缀 `LREAL#0.0`、常量 IN_OUT 实参要传给带 `Const=1` 的形参、混合 ENUM+STRUCT 容器根要 `<data Version="1">`）已用真编译二分定位到 0 错。② **库源 FB 形参名与"目标所依据的已编译库"漂移**（源 `iMasterNum`/`iSlaveNum` vs 原已编译库 `diMasterNum`/`diSlaveNum`）⇒ 重建的 `.slr` 让目标调用点报 12 条「'diMasterNum'不是输入-输出变量」；**不回界面逐个改**，按 [offline-surgery §10](references/offline-surgery.md) 配方在新 `.slr` 上**只对该 FB 的接口+体**离线改名，与 pristine 原库做 **Id 归一化**校验（每变量 `Id="GUID"` 每次重建都变 ⇒ 比较时 `re.sub` 抹掉；体字节全等、接口归一化后全等），守住别的 FB 字节不变（新 [pitfalls §78](references/pitfalls.md)）。③ **库缓存不自动重载**：改磁盘被引用的 `.slr` 后直接重编译错误一条不少，`库索引` 的**刷新(↻)键恒灰**（选中行也灰）⇒ 唯一可行的强制重读 = **删旧引用行 + 重加同一路径**；**替换不是追加**（新旧 `.slr` 库名相同、内部 Library id 不同，不删直接 `+` 会撞名出两行）；「引用库」警告可能 >2s 才冒出来，末尾再 `warn` 兜底；库索引改动**点「确定」才提交**、中途「关闭」可整体放弃（新 [pitfalls §79](references/pitfalls.md)）。④ **写锁定与陈旧内存实例**：被 Sysmac 开着的 `.smc2`/`.slr` 离线 `os.replace` 报 `WinError 5`（目标文件不变，交换是最后一步）；仍开着库源的实例持**改之前的陈旧内存副本**，从它保存/创建库会把磁盘补丁打回原形 ⇒ 离线改完让该实例从磁盘重开或不保存地关闭（新 [pitfalls §80](references/pitfalls.md)）。⑤ 脚本：`ss_libref.py` 0.1.0→**0.2.0**，dispatch 重构为函数式并新增 `replace`（select→delete→消警告→add→warn→confirm 一步换库/重载）与 `warn`（补消延迟模态）两模式，docstring 补库缓存重载原理与延迟警告教训，所有实测 UI 步骤/坐标/剪贴板校验保持不变。⑥ 新配方 [library-and-tasks §7](references/library-and-tasks.md)（7.1 创建库含 §77 保存框默认覆盖原库的坑 / 7.2 离线对齐接口 / 7.3 换引用强制重载 / 7.4 重编译+菜单保存+三点验收 / 7.5 收尾），[offline-surgery §10](references/offline-surgery.md) 给出可复用的 `.slr` 离线补丁 Python 配方（rename/norm/TARGETS/GUARDS/backup/保 compress_type+order 重写/os.replace）与 5 条硬约束。⑦ §1 能力表补 1 行能做 / 1 行不能做，§4.11 补 `ss_libref.py` 条目，§6 配方表补端到端链接。**MCP 桥接器 `serve_http.py` 无功能改动（仍 0.2.0，Sysmac 知识都在 Skill 侧）**。 |
| 0.10.1 | 2026-11-09 | **开源可移植整理**：全部文档去除本机绝对路径/私有工程名/固定实例句柄，统一占位符（`<pid>`、`<skill目录>` 等）；验收命令内置（`ss_ecat_archive.py cmp`、`ss_ectree.py subtree` 取代外部一次性脚本）；`ss_save.py --file` 必填；新增 §4.10 EtherCAT 家族命令表与 `ss_dlg.py` 条目；几何基线（125% 缩放 / 1920×1080）标注为实测基线、换环境先重测；新增 `README.md` 与 `requirements.txt`。实测结论无改动。 |
| 0.10.0 | 2026-11-08 | **EtherCAT 组态"右击插入"整条打通并端到端验收**（某 EtherCAT 组态工程：16 步计划 / 21 个从站 / 8 种型号，保存后与源归档逐条比对 `RESULT EXACT`）。① **ESI 库路线**（新 `scripts/ss_esi.py`）：主设备右键 `显示ESI库` → 顶层窗 `ESI库`（`ProfileLibraryView` / `EsiProfileTreeView`）→ `installFileButton` → Win32 `#32770`（`Edit id=1148` / 按钮 `id=1`）→ `find` 复核；**多实例时安装必被拒**（「因为正在运行多个Sysmac Studio，无法执行安装」），这条 MessageBox 是 `Name='Sysmac Studio'` + `AutomationId='MessageBoxView'`（ClassName 只是 `Window`）。实测装入汇川 SV660N 后 `SV660` 命中 `InoSV660N Rev:0x00010000 | SV660N_1Axis_00916`（新 [pitfalls §68](references/pitfalls.md)）。② **三条插入语义**（新 §69）：`GX-JC06(IN,X2,X3) Main device` **成对插入**（自动在 `Internal Port` 下再挂一个 Sub，从设备数量 +2）；插入落在所选端口的**头部** ⇒ 菊花链必须**倒序**写计划；**每插一个都自动重排全网络节点号** ⇒ 节点号最后用 `renumber` 统一写。③ **选位置的两步**：`SelectionItemPattern.Select()` + 真实左键点**行标题带**——行矩形是**整棵子树高度**（实测 `(275,186,902,1950)`），点中心会落到子行；`find_by_type(行,'TextControl')` 会把所有子孙文字扫出来，导致改名/改节点号落到祖先身上（本轮真踩到，修法 `row_texts()` 按子 TreeItem 矩形过滤），新 [pitfalls §70](references/pitfalls.md)。④ **工具箱搜索只匹配设备名**：`GX-JC06` 4 条 / `GX-JC06(IN,X2,X3) Main device` 0 条 / `CTEU` 1 条 / `SV660` 1 条 ⇒ 计划表 `kw` 写短型号 + `pick` 子串挑行；且 **「工具箱」与「查找和替换」是同一组 `PaneControl` 页签**（不是 `TabItemControl`），切过去时 `SearchTextBox`/`ItemListBox` 直接从 UIA 消失，脚本必须先 `ensure_toolbox()`（新 §71）。⑤ **组态只在进程内存里**：本轮建完 16 步没保存，进程退出后 `.smc2` mtime 未变、归档 `flat children of Proxy = 0`，整轮白做 ⇒ `ss_ecat_build.py` 新增 `--save-each`（每步走 `文件(F)>保存`），新 §72。⑥ **拓扑树按视口实化**：树高 1950 px / 视口约 700 px，从根 `walk()` 在源实例拿 51 行、在目标实例只拿 33 行（某分支 7 个从站整段缺失，归档 `cmp` 报 7 个 MISSING，而归档/renumber/从设备数量都对）⇒ 核结构从目标行 `ScrollIntoView`+`Expand` 后 `walk`（内置 `ss_ectree.py subtree`），核整份组态直接读归档，新 §73。⑦ 脚本：`ss_ecat_build.py` 0.3.0（insert/renumber/verify + `--save-each`/`--only`，2 次重试读回、`sweep_expand` 后再校验）、新 `ss_esi.py` 0.1.0、`ss_ecat_archive.py cmp`（只比 `(subtype, 节点标签)`，因为 `diff` 模式会把实体 `name` 算进签名而天然全红）、`ss_ectree.py subtree`。⑧ 工程侧：目标工程 `.smc2` 已落盘（sha `<保存前 sha>` → `<保存后 sha>`），归档 21 行与源逐条一致。⑨ **Git Bash 会改写 `tasklist /FI|/FO|/NH`** 成 `C:/Program Files/Git/FI` ⇒ 无输出、误判"进程没了/组态丢了"（用 `//FI` 或 PowerShell `Get-Process`），且同一 `.smc2` 被第二个实例打开会锁文件报「可能被该应用程序的另一个实例锁定」，新 [pitfalls §74](references/pitfalls.md)。 |
| 0.9.0 | 2026-11-07 | **落盘通道打通 + `NexAxisPDOMappingTable` 的旧结论作废**。① `ss_save.py` 0.2.0：`--esc N`（保存前关残留弹层）与 `--menu`（`文件(F)>保存` 走 UIA `Expand()`+点击，实测 +1s 落盘），弹层枚举补 `IsWindowVisible`/`GWL_EXSTYLE` 与 MenuItem/List 子节点；实测**没关掉的下拉是独立顶层 `HwndWrapper[SysmacStudio.exe;;…]` 93×31 小窗，会吃掉 `Ctrl+S`**（两轮 `FILE UNCHANGED` 的四个轮询点都能看到它），而菜单路线不受影响（新 [pitfalls.md §66](references/pitfalls.md)）。② **菜单项真实 `Name` 带访问键后缀**（`保存(S)`/`另存为(A)...`/`关闭(C)`），`ss.py menu_item(...,'保存')` 精确匹配必然 not found；`bare()` 正则剥后缀后比较。③ **`toggleUnit` 是 `Button`（`PAT=Toggle`），`'+'/'-'` 在它子节点 `Text id='toggleButton'` 上**（`ss_axpdo.py peek` 抓到的原文，已写进 [control-tree.md §17.2](references/control-tree.md)）：老 `row_info` 按 Text+id 找 ⇒ 永远找不到 ⇒ `expand_all/collapse_all` 走"找不到就当已到位"的捷径，**日志报成功、一次没点**，这是本轮"折叠态对不上"的真因。修好后 `expand/fold` 真点击（`round N: … pattern -> '-'`），并发现**第一遍读值会说谎**（刚 `expand_groups`/`raise_tab` 完读到 `'-'`，2 s 后与最终复查都是 `'+'`）⇒ 新增 `stable_glyphs()` 两次一致才判（新 [pitfalls.md §67](references/pitfalls.md)）。④ `ss_axpdo.page()` 补两件事：`ss_axis.expand_groups()`（PDO 表藏在**第二层** `详细设置` Expander 后，关掉页签再开会回到折叠态 ⇒ `NO DATAGRID`）+ `raise_tab`/`verify_axis`（文档已开 ≠ 该页在前面，命中测试会读到别的轴，轴号不符直接停手）；`grid_ready()` 处理"DataGrid 在树里但 0 行实化"；新增只读命令 `toggles`/`peek`。⑤ **§65.2 原结论（"该串 = 保存那一刻的折叠态"）被证伪**：真折叠/真展开/关页签三种做法后保存，归档那串**一字不变**；它只在"该轴 PDO 单元格被界面提交过"时出现，**只增不减、界面无清除通道** ⇒ 验收时与 `IsEnabled=False` 那类并列"如实报告"，recipes §R 第 5 步整段改写。⑥ 实测 `expand` 之后**立刻** `collect` 会把有值的行读成空（截图上 `6040h-00.0(Controlword)`，日志 `""`）⇒ "读回为空"不等于"没写进去"，最终以 `ss_axcmp.py` 归档为准。⑦ 本轮工程验收：`ss_axcmp` 从 `differing=171` 降到 **11**（5 条 `NexAxisPDOMappingTable` + 轴0 的 5 条未使用轴参数 + 轴1 `NexAxisStartDirection`，后 6 条在源与副本里都 `IsEnabled=False`）；`编译控制器(B)` 后截图读到 **0 错误 / 0 警告**，但 `ss_build.py totals/list` 在"编译面板以页签条停靠"的形状下读不到表头（已进待验证清单）。⑧ 收尾复验（证据落盘 `axcmp_final.txt`，原始记录不随 Skill 发布、需要时按 recipes §R 重跑验收；副本 `.smc2` 磁盘 sha 与最后一次 `ss_save.py --menu` 记的一致）：11 条差异的逐轴形状是 **轴0 五条**（`AxisType`/`UnitsNumerator 262144`/`UnitsDenominator 2`/`MaxVelocity 100`/`MaxJogVelocity 1`，两份都 `NexAxisUseAxis='…NotChangable'` + `en=False`）+ **轴1 两条**（`NexAxisStartDirection` 灰置、`PDOMappingTable`）+ **轴2/3/5 各一条**、**轴4 一条但方向相反**（源有该串、副本空）⇒ 再次印证它是提交历史标记而非折叠态，两类都归"如实报告"，不要为对齐它去手改归档。 |
| 0.8.0 | 2026-11-07 | **运动控制轴"照抄参数"路线整条打通**（某运动控制工程 轴0–轴5 实测：逐个建轴 → 轴设置文档逐参数写 → 轴设置表换从站绑定 → PDO 过程数据逐行写 → 两份 `.smc2` 逐参数验收），新配方 [recipes.md §R](references/recipes.md#r-轴从站绑定与-pdo-过程数据映射2026-11-07-实测)、新控件地图 [control-tree.md §17](references/control-tree.md#17-轴设置表winforms与轴-pdo-过程数据2026-11-07-实测)、新坑 [pitfalls.md §59~§65](references/pitfalls.md)。要点：① **轴页顶部 `输出设备1` 组合框只显不写**（`set_combo`/`Expand`+点项/键入/`Value`/真双击五种机制全试过，模型纹丝不动，§59）——真句柄在**轴设置表**里。② **`轴设置表` 是 WinForms/WindowsFormsHost，UIA 到 `AxisGrid` 就断**（一个单元格都不暴露），但**真点一格会浮出真的 `WindowsForms10.COMBOBOX.app.*` 子 HWND**：`CB_GETCOUNT=34`/`CB_GETCURSEL` 即模型真值，列表里是全部 EtherCAT 从站；提交必须用**关闭态+有焦点**的 `{UP}`/`{DOWN}`（触发 `CBN_SELCHANGE`）+ `{ENTER}`，**`CB_SETCURSEL` 禁用**（只改标题不发通知）；`SendMessageW` 要手动复位 `restype=c_ssize_t`/`argtypes`，`CB_GETLBTEXT` 的缓冲要 `ctypes.cast(b, c_void_p)`（§60、§17.1）。③ **换 `输出设备` 会清空该轴全部 PDO 映射** ⇒ 顺序只能"先设备后过程数据"，且 `set_combo` 必须**值已对就跳过**（幂等），否则越写越少（§61）。④ `过程数据` 下拉**一项 = 一个位**（实测某伺服 257 项，文本 `'<obj>h-<sub>.<bit>(<Receive|Transmit> PDO mapping N_<名>_<obj>_<sub>)'`）⇒ 匹配只能 `caption.startswith(key + '(')`，`60FDh-00.1` 是 `60FDh-00.10` 的子串，选错位**静默发生**（§62、§17.3）。⑤ 虚拟化弹层**一次只实化约 60 项**，其余 `IsOffscreen=True` 且矩形过期；`SelectionItemPattern` 是 `None`、`ScrollItemPattern` 在 uiautomation 包装上直接 `AttributeError` ⇒ UIA 的 Select/ScrollIntoView **两条正规路都不存在**；下拉**打开即定位到当前选中项**（未分配=列表底部）⇒ 扫描必须**先向上再向下** + stuck 检测 + 滚轮落在**弹层自身矩形中心** + 终极兜底"真点开拿焦点后把键名敲进去"（WPF 文本检索跳项）再点/`Enter`。实测 `ok=17 bad=0 miss=0`（§64）。⑥ **`.NET` 未处理异常框会冻住后面所有 UIA**——"脚本跑很久没结束"先怀疑它；只点 `继续(C)`，`详细信息`/关闭永不碰，点完实例存活、已写的值还在（§63，新脚本 `ss_crashdlg.py`）。⑦ 两条只有读归档才知道的真相：**编译不会把空的 `PDOPathName`/`ODBitLocation` 补出来**；`NexAxisPDOMappingTable` 的值就是**三个 PDO 组的折叠态**（源有该串而目标无 / 目标展开过就冒出该串，双向验证过）（§65）。⑧ `IsEnabled=False` 的参数（每轴 `NexAxisStartDirection`、未使用轴的型号/单位分子分母/最大速度/最大点动速度）**界面上根本没有开关**，只能如实报告，不要手改归档（§17.4）。脚本侧新增 `ss_axtable.py`（get/set/probe/geom）、`ss_crashdlg.py`，并把本轮工作脚本提升进 Skill：`ss_axisparams.py`（离线摊平轴 XML）、`ss_axcmp.py`（两份工程逐参数对比 = 唯一验收口）、`ss_axisplan.py`（源归档 + 目标网格转储 → 写计划）、`ss_axpdo.py` 0.5.0（expand/collect/apply/rows/fold，`pick_prefix` 五条硬约束）；新 §4.9 表格串起整条轴链路，§1 能力表补 2 行能做 / 3 行不能做。`ss_axpdo.py fold`（折回三组以对齐 `NexAxisPDOMappingTable`）按 `expand_all` 对称写成，**尚未实测**，用前先在一根轴上验证。补 `ss_save.py`（Skill 此前**没有任何落盘通道**：记 sha256 → 真 `Ctrl+S` → 轮询到文件变化才认"保存成功"，弹层只记录不动手）。再补一条只有比对归档才看得出的事实：**`NexAxisPDOMappingTable` 记的是点 toggle 的先后顺序，不是集合**（同一份源工程里 轴4 是 `output,input,digital input`、轴27 是反过来的 `digital input,input,output`）⇒ 收尾按源顺序点，否则该项永远对不上（§65.2b）。 |
| 0.7.3 | 2026-11-06 | **POU 变量表与模式分布测通**（`open --expand` / `--pat`，落盘 `openG.txt`/`openH.txt`/`openF.txt`，写进 [control-tree.md §16.7](references/control-tree.md)）。① `--pat` 实测：**`textEditor`(`SyntaxEditor`) 只暴露 `Text`，没有 `Value`** ⇒ `ValuePattern.SetValue` 这条路不存在，ST 写入仍是"点 + 键盘/剪贴板"；`DocumentWindow` 无任何模式；**`closeButton` 挂着 `Invoke` 却 `Invoke()` 抛异常**（所以日志恒 `closed(click)`，旧措辞"拒绝 Invoke"已改成这句可复现的描述）；`EditorView-Right`=`Scroll`、`ScrollBar`=`RangeValue`、`Expander`=`ExpandCollapse`、`HeaderSite`=`Toggle`。② `open … --expand` 展开 ST/LD 顶部那条 `变量` `Expander` 后，**整张 POU 变量表第一次进 UIA 树**：`VariablesView` → `UsingExpander('命名空间 - 使用')` + `VariableGroupTabControl` → `DataGrid id='DefaultGroupDataGrid' cls='CellEditor'`（7 列 名称/数据类型/初始值/分配到/保持/常量/注释）→ `DataItem cls='DataGridRow' Name='…VariableViewModel'`（25 px）。**格子契约**（对上 pitfalls §22 的长期痛点）：有值格 `Name`=`HelpText`=值、子 `Text` 同串；**空格 `Name` 形如 `项: <ViewModel>，列显示索引: N` 且 `HelpText` 空**——这就是"空名行"的机器可读定位法；保持/常量两格是 `CheckBox`（索引 4/5）；行在屏外整行带 `off`。③ 变量页签集合按 POU 种类变（程序=内部/外部；功能=内部/输入/输出/外部/返回值；功能块=内部/输入/输出/外部），**只有选中的页签里网格才实化**。④ 反面教训已写进 §16.7/§1：设置页 6 个 `subsectionExpander` **本来就展开**（前后逐行相同 138/138），`--expand` 治不了"读不到某设置项"，那是节没切对；全局变量页 `--expand` 打到 `GroupingSelectionComboBox`，换版本有把下拉卡住的风险。⑤ 顺带露出 `InstanceSelectorView`（`Text '请选择一个监测实例。'` + `Button id='SelectButton'` + `List id='InstanceListBox'`，离线恒 `off`）与 ST 的 4 个隐藏 margin、`跳转:` 控件行。脚本侧：`open` 新增 `--expand`（`expand_inside()`，上限 8 个宿主 / 2500 个元素 / 深度 14，逐个 `Expand()` 后重走该页），头注释与 §4.7 同步；[extending.md](references/extending.md) 回归第 14 条改为带 `--expand` 的三页组合并新增第 15 条（6 个打不开节点的取证基线），待验证清单里"ST 编辑器读写"降级为"`TextPattern` 能否读出全文"。 |
| 0.7.2 | 2026-11-06 | **编辑器内部形状测绘完成**（`ss_uimap.py open/close` 实测 15 类页面，原始落盘 `openA/B/C/E/D.txt`，写进 [control-tree.md §16](references/control-tree.md)）。① 通用外壳契约：编辑器实例是 `Pane cls='DocumentWindow'`，**`Name` = 文档名**（多语言 POU 是 `PrgMain - PRG_Example` 这种"名 - 父名"，必须精确匹配），它自己的矩形只是页签，内容区永远是 `(249,134 1388x632)` 那个 `Custom`；`closeButton` **拒绝 `InvokePattern`**，只能 `force_foreground` + 按矩形真点，关"没编辑过的页"**不弹保存框、不冒新窗口**。② ST = `StructuredTextView`、LD = `LadderProgramView`，**看页面根类名就能分流**；两边唯一可寻址的书写目标都是 `Text id='textEditor' cls='SyntaxEditor'`（无可用 ValuePattern）；LD 每梯是 `Text id='PART_TextBlock' Name='STMultiSection(<GUID>)'`，**GUID 跨保存不稳定，不能当锚**；变量声明区是默认折叠的 `Expander`，里面不在 UIA 树。③ 设置页家族：5/9 个页面根类是 `ConfigurationView`，左导航 `SectionView`→52×52 `Button`→`IconView`，**图标 id 就是节锚**（`CPU_setting`/`fins`/`eventlevel_setting_normal`/`CJunit_memory_setting_L_normal`/`opcua_svr_setting_L_normal`/`DB_service_setting_L_normal`），`任务设置` 例外——6 个节没有 id、只有类名 `BaseTask*`；右侧正文类名逐页不同（`…SectionDetailsView`），按矩形+`TitleTextBlock` 认；设置项一层 = 一行 `ComponentsFieldView`（标签 `Text` + `RadioButton`/`Edit`/`ComboBox` + 单位 `Text`），**这些页没有"应用/确定"，改完即入工程**。④ 组态页最有用的发现：`ParameterSettingTable` 的 `ListItem` **类名后缀直接说明读写方式**（`String`/`Label`(只读)/`Integer`/`Boolean`+`ComboBox id='editControl'`/`Enumerable`+同上/`LabelWithButton`+`Button id='OpenTransmissionDelayTimeSetting'` 开子对话框→留给 #31）；I/O 映射单元格**按 `Name` 里的"列显示索引"+左边缘认列，序号会跳号**（实测 0,1,2,3,5,7,8,9 对 8 个表头）。⑤ 全局变量页必须 `--all`：`TabItem '全局'` 处于 `off`，默认遍历把整棵子树裁光（10 行 vs 52 行）；`GlobalNamespaceGroupDataGrid`(`cls='CellEditor'`) 8 列全带 `CellEditor.Internals.Sorting`（点表头=排序），空表时外面盖一个 `Button '数据为空。点击此处添加项。'`。⑥ **6 个节点在本工程打不开页**（`0.4.0 轴设置`/`0.4.1 轴组设置`/`0.5 Cam数据设置`/`0.8 数据跟踪设置`/`1.2.0 PrimaryTask`/`1.2.1 TempCtrlTask`），取证字段（`tree focus=True`、`row hit by click=True/True`、`rows 85->85`、`new windows=[]`）证明不是定位失败而是"没有实体就没有文档"；§15 那份轴设置表来自**有轴实体的工程**。脚本侧新增 `open`（Enter→取消选中+真双击 两级兜底、逐页 walk、`--close`/`--fit`/`--all`/`--depth`）与 `close`（按 Name 或 `--all`，记 `# before/after` 文档名）；`close_document` 的返回值细化为 `no pane`/`no button`/`invoke failed`/`closed`/`closed(click)`/`still open`。§1 能力表新增一行（含两条新硬边界：打不开的容器节点、默认遍历会裁掉 `off` 子树）并把"数据类型表行文字"从不能改成能；§4.7 补 `open`/`close` 两行与第 ④ 条前提；§5 骨架标出 `DocumentWindow`/页面根类名；[extending.md](references/extending.md) 回归清单加第 14 条。 |
| 0.7.1 | 2026-11-06 | **主窗口骨架测绘完成**（`ss_uimap.py panels` 全量落盘 `panels01/panels02.txt`，写进 [control-tree.md](references/control-tree.md) §3.1/§4/§5/§6.1/§9.1/§10/§10.1）：`ControllerView` 才是工作区整页的根；6 条 ToolBar 逐按钮与**离线灰置基线**（33 个命令，修正 §5 旧表的 3 个错映射：`terminal_window`=输出窗口、`search`=交叉索引窗口、`reset`=缩放到合适大小，补 `zoomIn`/`zoomOut`，外层 `Button` 的中文在 **HelpText**）；四个停靠容器**只能按矩形认身份**；编译面板实测形状（错误/警告数字是那两个按钮的**子 Text**、表头 5 列里前两列无标题、`FilterResultList` 是筛选器网格不是错误网格）；状态栏只有 `Text(0×0)+ProgressBar`，**空闲时 `IsOffscreen=True`** ⇒ 忙闲判据改成 off→on；工具箱 `searchCombo.HelpText` **就是搜索语法说明书**。**两条新硬约束**：① 工程打开后 `StartPageView` 整套元素仍以 disabled+off 留在树上，按 id/Name 找元素必须过滤 `IsEnabled`/`IsOffscreen`，其中 `LicenceToggle`/`EditionNameTextBox`/`DaysLeft*` 属许可区，任何情况下不读写；② 窗口底边默认超屏 271px，状态栏/输出·编译页签/`筛选器` 读得到点不到，`--fit` 平移量为 (-26,-279)（[pitfalls.md §53](references/pitfalls.md)）。脚本侧：`panels` 新增 `--fit`（结束时 `restore_rect` 还原），头注释补 `panels`/`treerows` 两条更正（`TVM_EXPAND` 只对两根有效）。 |
| 0.7.0 | 2026-11-06 | **工程树节点类型 × 右键菜单全量测绘**（84 节点，新 [references/tree-node-menus.md](references/tree-node-menus.md)）：9 类节点**根本没有菜单**（两个根、`控制器设置`/`运动控制设置`/`主机连接设置`/`数据`/`任务` 容器、`PrimaryTask`/`TempCtrlTask`）；配置叶子的菜单里**没有** `复制(C)` —— 这是"配置搬不动"的机制级解释；`轴设置`/`轴组设置`/`Cam数据设置` 有 `导入(I)`/`导出(E)`（跨工程搬组态参数的界面入口）；POU 容器 vs 实体两种形状、`上移/下移` 只由同级位置决定、`PrgMain` 禁 `剪切/删除`（要搬程序搬 `1.0.0.0`）。**节点文字改为可安全读**（`TVM_GETITEMW 0x113E` + 远端 `TVITEMW`/文本缓冲，新命令 `ss_uimap.py treelabels`），推翻 0.x 以来"树行读不到文字"。`ss_uimap.py` 首次进 Skill 文档（新 §4.7 全命令表）。新坑 §48 Alt 轻点吞点击、§49 `VK_APPS` 给的是窗口系统菜单（`#32768`）+ `GetGUIThreadInfo` 焦点判据、§50 点根行折叠整段导致序号错位、§51 `PostMessage(WM_CONTEXTMENU)` 永久无效、§52 展开要靠 caret+真实 `VK_RIGHT`、§53 行几何三前提（26px / 一滚轮 3 行 / `pane_bounds`+`--fit` / `XamlExplorerHostIslandWindow` 抢 `WindowFromPoint`）、§54 读名字的安全写法、§55 弹层子菜单打不开 + `menuitems=` 计数含义。修正 [project-tree.md](references/project-tree.md) §1/§2/§3.2/§3.3/§7 与本页 §1 里被本轮推翻的旧结论；`probe_select.py` 只发消息复测坐实 **`TVM_SELECTITEM` 能选中**（`TVGN_CARET` 回读一致 + 真给 `TVIS_SELECTED` + 取消上一行 + 滚进视野 + 最小化下有效），**作废 0.4.2 的"消息到不了这棵树"**（新 [pitfalls.md §56](references/pitfalls.md)，同步修 [control-tree.md §6](references/control-tree.md)、[architecture.md §7](references/architecture.md)、[extending.md §0](references/extending.md) 与 `ss_tree*.py` 头注释）。 | 
| 0.6.0 | 2026-11-06 | 修正程序注入模型（重大）：程序实体必须是 `Program / MultipartLadder`，程序变量表是 `Variables / Ladder`（子实体只有 `SourceHolder`），ST 代码放在段的 `PouBody / Ladder` 里的 `Inline / StructuredText`（`IST` 内联块，配套文件是 BOM + 梯图 JSON）。旧写法 `Program / StructuredText` 能打开能编译，但整张程序变量表不被识别、程序内变量全报未定义。新增错误跟踪日志诊断 `%APPDATA%\OMRON\CXAP\Log\SysmacStudioErrorTrace.log`（`Extended data is not an instance of VariableGroups` / `KeyNotFoundException`），新增"假 0 错"判据（CPU 增长 + 面板计数 + 日志字节差三条同时成立），锁屏下的 InvokePattern + 提权执行通道免前台编译路线，`LREAL→REAL` 必须显式转换。详见 [offline-surgery.md §8](references/offline-surgery.md#8-从零新建-poust-功能块--程序--任务--实测可行2026-11-06-修订)、[pitfalls.md §45~§47](references/pitfalls.md)。 |
| 0.5.3 | 2026-10-31 | 按录制原始快照校正轴页顶部布局：顶部是 **2~3 个** `ComboBoxControl`（实测 y=247/270/377），轴类型/关联节点**按展开后的选项内容认**（含 `伺服器轴` = 类型，以 `节点` 开头 = 关联节点），不能按序号硬取；下拉项查找改为扫全部弹层根（顶层弹窗 + 主树里的 `Window(cls=Popup)`），首项 top ≈ 组合框 bottom + 0~2、项可宽于组合框；数值组标签读不到时按行序兜底（`速度/加速度/减速度` 自上而下 = 最大速度/最大加速度/最大减速度）。详见 [recipes.md §Q](references/recipes.md)、[control-tree.md §15](references/control-tree.md)。 |
| 0.5.2 | 2026-10-31 | 运动控制轴路线定稿（新配方 [recipes.md §Q](references/recipes.md)、[control-tree.md §15](references/control-tree.md)、[pitfalls.md §42](references/pitfalls.md)）：建轴走工程树 `轴设置` **右键 → 添加 → 子菜单第一项**（弃用主菜单 `插入(I) > 轴设置(A)` 对话框）；新行双击/`F2` 行内重命名（临时 `EditControl` 按“落在树矩形内”找）；轴页两个顶部组合框 = 轴类型 / 关联节点，左侧导航 `axes_scale`/`axes_dynamics`/`axes_io`/`axes_limit`/`count_mode_set`/`servo`，右侧 `GroupControl '单元'/'行程距离'/'速度/加速度/减速度'`；**下拉项不在组合框子节点里**（挂在主窗口 `Window(cls=Popup)>Pane>ListItem`）。轴参数真值从轴 XML `NexAxis*` 的 `<CurrentValue>` 读，`.oem` 里是 `AxisSettingEntity`。 |
| 0.1.0 | 2026-10-30 | 首版：非官方声明与局限、技术形态与 UIPI/DPI/会话前提、启动页/向导/工作区/工具栏/菜单/工程树/工具箱控件地图、工程树按路径操作、项目文件导入另存为导出与校验、组态与编程配方、坑清单、扩展与回归流程 |
| 0.2.0 | 2026-10-30 | 工程树定位改为**消息驱动**（`TVM_SELECTITEM` + 光标回读），实测到叶子且锁屏可用；修正"UIA 暴露全部可见行"为**只暴露根节点**；实测 `TVM_EXPAND` 只对根节点有效（深层靠截图像素确认）；废弃键盘下降方案；补充单实体复制基线 10,376 B；修正失效锚点 |
| 0.3.0 | 2026-10-30 | 新增 [library-and-tasks.md](references/library-and-tasks.md)：`工程>库` 子菜单两世界（`库设置/创建库` 仅库工程可用）、`显示索引→库索引→+→引用库文件→引用库提示→确定` 全流程与几何、`任务设置→程序分配设置` 逐行 `+` 的驱动写法（按钮每行下移 22px）、变量表编辑与"空名行删不掉"、读编译结果。新坑 §20 弹出菜单进程级罢工（鼠标/打字仍正常，`SendInput` 成功但菜单只聚焦）、§21 工具栏按钮文字在 `HelpText`、§22 空名行会被导出。修正导出对话框 `EditControl` 名为 `文件名:`（不是 `文件名(N):`）。补第二个重建基准（1548→318 条目、Program 11→5、DataType 35→15、编译 6890 错误）与"架构限制 vs 漏搬"的判读 |
| 0.3.1 | 2026-10-30 | 编译面板**实测可全量读**（`DataGridControl` 靠 `top>630` 定位 + `ScrollPattern` 逐屏 + UTF-8 落盘；头部 `TextControl` 直接给 `N 错误/M 警告`），新增 `scripts/ss_build.py`；导出流程**完整跑通并脚本化**（`scripts/ss_export.py`：菜单栏坐标 + 键 `E` + `SetForegroundWindow(对话框)` + aid `1001` 剪贴板粘贴中文 + aid `1` 保存 + `确认另存为 是(Y)`），并**修正 0.3.0 的错**：该 Edit 不支持 `ValuePattern.SetValue`（抛 `COMError -2147220992`）。新坑 §23 菜单点不开先查残留模态窗（菜单项本身可枚举可点，实测 `文件(F)`/`文件(_F)`）/ 弹窗只枚举非主窗口、§24 `grab` 截图不含弹窗、§25 导出三件套、§26 编译列表读法。新配方 §L 导出、§M 错误分类、§N 建数据类型命名空间。补 EtherCAT 跨工程 **5 条路径全失败**的实测表与"库内同名类型撞名 → 100×2 条错误"的判读。新增 [control-tree §14 数据类型页](references/control-tree.md#14-数据类型页结构体--命名空间)。第三个重建基准：385 错误/0 警告、zip 条目 1548→364 |
| 0.3.2 | 2026-10-30 | 重建工程**收敛到 0 错误/0 警告**并复验。新增 [offline-surgery.md](references/offline-surgery.md)：`.smc2`/`.slr` 是 zip，实体树在 `<GUID>.oem`，**按实体 id 基名搬配套文件**即可跨工程移植 EtherCAT（251 id/158 文件）、安全 CPU（197 id/509 文件）、数据类型页；子树内 GUID 自洽、跨工程外部引用可忽略；`.oem` 必须带 BOM+声明；**加密 `PouBody` 不可改文本 → 参数名不一致改调用点**。修正 §1 的"组态搬不动"：**界面搬不动 ≠ 不能重建**。新坑 §27 提权窗口对中权限注入静默无效（判定 `TokenElevation`）、§28 DPI 虚拟化导致两套坐标（768×503 vs 960×629）、§29 对文件列表单元格 `SetValue` 会触发就地重命名（危险，只点不写）、§30 提权守护进程单任务 900 s 超时。新配方 §O EtherCAT 编辑器组态、§P 收敛到 0 错后的导出复验 |
| 0.4.0 | 2026-10-31 | 一键重建脚本实测回写：**EtherCAT 关键字框有固定 id `SearchTextBox`**、**搜索结果可 UIA 读**（`List id=ItemListBox`，行高 38px）→ 不再靠截图量坐标；**输入法会吞 `SendKeys` ASCII**，文本统一剪贴板粘贴（新坑 §31）；表格未关的下拉会吃掉第一次菜单点击（§32）；`TVM_GETITEMRECT` 必须填 `hItem`、跨进程 `SetFocus` 必须 `AttachThreadInput`（§33）。修正 `工程>库` 子菜单打开方式：悬停展开二级菜单，旧的 `menu_click` 二级写法永远找不到项；`库索引` 可能是 WPF 窗口，不能只按 `#32770` 找。补全 key 控件 id（全局变量网格 `GlobalNamespaceGroupDataGrid`、数据类型 `PART_ListView`、拓扑 `TopologyView`）。 |
| 0.4.1 | 2026-10-31 | 结构体成员入口定稿：**不用开成员页**，选中结构体行右键 `新建成员(M)` 即在**同一张 `PART_ListView`** 里插入子行，就地写 名称/Tab/类型/Enter；成员存在性只能按**行第一列名称全等**判定（结构体行与成员行同表）。原先"双击名称格开成员页"降级为兜底路径。另：悬着的 WPF 下拉在 UIA 里是 `Window/ClassName=Popup`（Win32 顶层窗类名仍是 `HwndWrapper`，`EnumWindows` 过滤抓不到），新增 `ssk.dismiss_popups()`：ESC → 点主菜单条右侧空白 → 复检；文件对话框取文件名框必须排除"搜索"框（§32）。 |
| 0.4.2 | 2026-10-31 | 工程树交互定稿：**只能真实鼠标**（`TVM_SELECTITEM`/方向键/`WM_KEYDOWN VK_RETURN` 都到不了树），可见行 = `TVGN_FIRSTVISIBLE(5)`/`TVGN_NEXTVISIBLE(6)`，行高 26px，`y=客户区top+26i+13`；**双击未选中行=打开，双击已选中行=行内重命名**（修正 §7）；`TVM_GETITEMRECT` 按 `CommCtrl.h` 真实宏修正（wParam=fItemRect，lParam=RECT* 且首字段先放 `HTREEITEM`），两参数对调会**把软件打崩**（§33）；库索引 `+` 稳定 id=`CreateLibraryReference`，成功判据改为"对话框里出现库文件名"；残留 `库索引/引用库` 模态窗会让树双击完全无反应（§23.4）；批处理 CRLF / `-ArgumentList ''` / 单实例互斥（§34）；Sysmac 可中权限运行、UIPI 只挡"低→高"注入（§35）。 |
| 0.4.3 | 2026-10-31 | EtherCAT 组态界面路线补完 + 输入法坑扩展：**`SendKeys('^a')` 不认 `^` 前缀**，会把 `^a` 原样敲进框里（导出文件名变成 `x.smc2^a^v.smc2`），组合键必须用真实 `keybd_event`（§36）；拓扑树**默认只暴露第一行**，从站行判据 = 直接子节点含 `EditControl aid=editBox`，**选中行按 VK_RIGHT 后**端口行（`X2`/`X3`/`Internal Port`）与后续从站行才进入 UIA（§37、control-tree §14.1）；插入从站改走**工具箱结果右键 →「插入(I)」**，空网络有效、已有从站时需先选端口行，一次插入 `GX-JC06 Main` 会**同时产生 Main+Sub 两个 SlaveProxy**，删除走从站行右键「删除(D)」且无确认框；**真值只看导出文件**：`.smc2` 内 `.oem` 的 `subtype="SlaveProxy"` DN 列表（§38）；修正 §35——本机 Sysmac 实测以 **High** 完整性运行（`integrity_of`），提权仍弹一次 UAC，被拒报 `The operation was canceled by the user`（§39）。§O 配方整段重写。 |
| 0.4.4 | 2026-10-31 | 新建工程后必须点掉 WPF 说明框：点「创建」会弹 `HwndWrapper` 顶层小窗（「启用此功能可以将工程编辑直接保存到工程文件中…」，只有「确定」），不点它工程就一直停在启动页、标题永不出现工程名，后面所有步骤连锁报“工程树不存在”（§40）。等待“工程建立”的循环里顺手 `auto_ok_popup()`，只点 `确定`/`OK`，不碰 `是(Y)`/`否(N)`。 |
| 0.5.1 | 2026-10-31 | 修复录制器卡死：低级钩子回调里不做 UIA/写盘/打印，改成“钩子入队 + worker 线程解析”。按 Win 键/开始菜单一度能把控制台永久卡死（跨进程 UIA 与钩子返回互锁），现在输入通道始终可响应；键盘的“只录 Sysmac”判断改用 worker 缓存的前台 pid。见 [pitfalls.md §41](references/pitfalls.md)、[recording.md §1.1](references/recording.md)。 |
| 0.5.0 | 2026-10-31 | 新增 `scripts/ss_record.py`：提权录制手工操作到 JSON/JSONL——点击在按下前快照 UIA 元素路径（含祖先、行内文本、值），记录拖拽起止、键入/粘贴/快捷键、焦点、前台切换与每个顶层窗口的控件树；`actions` 把“点击+其后输入”合并成可回放的步骤。用于界面能手工做、脚本做不出的路线（EtherCAT 展开节点→选中插入点→插入、特殊右键菜单、向导）。限制：只记录输入不记录结果；中文输入法靠 `value` 回读恢复；RuntimeId 不稳定；菜单是独立顶层窗口。见 [references/recording.md](references/recording.md)。 |
