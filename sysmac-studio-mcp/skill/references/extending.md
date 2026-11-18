# 扩展知识：怎么自己测、怎么记回来

本 Skill 只能靠实测生长。换版本、换机器、遇到没见过的对话框时，按这里的流程补测并回写。

## 0. 铁律

1. **只读优先**：先 `wins` / `state` / `dump` / `popups` / `struct` / `rows`，能把结构看清楚，再动写操作。
2. **读树节点文字只用 `ss_uimap.py treelabels`**：`TVM_GETITEMW(0x113E)` 且 `TVITEMW` + 文本缓冲都 `VirtualAllocEx` 到 Sysmac 里。**别自己发 ANSI 变体 `0x110C`、别把本地指针当 `pszText` 传过去**——那两种写法实测把软件直接打崩（[pitfalls.md §54](pitfalls.md)）。
3. **写操作前先保存工程**。尤其"导入"会关掉当前工程。
4. **测出来才写**：没测过的推断只能进 §4 待验证清单，不能写进正文当事实。
5. 每次回写都更新 `SKILL.md` 的 `version` 与更新记录表，并在本文档末尾追加一条。

## 1. 版本回归清单（换机器 / 升级后跑一遍）

先跑**不依赖 Sysmac 的单测**（Skill 目录下）：`python -m unittest discover -s tests -p "test_*.py"`，应全过——覆盖计数解析 / 保存判定 / 归档校验等纯逻辑；它不证明真机上找得到控件，UI 行为仍按下表回归。

| # | 检查 | 期望 | 失败意味着 |
| --- | --- | --- | --- |
| 1 | `ss.py wins` | 列出 `SysmacStudio.exe` 窗口，标题含工程名 | 进程名变了 / 没提权 |
| 2 | `ss.py state <pid>` | `mode` 是 `Online`/`Offline`，`editor` 数值合理 | UIA 树结构变了 |
| 3 | `ss.py dump <pid> out.txt` | 行数上百（工作区 ~448 节点），有 `MainDockSite` / `MenuControl` / `ToolBarControl` | 控件 ID 改了 |
| 4 | `ss_tree.py struct <pid> 2` | 有根节点且子节点数 > 0 | 工程树宿主类名变了 |
| 5 | `ss_tree.py rows <pid>` | 行数 == 根节点数（典型 2） | 若行数 > 2，说明新版开始暴露子行，需重写定位策略 |
| 6 | `ss_tree.py goto <pid> 1.0` | 打印 `caret=<句柄> path=[1, 0] children=<n>` 且退出码 0 | `TVM_SELECTITEM`/光标语义变化 |
| 7 | `ss_tree.py expand <pid> 0` | `expand_ret=1`（未展开时），截图可见子行 | 根节点不再响应 `TVM_EXPAND` |
| 8 | `ss.py menu <pid> 编辑(E) 复制(C)` | 弹窗出现且找到菜单项 | 菜单结构/命名变了 |
| 9 | `ss_uimap.py treelabels <pid> out.txt` | 行数 == 头部 `total=`，且**每行都有名字** | 读文字的远端缓冲写法在新版失效 → **立刻停手**，绝不要改试 `0x110C`/本地指针（会把软件打崩，[pitfalls §54](pitfalls.md)） |
| 10 | `scripts/probe_select.py <pid>` | Q1/Q2/Q3/可见化四项全"是"，最小化下也"是" | 选中语义变了 → [pitfalls §56](pitfalls.md) 的结论要重写，一切"消息选中 + 走菜单"的配方作废 |
| 11 | `ss_uimap.py treectx <pid> out.txt --fit 1.0.2.0` | `name='FB_…'` 且出现 `RCLICK POPUP … MenuItem\|复制(C)` | 弹层类名/结构变了；忘了 `--fit` 则深层行永远点不到（[§53](pitfalls.md)）；只弹 `#32768` 说明焦点没到树（[§49](pitfalls.md)） |
| 12 | 对照 [tree-node-menus.md](tree-node-menus.md) 抽查 3 类节点（`0.0` / `1.0` / 任一 FB） | 菜单项集合与表一致 | 节点类型语义变了，表要重抓（一次约 4 s/节点） |
| 13 | `ss_uimap.py panels <pid> out.txt --fit` | 出现 `ControllerView` → `MenuControl`(10 项) / `ToolBarControl`(**6 条** ToolBar、33 个 IconView) / `MainDockSite`(4 个容器 + 3 个 `ContainerSplitter`) / `StatusBar`(`Text`+`ProgressBar`)；拟合后 `StatusBar` 的 top 应 < 屏高 | 工具栏条数/按钮数变了 = 版本网格改了，[control-tree §5](control-tree.md) 的 id↔HelpText 表要重抓；`ProgressBar` 一直 on-screen 说明软件在忙或状态栏语义变了（[§10](control-tree.md)） |

