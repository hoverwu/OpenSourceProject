# 扩展知识：怎么自己测、怎么记回来

本 Skill 只能靠实测生长。换版本、换机器、遇到没见过的对话框时，按这里的流程补测并回写。

## 0. 铁律

1. **只读优先**：先 `wins` / `state` / `dump` / `popups` / `struct` / `rows`，能把结构看清楚，再动写操作。
2. **读树节点文字只用 `ss_uimap.py treelabels`**：`TVM_GETITEMW(0x113E)` 且 `TVITEMW` + 文本缓冲都 `VirtualAllocEx` 到 Sysmac 里。**别自己发 ANSI 变体 `0x110C`、别把本地指针当 `pszText` 传过去**——那两种写法实测把软件直接打崩（[pitfalls.md §54](pitfalls.md)）。
3. **写操作前先保存工程**。尤其"导入"会关掉当前工程。
4. **测出来才写**：没测过的推断只能进 §4 待验证清单，不能写进正文当事实。
5. 每次回写都更新 `SKILL.md` 的 `version` 与更新记录表，并在本文档末尾追加一条。

## 1. 版本回归清单（换机器 / 升级后跑一遍）

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

任何一项失败：先记录实际输出，再按 §2 重新抓结构，最后更新对应 reference。

轴家族（§R / §17）另有两条，升级后**必须先跑**，因为它们的结论全靠"Win32 组合框 + 像素几何 + 虚拟化弹层"这三件事还成立：

| # | 检查 | 期望 | 失败意味着 |
| --- | --- | --- | --- |
| 16 | `ss_axtable.py probe <pid> out.txt`（轴设置表页在前台、最大化） | 至少一个可见 `WindowsForms10.COMBOBOX.app.*` 子 HWND；若给了列/行还能读到 `count=34` 量级的从站列表与 `cursel` | 新版改成 WPF 网格 → UIA 能直接看见单元格，§17.1 与 `ss_axtable.py` 整条通道作废（**先按 UIA 重测，别硬套 CB_***）；一个 COMBOBOX 都没有而 `EnumChildWindows` 也空 → 是 `raise_tab`/坐标没落到格子上，跑 `geom` 重量 |
| 17 | `ss_axpdo.py expand <pid> out.txt <轴树路径>` | 日志里**必须出现** `expand round N: <组名> pattern -> '-'`（没有 `round` 行 = 一次没点，就是 §67 的假成功）；`expand stable=` 两次一致；随后 `collect` 行数 == 源工程同轴行数 | 组行不再靠 `toggleUnit` 折叠 → §17.2 结构树要重抓（先跑 `ss_axpdo.py peek`）；`过程数据` 下拉打开后**首屏项数**远大于/远小于 ~60 → §17.3 的"先上再下 + 键入兜底"扫描参数要重调；弹层根找不到（`popup_win` 返回 None）→ 下拉宿主变了，回 §2 抓弹层 |
| 17b | `ss_axpdo.py toggles <pid> out.txt <轴树路径>`（只读） | 三组都报出 `'+'` 或 `'-'`，且 `raw` 列表里**只有一个非 offscreen** 的符号 | 报 `('' , …)` = `toggleButton` 改名/挪层，回 `peek` 重认；`轴号 在前面的页` 与期望不符 = `raise_tab` 失效，见 §67.4 |
| 17c | `ss_save.py <pid> saveN --menu` | `#### SAVED (+Ns)` 且日志有 `点了 文件>保存（click）` | `FILE UNCHANGED` 且轮询里一直有 `HwndWrapper[...]` 小窗 = 弹层没关，加大 `--esc`；`菜单兜底：弹层里没有 保存` = 菜单项 `Name` 形状变了，改 `bare()` 正则 |

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
| 在线/下载/监视/仿真 | **未做，且会改真实控制器** | 需要用户明确同意 + 一台可随意折腾的 PLC |
| 视图/工程/控制器/模拟/工具/窗口/帮助 菜单全量项 | 未导出 | 按 §2 逐个抓 |
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
| `ss_build.py totals/list` 在"编译面板以页签条形式停靠在底部"时读不到表头 | 未验证（本轮 `run` 点了 `编译控制器(B)`、日志 `build finished`，但 `header not found`/`no message grid`；只能靠截图读到 `0 错误 0 警告`） | 先用工具栏 `build`（`编译窗口(B)`）把面板切到前台再跑；或按 §3.1 重抓编译面板的表头控件形状 |
| 轴设置表里 `输出设备2/3`、`通道` 各行的写入 | 未验证（本轮只实测过 `out1` 那一行是 COMBOBOX 且 `CB_GETCURSEL` 给真值） | 先 `ss_axtable.py get <pid> out.txt <列> out2` / `… out1ch` 看**能不能浮出编辑控件、是什么类名**（`probe` 会连 EDIT 一起列出来），再决定用组合框通道还是打字通道；不要假设每行都可编辑 |
| 灰置参数（`NexAxisStartDirection`、未使用轴的型号/单位/速度）能否绕开界面 | 界面**确认无开关**（§17.4，两份工程都 `IsEnabled=False`）；是否只能离线改归档**未测** | 只读地对比源/目标 XML 里 `IsEnabled` 的取值来源（多半由 `轴使用`/`AxisType` 派生）；不要在活工程上试手改 |

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