| 14 | `ss_uimap.py open <pid> out.txt --fit --all --expand --close 1.0.2.3 1.1.1 0.3.0` | 三行都出现 `opened via enter:`，页面根类名分别是 `StructuredTextView`(ST) / `GlobalVariablesView` / `ConfigurationView`；`--expand` 后必须出现 `VariablesView` → `VariableGroupTabControl` → `DefaultGroupDataGrid`（7 列）和 `UsingExpander`；`全局变量` 那页在 `--all` 下必须露出 `GlobalNamespaceGroupDataGrid`（8 列）；三行 close 都是 `closed(click)` 且 `still open=[]` | 根类名换了 → [control-tree §16.2–§16.4](control-tree.md) 的分流判据要重写；`expand … FAILED` 或展开后仍无 `DefaultGroupDataGrid` → 变量表折叠方式变了（[§16.7](control-tree.md)）；`closed` 而不是 `closed(click)` 说明 `closeButton` 的 Invoke 现在真能调（[§58](pitfalls.md)）；不加 `--all` 就看不到内容 → 别误判"这页是空的"（[§57](pitfalls.md)） |
| 15 | `ss_uimap.py open <pid> out.txt --fit 0.4.0 0.4.1 0.5 0.8 1.2.0 1.2.1` | **6 行全是** `enter then dblclick did not open a document`，且每行 `tree focus=True`、`row hit by click=True/True`、`rows 85->85`、`new windows=[]` | 某一页突然能开了 = 该工程在那儿有实体（轴/轴组/跟踪/任务分配），[§15](control-tree.md) 的表开始适用；取证行里 `row hit by click=False` 才是定位问题（行高变了或 `--fit` 没生效，[§53](pitfalls.md)）；`new windows=[...]` 非空说明现在会弹对话框，[§16.6](control-tree.md) 的结论要改 |
| 15b | `ss_build.py totals <pid>`（编译面板可见，工程已编译过） | 打印 `errors=N warnings=M` 且退出码 0 | 面板 id / 计数按钮形状变了 → 按 [control-tree §9](control-tree.md) 重抓编译面板；几何兜底也读不到时**不得把"读不到"当 0 错**（[pitfalls §81](pitfalls.md)） |

任何一项失败：先记录实际输出，再按 §2 重新抓结构，最后更新对应 reference。

轴家族（§R / §17）另有两条，升级后**必须先跑**，因为它们的结论全靠"Win32 组合框 + 像素几何 + 虚拟化弹层"这三件事还成立：

| # | 检查 | 期望 | 失败意味着 |
| --- | --- | --- | --- |
| 16 | `ss_axtable.py probe <pid> out.txt`（轴设置表页在前台、最大化） | 至少一个可见 `WindowsForms10.COMBOBOX.app.*` 子 HWND；若给了列/行还能读到 `count=34` 量级的从站列表与 `cursel` | 新版改成 WPF 网格 → UIA 能直接看见单元格，§17.1 与 `ss_axtable.py` 整条通道作废（**先按 UIA 重测，别硬套 CB_***）；一个 COMBOBOX 都没有而 `EnumChildWindows` 也空 → 是 `raise_tab`/坐标没落到格子上，跑 `geom` 重量 |
| 17 | `ss_axpdo.py expand <pid> out.txt <轴树路径>` | 日志里**必须出现** `expand round N: <组名> pattern -> '-'`（没有 `round` 行 = 一次没点，就是 §67 的假成功）；`expand stable=` 两次一致；随后 `collect` 行数 == 源工程同轴行数 | 组行不再靠 `toggleUnit` 折叠 → §17.2 结构树要重抓（先跑 `ss_axpdo.py peek`）；`过程数据` 下拉打开后**首屏项数**远大于/远小于 ~60 → §17.3 的"先上再下 + 键入兜底"扫描参数要重调；弹层根找不到（`popup_win` 返回 None）→ 下拉宿主变了，回 §2 抓弹层 |
| 17b | `ss_axpdo.py toggles <pid> out.txt <轴树路径>`（只读） | 三组都报出 `'+'` 或 `'-'`，且 `raw` 列表里**只有一个非 offscreen** 的符号 | 报 `('' , …)` = `toggleButton` 改名/挪层，回 `peek` 重认；`轴号 在前面的页` 与期望不符 = `raise_tab` 失效，见 §67.4 |
| 17c | `ss_save.py <pid> saveN --file <目标.smc2> --menu` | `#### SAVED (+Ns)`（sha 变化**且**归档仍有效）且日志有 `点了 文件>保存（click）` | `UNCHANGED` 且轮询里一直有 `HwndWrapper[...]` 小窗 = 弹层没关，加大 `--esc`；`菜单兜底：弹层里没有 保存` = 菜单项 `Name` 形状变了，改 `bare()` 正则；`MISSING`/`INVALID` = 目标消失/损坏，**不是**保存成功（[pitfalls §81](pitfalls.md)） |

## 2. 抓一个没见过的菜单

```bash
ss.py popups <pid> 4          # 先看现在有没有弹窗
ss.py menu <pid> <菜单名> <随便一个肯定存在的项>   # 打开菜单
ss.py popups <pid> 5          # 立刻抓（同一进程内）
```

不行就手写一段：点菜单 → `sleep(0.8)` → 枚举所有可见顶层窗口 → 逐棵 `walk` 输出 `ControlType / Name / AutomationId / Enabled / Rect`。

已知菜单全集：`文件(F) 编辑(E) 视图(V) 插入(I) 工程(P) 控制器(C) 模拟(S) 工具(T) 窗口(W) 帮助(H)`。

## 3. 抓一个新对话框

对话框一般在某个菜单项/按钮之后出现：

```bash
ss.py menu <pid> 插入(I) 轴设置(A)
sleep 1
ss.py popups <pid> 6          # 新对话框的完整树
```

记录要点：

- 对话框标题（顶层窗口 `Name`/`WindowText`）；
- 每个可编辑字段：`AutomationId`（有就最优先）、`Name`、左侧 label 的 id、相对位置（"label 右侧第一个 Edit"）；
- 确认按钮的 `AutomationId`/`Name`（中文按钮通常形如 `确定`、`应用(A)`、`是(Y)`）；
- **是否可 `Invoke` 而不需要前台**（锁屏下也要能跑）。

**怎么证明"树真的展开了"**：UIA 只暴露根节点，行数不会变，只能比对截图像素：

```python
import hashlib
from PIL import ImageGrab
x, y, w, h = tree_rect          # 从 ss_tree.find_tree(pid) 拿
def snap():
    im = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    return hashlib.md5(im.tobytes()).hexdigest()
a = snap(); send(TVM_EXPAND, TVE_COLLAPSE, node); b = snap()
send(TVM_EXPAND, TVE_EXPAND, node); c = snap()
print(a != b, b != c)           # 两个 True 才算折叠/展开都生效
```

实测：根节点 `a!=b and b!=c` 成立；`POUs` 三个哈希完全相同 ⇒ 没反应。

## 4. 待验证清单（别当事实用）

| 条目 | 现状 | 下一步怎么测 |
| --- | --- | --- |
| 在工程树里新建 POU（`插入>程序`） | 未验证 | `ss.py menu <pid> 插入(I) 程序(P)` → `popups` 抓对话框 → 填名 → 确定 → `count` 校验 |
| ST 编辑器读写 | **写入通道已排除**：`--pat` 实测 `textEditor`(`SyntaxEditor`) 只有 `Text` 模式、**没有 `Value`**，所以 `ValuePattern.SetValue` 不存在这条路（`openF.txt`）；写仍走"点它 + 剪贴板/键盘" | 剩一个问题：`TextPattern.DocumentRange.GetText(-1)` 能不能**读出**整段代码——用只读的 `ss_uimap.py open … --pat` 打开一个 ST POU，对 `textEditor` 取 `GetTextPattern()` 读一次即可，不要写 |
| POU 变量表整张表的可读性 | **已验证**：`open … --expand` 后 `DefaultGroupDataGrid` 的行/格/空值全可读（[control-tree §16.7](control-tree.md)） | 需要覆盖"输入/输出""外部""返回值"三个未选中的页签时，得先切 `TabItem`（`SelectionItem.Select()` 未测），再重走 |
| 梯形图/功能块图画布内元件 | 已确认不可枚举 | 只做截图 + 坐标，或在副本上离线改 `.smc2` |
| 编译结果文本读取 | **已验证可全量读**（见 [control-tree §9](control-tree.md#9-输出--编译面板)、`scripts/ss_build.py`） | — |
| 在线/下载/监视 | **未做，且会改真实控制器** | 需要用户明确同意 + 一台可随意折腾的 PLC |
| 仿真（`模拟(S)` 菜单） | **已实测（2026-11-17，用户明确授权）**：在**本地虚拟控制器**上成功运行一次性工程副本，`mode` 离线→`OnlineSimulator`→离线；仿真在本机跑虚拟控制器，**不等于改真实控制器**，但它仍会运行程序、执行运动指令，不是"虚拟就绝对安全" | 安全边界与完整流程见 [tree-node-menus §6](tree-node-menus.md#6-模拟s主菜单与仿真运行态)。**未做**真实在线 / 下载 / 监视（那会改真实控制器，需用户同意 + 可折腾的 PLC）；文档里的示例运动参数只属于其工程语境，**不具普适安全性**，不得照搬到实机或别的工程 |
| 视图/工程/控制器/模拟/工具/窗口/帮助 菜单全量项 | **已逐项导出**（2026-11-17）：主菜单栏 10 项 + `模拟(S)` 26 项（[tree-node-menus §6](tree-node-menus.md#6-模拟s主菜单与仿真运行态)）+ `视图(V)` 27 / `工程(P)` 12 / `控制器(C)` 31 / `工具(T)` 25 / `窗口(W)` 17 / `帮助(H)` 12（[tree-node-menus §7](tree-node-menus.md#7-六个未逐项菜单的全量只读导出2026-11-17-实测)）；`文件(F)` / `编辑(E)` 仍只记常用项 | 剩余两菜单用 `ss_uimap.py menus <pid> <out> [--only=…]`（Expand/Esc，从不 Invoke），按 §2 现抓 |
| 菜单背后的配置对话框 | **已实测（2026-11-17，只读）**：`工具>选项` 20 页、`工程>内存使用`、`自定义快捷键`、`关于`、`通信设置`、`变量管理器`、`库索引`、`用户程序执行用ID`、`窗口布局模板管理` 等结构已落 [control-tree §19](control-tree.md#19-配置对话框与相邻配置页2026-11-17-实测)；事件日志/EtherCAT 诊断入口实际是打开文件对话框 | 换版本先重跑：目录树 + 精确 `Name`（带访问键后缀）→ dump → `CancelButton`/`CloseButton`；绝不点 OK/应用/导入/导出。几类假象见 [pitfalls §88](pitfalls.md) |
| 工程树相邻配置页 | **已实测（2026-11-17，只读）**：内置/单元 EtherNet/IP 端口设置、`事件设置`、`CPU机架: NX总线`、从站 `参数` 可开；`DB连接设置`/`轴组设置`/`Cam数据设置`/`数据跟踪设置` 等无实体节点不开页，见 [control-tree §19.3](control-tree.md#193-工程树相邻配置页按标签不按数字路径) | 用 `ss_uimap.py treelabels` 先建标签表（数字下标会变），再 `open <标签对应路径> --close`；无文档节点与不可达行分开记录 |
| `文件>新建`（已打开工程时） | 未验证 | 打开工程后点菜单，看是向导还是直接建 |
| 拖拽工具箱指令到画布 | 未验证 | `flow` 的 `drag:x1,y1,x2,y2` |
| POU 删除后树/磁盘的一致性 | 部分验证（删除确认框） | 在副本工程里删一个 POU，`count` + 导出校验 |
| 变量表"空名行"的删除通道 | **6 种写法全失败**（右键 删除(D)、工具栏 删除(D)、Delete、Esc、清空类型、Ctrl+A+Delete） | 试：点最左行号格选中整行 → 右键；或离线改 `.smc2` 删掉缺 `N=` 的那一行，再用软件打开验证是否接受 |
| 菜单/上下文菜单"进程级罢工"的根因与恢复 | 现象已记录（pitfalls §20），根因未定位 | 复现后对比 `GetGUIThreadInfo` 的 `hwndMenuOwner`；试 `WM_CANCELMODE`、切到别的应用再切回、只关工程不关进程 |
| 程序分配设置里"初始状态"有哪些选项 | 只见过 `运行` | 点开那一列的 ComboBox 抓 `ListItem` 全量 |
| 合成鼠标拖拽是否在别的控件上有效（树/画布/表格） | 三次都无效 | 用 `flow` 的 `drag:` 在副本上再试一次并截图确认有没有拖动影像 |
| 工程树 `程序`/`任务` 节点的右键菜单 | 实测**完全没有** | 换版本再确认；有的话可能是批量分配的捷径 |
| 给被引用库设命名空间以消除同名类型冲突 | 未验证（`ReferredLibrary/NameSpace` 目前为空） | 库索引里找"命名空间"列/按钮 → 设一个前缀 → 重编译，看 `该名称已用于数据类型 X` 是否归零 |
| 移除库引用后工程是否仍完整 | 未验证 | 在副本工程里移除引用 → 编译 → 对比"未定义标识符"数量；只有确认 FB/FC 已全部在本地才可移除 |
| 数据类型里的"空名结构体行"删除 | 与变量表空名行同样删不掉 | 用户给的线索：**双击编译里的 `数据类型名是空。` 报错会跳到那一行**，再删；或离线改 `.smc2` |
| `ss_axpdo.py fold` / `expand` 能否对齐 `NexAxisPDOMappingTable` | **已验证：不能**（2026-11-07）。两个方向的真点击都能把 `toggleButton` 文字切过去（`peek`/`toggles` 可复核），但保存后归档那串**一字不变**，关掉页签再保存也不变 ⇒ 它是"提交过 PDO 单元格"的历史标记，界面没有清除通道（pitfalls §65.2 已改写） | 别再拿它做验收项；要复核折叠态只看 `ss_axpdo.py toggles`（只读） |
| `toggleUnit` 的点击通道 | `TogglePattern.Toggle()` 实测**能**切状态（`expand round N: … pattern -> '-'`），但**第一遍读值会说谎**，必须 `stable_glyphs()` 两次一致才判（pitfalls §67.2） | 换版本后先 `peek` 确认形状还是 `Button id=toggleUnit → Text id=toggleButton`；形状变了就改 `glyph()` |
| `ss_save.py --menu` 的菜单兜底 | 实测可用（`文件(F)` 展开 + 点 `保存(S)`，+1s 落盘）；裸 `Ctrl+S` 在有残留下拉时会被弹层吃掉 | 换分辨率/语言后重跑一次 `--menu`；若 `bare()` 剥完后缀仍找不到，用 `ss_uimap.py menus` 重抓真实 `Name` |
| `ss_build.py` 面板锚定 + 相对几何兜底 + 短周期 busy 采样 + 状态栏类型锚点的真机行为 | 0.12.0 起按 `buildWindowsViewWindow` id 锚定、几何兜底改相对主窗口；`run` 收紧为 busy 必须明确空闲（None 未知不当空闲，忙/未知重置稳定）、**空闲后重读新快照**连续两个有效稳定新快照才判（绝不复用缓存，防编译中陈旧 (0,0) 被当稳定结果漏读稍后发布的错误）、无证据前不累计稳定（防稍晚开始的编译被错失）、errors>0 一律非 0（warnings 单独不失败）、busy 短周期采样抓 ~2-3s 短编译、计时用 `time.monotonic` 墙钟 deadline 计入全树读成本。`is_busy` 改按**控件类型**在 `StatusBarControl` 上下文找 `ProgressBarControl`（`ss.find` 是 Name/Aid 精确匹配，无名 ProgressBar 恒 None）。纯逻辑有单测（含假时钟），**真机 UI 行为未回归**（历史问题：面板以页签条停靠时 `header not found`/`no message grid`；`POLL_S`/`RUN_TIMEOUT_S` 是启发式默认值；**状态栏/ProgressBar 类型锚点无可靠实测前 `is_busy` 可能恒 None=未知，不伪称有效检测**） | 真机各跑一次 `totals`/`list`/`run`：计数要读到、`run` 要有本轮编译证据、短编译（~2-3s）也要被判为编译过而非 INCONCLUSIVE、有错时退出码非 0、编译中陈旧 0 错不得被当稳定结果;仍读不到就按 [control-tree §9](control-tree.md) 重抓面板形状，别把读不到当 0 错（[pitfalls §81](pitfalls.md)）。**需协调工程方提供状态条/编译按钮证据**确认 `StatusBarControl`→`ProgressBarControl` 锚点与 `IsOffscreen` 忙闲语义（[control-tree §10](control-tree.md) 是历史实测，未在 `run` 回归）；可选增强：探测编译按钮 disabled→enabled 作为额外生命周期证据（**未实现/未验证**） |
| 任务 XML 有 `AssociatedProgramData` 但任务树里没有程序实体 | **结构持久化已观察**（主审独立复核：原生保存后只读 ZIP，主任务 7 个 `AssociatedProgramData` ↔ `.oem` 任务子树 7 个 `NexAssociatedProgram`，含示例，`AssociatedProgramModel` 伴随 XML 仍在；保存前截图/树也显示示例）⇒ 承载分配关系的实体 = `NexAssociatedProgram`（+ `AssociatedProgramModel` 配套），见 [offline-surgery §8.3](offline-surgery.md)。**仅"UI 出现 + 保存后结构持久化"层级，运行时未验证** | `ss_verify.py --program <名>`（结构检查）把悬空关联判 FAIL、子树缺该实体记 INFO（**INFO 不算任务关联通过**）;剩下要证的是**重开后 / 运行时**：在副本工程重开确认分配仍在、并跑一次运行时执行，才能升级为执行验证；`NexAssociatedProgram` 是否运行时必需仍未确认 |
| 轴页八子页每个可见字段 ↔ `.oem` `AxisSettingEntity` XML 字段 | **已验证（2026-11-17 只读实测）**：`ss_axis.py read` 展开全部 Expander 后 8 页共 92 个实化 UIA 行，已逐行与归档叶节点按值/枚举/顺序/Group 配对，完整表见 [control-tree §20](control-tree.md#20-轴页八子页全字段--归档字段映射2026-11-17-只读实测)；归档额外的 `*Value2` / `PDO0..PDO27*` / 版本与历史标记**不是**独立 UI 行 | 换版本或换轴型后先 `treelabels` 选叶序号=轴号的行（[pitfalls §89](pitfalls.md#89-ss_axispy-的树路径末段不等于轴号轴稀疏编号时会主动中止2026-11-17-实测)），再 `ss_axis.py read` 重采；PDO 网格只有 3 行实化、其余 offscreen，逐项集合仍留给 PDO 专项验证 |
| 轴设置表里 `输出设备2/3`、`通道` 各行的写入 | **部分验证（2026-11-17 只读 probe）**：`out2/out3` 单击只画出编辑器，**真实双击**才浮出 `WindowsForms10.COMBOBOX.app.*`；本工程所有轴这些字段都为空，combo 只有 1 项 `＜未分配＞`，无可写替代值；6 个 `通道` 行双击后 **COMBO/EDIT 都没有**。写入通道判 `INCONCLUSIVE / NON_TRANSFERABLE`，见 [control-tree §17.1](control-tree.md#171-轴设置表uia-全盲但格子里有一个真的-win32-组合框) 2026-11-17 补充 | 换到确有 secondary 设备/通道值的工程重跑；只有 combo ≥2 项且能读到非 `＜未分配＞` 时才做“原值写回”可逆验证，不要对只有一项的 combo 硬发按键；树右键用真鼠标，禁用 SendKeys `Shift+F10`（[pitfalls §90](pitfalls.md#90-不要用-sendkeys-shiftf10-开工程树右键菜单会误触仿真2026-11-17-实测)） |
| 灰置参数的派生来源与能否绕开 | **已判明三条独立派生链**（[control-tree §17.5](control-tree.md#175-灰置参数的三种独立派生判据2026-11-18-全-34-轴归档对照--ui-交叉验证)，全 34 轴归档对照 + UI 交叉验证，`PASS`）：A 未使用轴 `NotChangable`、B 虚拟轴型 `Virtual*`（用轴也可能灰）、C `OriginPreset` 派生 `StartDirection`。**无界面开关、可绕开性 `NON_TRANSFERABLE / 未验证`** | 判据读 `.oem` 的 `NexAxisUseAxis` / `NexAxisAxisType` / `NexAxisHomingMode` 与各字段 `IsEnabled` 即可，不要为激活灰值改轴使用/轴型/原点方式；"改原点方式可激活 StartDirection"因全工程仅 `OriginPreset` 一种取值判 `INCONCLUSIVE` |
| 不同轴/型号的 `过程数据` 下拉项集合是否相同 | **已判明按从站型号的 ESI 对象字典分组**（[control-tree §17.6](control-tree.md#176-pdo-过程数据项集合的跨轴型号覆盖2026-11-18-只读测绘)，`PASS`）：`.smc2` 的 ESI `.dat` 内嵌 5 个 `<Dictionary>` 只落 **3 种**索引集——InoSV660N(36 对象)、Panasonic MEDLT/MBDLT/MCDLT(637 对象、索引集逐字节相同)、Festo CTEU 阀岛(27 对象)。同型号族可共用项集合，跨族不可 | 离线从归档按对象索引集 SHA 分组即可，不必逐轴点 257 项下拉；R88D-KN04H-ECT 在本工程无独立 `<Dictionary>`（来自本机已安装 ESI），"换机器仍同集合" `INCONCLUSIVE`；轴1 `Controlword` 行下拉实测只有 3 项（上下文过滤短列表），不能假设每行都是 257 项全集，见 §17.6 |
| EtherCAT 从站 `参数` 页：哪类节点配什么、在哪配 | **已判明导航级形状（2026-11-18 只读，`PASS`）**：从站子节点 `参数`（树路径 `<节点>.0`）打开 `ParameterEditorControl`，含 `导入`/`导出`/`复制设置`/灰置 `Config操作`、`所有参数` 过滤器与 `ParameterGrid`；列固定为 `序号/OD/描述/值/驱动值/默认/范围/单元/数据属性`。按 ESI 字典 OD 区间判大类：伺服厂商参数主要在 `3000h-3FFFh`、厂商扩展 `4000h-5FFFh`、通信 `1000h-1FFFh`、PDO/设备 `6000h-6FFFh`；I/O/耦合器与阀岛不是 Pn 参数模型。**按用户口径不逐项穷举 Pnxxx**，完整导航图与边界见 [control-tree §21](control-tree.md#21-从站参数页导航图按节点类型配什么在哪配2026-11-18-只读) | 先按节点型号判类型，再用 `ss_uimap.py open <pid> <out> <节点路径>.0` 打开该从站的 `参数` 页；要具体参数值时才读 `ParameterGrid`，只读不点导入/导出/复制设置/Config。当前仅一例伺服页在 UI 实测，其它型号的页未逐页打开，标 `INCONCLUSIVE`；参数项随节点配置而变，不把本工程 Pn 列表当通用全集。**厂商差异（用户 2026-11-18 21:05 补充）**：同为伺服，OMRON 自家节点通常可配更多详细参数；判断顺序应为"厂商 → 型号 → ESI 字典"，不要跨厂商套用；该条为用户经验，本轮未再穷举跨型号 UI |

## 5. 回写格式

- **正文**：只写结论 + 判据，用 `[实测]` / `[未验证]` 标注。
- **每条新坑**：写进 [pitfalls.md](pitfalls.md)，标题一句话说清"什么现象 → 什么原因"。
- **每个新 ID**：写进 [control-tree.md](control-tree.md) 对应小节，并注明是在哪个版本上测的。
- **版本记录**：`SKILL.md` 的更新记录表加一行（版本 / 日期 / 内容），并把 frontmatter 的 `version` 递增。
- **失败也记**：多次尝试仍失败的，写进对应 reference 的"搬不动/不可行"小节，避免下一个人重复踩。

## 6. 记录本次探索的模板

```markdown
### <对象名>（实测，V<版本>，<日期>）
- 入口：<菜单/按钮路径>
- 顶层窗口：<标题 / 类名>
- 字段：
  | 字段 | 类型 | AutomationId | 定位规则 |
- 确认：<按钮 Name>（Invoke 可行 / 需前台）
- 成功判据：<外部状态>
- 坑：<现象 → 原因>
```
