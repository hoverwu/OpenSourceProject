# 控件地图：窗口 / 菜单 / 工具栏 / 面板

> 这里列的是 **AutomationId 与 Name**，它们是跨机器稳定的；物理矩形只作为"大致在哪"的参考。
> 实测环境：Sysmac Studio V1.68 64 位，Windows 11，125% 缩放，主窗口最大化（约 1582×828 客户区）。换分辨率/缩放/未最大化后**矩形全变**，必须运行时用 `BoundingRectangle` 读。
> 2026-11-06 另有一组"窗口在 `(0,253 1938x1098)`（底边超出屏幕 271px）"的全量实测，落在 §3.1/§4/§5/§6.1/§9.1/§10/§10.1。**那批矩形最直接的用处是告诉你哪些区域此刻在屏幕外**（状态栏、输出/编译页签、筛选器），点不到但读得到。

## 0. 顶层窗口族（先枚举，再找元素）

同一个 `SysmacStudio.exe` 进程下会同时存在多种顶层窗口，**它们不是父子关系**：

| 窗口 | 类名 / 标题特征 | 用途 |
| --- | --- | --- |
| 主窗口 | 类 `HwndWrapper[SysmacStudio.exe;;<guid>]`，标题 `<工程> - <控制器> - Sysmac Studio (64bit)` | 启动页或工作区 |
| 弹出菜单 | 独立小 HWND，出现在点击菜单后，矩形窄而高（实测 189×570） | 主菜单下拉、上下文菜单 |
| 对话框 | 独立 HWND，标题为对话框名（如 `确认另存为`、`工程属性`） | 编辑/确认类 |
| 原生文件对话框 | 类 `#32770`，标题如 `导出文件` / `打开` | 导入/导出/另存为 |
| 隐藏辅助窗 | `SystemResourceNotifyWindow`、`MediaContextNotificationWindow`、`.NET-BroadcastEventWindow.*` | 忽略 |

**规则**：任何 `FindAll` 都要以"该 pid 的全部可见顶层窗口"为根，否则菜单项、对话框永远找不到。`scripts/ss.py find/click/menu/popups` 都是这么做的。

## 1. 启动页（未打开工程，约 55 节点）

```
Window id='MainWindow'
└─ Custom cls='StartPageView'
```

| 目的 | ControlType | AutomationId / Name |
| --- | --- | --- |
| 新建工程 | RadioButton | `NewProjectToggle` |
| 打开工程 | RadioButton | `OpenProjectToggle` |
| 导入 / 导出 | Button | `ImportButton` / `ExportButton` |
| 连接到设备 | RadioButton | `AutoConnectionToggle` |
| 版本控制浏览器 | RadioButton | `SourceControlExplorerToggle` |
| 许可页 | RadioButton | `LicenceToggle`（**只看，不要填**） |
| 在工程文件中管理 | CheckBox | `FileModeCheckBox` |
| 以仿真模式打开 | CheckBox | Name=`以仿真模式打开`（在 `RobotSystemGroupBox` 内） |
| 试用剩余天数 | Text | `DaysLeftValueTextBlock` / `EndTrialTermTextBlock`（未启用时 0×0） |

## 2. 新建工程向导（约 104 节点）

容器：`NewSolutionControl` → `SolutionPropertiesView` + `InsertDeviceView`。

**关键事实：除 `VersionNumberTextBox` / `CreateButton`，其余输入框都没有 AutomationId。** 只能靠"左侧 label 的右侧第一个 Edit/ComboBox"这种相对关系定位。

| 字段 | 类型 | label 的 AutomationId | 定位规则 |
| --- | --- | --- | --- |
| 工程名称 | Edit | `ProjectNameLabel` | label 右侧同高的第一个 Edit |
| 作者 | Edit | `AuthorLabel` | 同上 |
| 注释 | Edit（多行） | `CommentLabel` | 同上，高度更大 |
| 类型（标准/安全…） | ComboBox | `ProjectTypeLabel` | 同上 |
| 号码 | Edit | — | AutomationId=`VersionNumberTextBox` |
| 设备·类型 | ComboBox | `CategoryLabel` | label 右侧第一个 ComboBox |
| 设备·型号 | ComboBox ×2 | — | 两个 ComboBox 中间夹一个 `-` 文本；前=系列，后=具体型号 |
| 设备·版本 | ComboBox | `VersionLabel` | label 右侧第一个 ComboBox |
| **创建** | Button | `CreateButton`，Name=`创建(_C)` | 直接 Invoke |

> 实测：向导里点 ComboBox 会弹出**独立下拉窗口**，选项是 `ListItem`，Name 就是显示文本；选型号要分两步（先系列后型号），第二步的选项随第一步变化。

## 3. 工作区骨架（打开工程后，约 448 节点）

```
Window id='MainWindow'  '<工程> - <控制器> - Sysmac Studio (64bit)'
├─ Custom id='MenuControl' cls='MenuView'
│   └─ Menu id='MainMenu'
│       └─ 10 个 MenuItem：文件(F) 编辑(E) 视图(V) 插入(I) 工程(P)
│                            控制器(C) 模拟(S) 工具(T) 窗口(W) 帮助(H)
├─ Custom id='ToolBarControl' cls='ToolBarView'   → 6 个 ToolBar
├─ Pane   id='MainDockSite' cls='CustomDockSite'  ← Name = 'Online' / 'Offline'
│   ├─ Pane id='ToolWindowContainer-…-<guid>'  左：多视图浏览器（工程树）
│   ├─ Pane id='TabbedMdiContainer-…-<guid>'   中上：编辑器
│   ├─ Pane id='ToolWindowContainer-…-<guid>'  中下：输出 / 编译
│   └─ Pane id='ToolWindowContainer-…-<guid>'  右：工具箱
└─ StatusBar（内含 ProgressBar）
```

- **`-<guid>` 后缀每次运行随机**，用前缀 `ToolWindowContainer` / `TabbedMdiContainer` 匹配。
- `MainDockSite.Name` 就是当前在线模式，实测 `'Offline'`。
- 面板通用小部件：`Button id='autoHideButton'`（自动隐藏）、`Button id='optionsButton'`（Options）、`Text id='title'`（面板标题）。

### 3.1 实测形状（`ss_uimap.py panels`，2026-11-06，当时实例，1.68 64bit，1920×1080 / 125%）

原始记录：`panels01.txt`（未拟合）与 `panels02.txt`（`--fit`），**不随 Skill 发布**；要重跑：

```bash
python <SKILL_DIR>/scripts/ss_uimap.py panels auto logs/uimap/panels02.txt --fit
```

**这一组矩形只在"当前这个窗口位置"有效**，换分辨率/缩放/未最大化全变；记它们是为了认结构、判可见性，不是为了复用坐标（[pitfalls.md §53](pitfalls.md)）。

```
Window  cls='Window' id='MainWindow'                      (0,253 1938x1098)   ← 底边 1351，超出屏幕 271px
├─ TitleBar                                               (29,256 1900x35)
│   MenuBar id='MenuBar' Name='系统'                       (9,262 28x28)
│   Button 最小化 (1751,254) / 最大化 (1811,254) / 关闭 (1870,254)   60x37
├─ Custom cls='StartPageView'                             (0,0 0x0)  disabled+off ← 见 §3.2
└─ Custom cls='ControllerView'        ← 工作区整页         (9,291 1920x1051)
   ├─ Custom id='MenuControl'   cls='MenuView'             (9,291 1920x34)
   │   Menu id='MainMenu'  → 10 个 MenuItem，24px 高，y=296，宽 65~85
   ├─ Custom id='ToolBarControl' cls='ToolBarView'         (15,326 1908x40)  → 6 条 ToolBar，见 §5
   ├─ Text id='SelectedDeviceNameTextBlock' Name='new_Controller_0'   (0,0 0x0) off ← 读 Name 仍可
   ├─ Pane id='MainDockSite' Name='Offline' cls='CustomDockSite'      (9,374 1920x937)
   │   ├─ Custom 'AutoHideTabStrip' ×4                     全 (0,0 0x0) ← 没有自动隐藏面板时就是 4 条空的
   │   ├─ Pane 'ToolWindowContainer-<guid>'   左           (17,381  250x922)  ← 多视图浏览器 / 工程树
   │   ├─ Pane 'TabbedMdiContainer-<guid>'    中上          (274,381 1390x665)  ← **off**：0 个编辑器时整个容器不在树上留内容
   │   ├─ Custom 'ContainerSplitter'                       (267,381 7x922)   左分隔条
   │   ├─ Custom 'ContainerSplitter'                       (274,1046 1390x7)  上下分隔条
   │   ├─ Pane 'ToolWindowContainer-<guid>'   中下          (274,1053 1390x250) ← 输出 / 编译
   │   ├─ Custom 'ContainerSplitter'                       (1664,381 8x922)  右分隔条
   │   └─ Pane 'ToolWindowContainer-<guid>'   右           (1672,381 250x922) ← 工具箱
   ├─ StatusBar                                            (9,1311 1920x31)  ← **在屏幕外**，见 §10
   ├─ Custom id='LeftBottomToolBar'  cls='ToolBarView'      (0,0 0x0) off
   └─ Custom id='RightBottomToolBar' cls='ToolBarView'      (0,0 0x0) off
```

可操作要点：

- **`ContainerView` 是"工作区"这页的根**，`MenuControl`/`ToolBarControl`/`MainDockSite`/`StatusBar` 都挂在它下面；按 id 找控件时以它为界能避开启动页的同名元素。
- **停靠容器谁是谁，只看矩形不看 id**（id 带随机 guid）。判据：左 = `x<30 且 宽≈250`；右 = `x>屏宽-280`；中下 = `宽≈1390 且 top 比 TabbedMdi 大`。
- **`ContainerSplitter` 别点**：拖动会改布局，且 `ContainerSplitter`/`GridSplitter`/`Thumb id='ToolBarThumb'` 三类都是可拖动手柄。
- **窗口挂在屏幕下面**：主窗口 `(0,253 …1098)` ⇒ 底边 1351 > 1080，所以状态栏（y=1311）、输出/编译页签（y≈1276）、`筛选器` Expander（y=1275）**都点在屏幕外**，UIA 能读到但真实鼠标到不了。要在屏幕内操作这些，先 `ss_uimap.py panels --fit`（把窗口滑到 `(-26,-26)`）或把窗口上移/最大化。
- **`--fit` 的效果可以算出来**：同一工程两次全量实测（`panels01.txt` 未拟合 / `panels02.txt` 已拟合），所有元素矩形整体平移 **(-26, -279)** —— 树 `(18,458)` → `(-8,179)`，状态栏 `(9,1311)` → `(-17,1032)`，错误网格 `(275,1108)` → `(252,829)`，`筛选器` `(18,1275)` → `(-8,996)`。拟合后底边 1098 仍比 1080 低 18px，但**状态栏/页签/网格全进屏幕了**，够操作。这组差值只在本机这个分辨率成立，别当常数用：**要坐标就在同一轮里现读**（`--fit` 后立刻 `panels`/`row_rect`）。
- `--fit` 会在结束时把窗口**放回原位**（`restore_rect`），所以"拟合后接着点"必须在同一次脚本调用里做完，不要指望跨命令保持。

### 3.2 工程打开后启动页**仍在 UIA 树里**（坑）

`Custom cls='StartPageView'` 带着全部启动页元素留在树上，只是 `disabled` + `IsOffscreen=True`、矩形 0×0：`NewProjectToggle`、`OpenProjectToggle`、`ImportButton`、`ExportButton`、`AutoConnectionToggle`、`SourceControlExplorerToggle`、`FileModeCheckBox`、`RobotSystemGroupBox`→`StartPageExtensionView`→`以仿真模式打开`，以及 `OfflineLabel`/`OnlineLabel`/`LicenseTopLabel`/`DaysLeftTextBlock`/`DaysLeftValueTextBlock`/`EndTrialTermTextBlock`/`SampleVersionTextBlock`/`EditionNameTextBox`。

两条后果，都要防：

1. **按 id/Name 找元素时必须过滤 `IsEnabled` 与 `IsOffscreen`**，否则工作区里找不到目标时会拿到启动页那个同名的死元素，点下去毫无反应。
2. **许可与序列号相关的那几个（`LicenceToggle`、`EditionNameTextBox`、`LicenseTopLabel`、`DaysLeft*`、`EndTrialTermTextBlock`）在任何状态下都不要读写**——本项目的硬约束是不碰序列号/许可（见 [library-and-tasks.md](library-and-tasks.md) 与用户规则）。它们恒为 disabled+off，正好可以当作"过滤逻辑写对了"的哨兵：如果脚本居然给它们做了操作，说明筛选条件漏了。

启动页本身在**没开工程**时的元素表见 §1。

## 4. 菜单栏

`MenuItem` 的 `Name` 与 `AutomationId` **都是**带助记符的形式（`Name='文件(F)'`，`AutomationId='文件(_F)'`，实测矩形 `(0,34,68×24)`）。按 Name 找、用 `ss.py menu` 点是可行的（实测能展开并列出弹窗项）。

实测条带（2026-11-06，窗口在 `(0,253 …)` 时）：`MenuControl`/`MainMenu` = `(9,291 1920x34)`，10 个顶级项都在 **y=296、高 24**，宽 65~85 从左往右连排：`文件(F)`@9、`编辑(E)`@77、`视图(V)`@145、`插入(I)`@215、`工程(P)`@280、`控制器(C)`@349、`模拟(S)`@434、`工具(T)`@503、`窗口(W)`@571、`帮助(H)`@647。每项里面还有一个 `Text`（`Name='文件(_F)'`，24px 行里 19px 高）——**顶级菜单栏是 WPF 画的、在主窗口树里**；点开后出现的下拉才是**独立弹窗**（[pitfalls.md §49](pitfalls.md)，以及 §0 的顶层窗口族）。

> ⚠ 第二排第 4 个是 `工程(P)`，不是 `工程(E)`。写错会得到"menu not found"。

> ⚠ 点不开时先看 [pitfalls §23](pitfalls.md#23-菜单点不开时先查残留模态窗与罢工再用坐标助记符兜底)：残留模态窗 > 菜单罢工 > 弹窗枚举方式；兜底才用坐标点菜单栏 + 助记符键。

实测已导出的菜单内容：

**文件(F)**：`关闭` `保存` `另存为(A)...` `另存为新号码...(N)` `导入(I)...` `导出(E)...` `离线比较(M)` `页面设置(G)...` `打印(P)...` `工程属性(R)`（无工程时 DISABLED）`退出(X)`

**编辑(E)**：`撤销` `重做` `剪切` `复制(C)` `粘贴(P)` `删除(D)` `全选` …（对工程树节点，实测 `复制(C)`/`粘贴(P)`/`删除(D)` 是关键三项）

**插入(I)**（实测全量，分隔线是 Name 为空、高 6~7px 的 MenuItem，跳过）：

```
回路(R)  导出设备  控制器(C)  应用管理器  安全网络控制器(O)  驱动器(D)  HMI(H)
测量传感器(E)  视觉传感器(V)  从设备终端(S)  程序(P)  功能(F)  功能块(B)
轴设置(A)  轴组设置(G)  CNC设置(E)  机械手控制设置(L)  CAM数据设置(M)
数据跟踪(T)  DB连接设置(N)  …
```

**已逐项导出**：`插入(I)` 全量、`模拟(S)` 26 项（[tree-node-menus §6](tree-node-menus.md#6-模拟s主菜单与仿真运行态)）、`视图(V)` 27 项、`工程(P)` 12 项、`控制器(C)` 31 项、`工具(T)` 25 项、`窗口(W)` 17 项、`帮助(H)` 12 项（[tree-node-menus §7](tree-node-menus.md#7-六个未逐项菜单的全量只读导出2026-11-17-实测)）。`文件(F)` / `编辑(E)` 仍只记了常用项；需要时用只读工具 `ss_uimap.py menus <pid> <out> [--only=…]` 现抓，见 [extending.md](extending.md#2-抓一个没见过的菜单)。

## 5. 工具栏（33 个命令 / 6 条 ToolBar）

按钮结构：`Button`（无 id）→ `Custom id='<命令名>' cls='IconView'`。**外层 Button 的 `Name` 和 `AutomationId` 都是空的，中文标题在 `HelpText` 里**（实测 `Button|||Button|剪切(T)` 这种形状：类型｜Name｜id｜类名｜HelpText｜状态｜矩形）。所以：

- 稳定定位 = 找 `Custom id='<命令名>'` 再取父 `Button`；
- 按文字找 = 用 **HelpText** 匹配（`ss.py` 的 help 匹配走这条），别用 Name；
- 直接坐标点外层 Button 在锁屏/多实例下不可靠。

`ss_uimap.py panels` 实测（2026-11-06，离线 + 无编辑器打开时的状态；矩形是当时窗口位置的，只用于认结构）：

| # | ToolBar 矩形 | 命令（id ← HelpText），`✗`=离线时灰 |
| --- | --- | --- |
| 1 | `(15,326 280x40)` | `cut` 剪切(T)、`copy` 复制(C)、`paste` 粘贴(P)、`delete` 删除(D)、`undo` 撤销(U)✗、`redo` 重做(R)✗、`help` 帮助 |
| 2 | `(295,326 355x40)` | `3d_visualizer` 3D可视化器、`terminal_window` **输出窗口(O)**、`build` **编译窗口(B)**、`search` **交叉索引窗口(C)**、`watch` 监视窗口(W)、`watch_table_normal` 监视标签页(表)(G)、`differential_monitor` 微分监视器(D)...、`find` **查找和替换**、`error_log` 故障分析✗ |
| 3 | `(650,326 55x40)` | `device_build` 编译控制器(B) |
| 4 | `(705,326 355x40)` | `online` 在线、`offline` 离线✗、`monitor` 监测✗、`stop_monitor` 停止监测✗、`drive_mode` **运行模式**✗、`program_mode` 编程模式✗、`sync` 同步✗、`download` **到控制器**✗、`upload` **从控制器**✗ |
| 5 | `(1060,326 168x40)` | `reset` **缩放到合适大小(F)**✗、`zoomIn` 放大(I)✗、`zoomOut` 缩小(O)✗、`zoom100_normal` 重置缩放(R)✗ |
| 6 | `(1228,326 92x40)` | `start_playback_normal` 开始回放(S)✗、`end_playback_normal` 退出回放(E)✗ |

三个容易记错的 id（id 与中文标题对不上，别按英文字面猜）：`terminal_window` 是**输出窗口**不是终端；`search` 是**交叉索引窗口**、`find` 才是查找替换；`reset` 是**缩放到合适大小**、`zoom100_normal` 才是 100% 重置缩放。`download`/`upload` 的标题是"到控制器/从控制器"。

离线基线（可用于"软件现在是什么状态"的粗判）：第 4 条除 `online` 外全灰，第 5、6 条**全灰**（因为没有编辑器打开），`error_log` 灰，`undo`/`redo` 灰。判定在线/离线仍然要读 `MainDockSite.Name` 或 `ss.py state`，别拿按钮灰不灰当唯一依据。

每条 ToolBar 还有 `Button id='OverflowButton'`（溢出菜单，实测恒为 disabled）和 `Thumb id='ToolBarThumb'`（拖动手柄，**不要点**，会把工具栏拖走）。

## 6. 工程树（多视图浏览器 / Multiview Explorer）

```
ToolWindowContainer-* 
└─ ComboBox id='DeviceComboBox'
   └─ Pane id='WindowsFormsHost'
      └─ Pane id='GDISolutionView'
         └─ Tree id='SolutionTreeView'  cls='WindowsForms10.SysTreeView32.app.0.*'
```

- 每个进程只有一个这样的 Tree；`UIA` 下它的 `Name` 为空。
- **UIA 只暴露根节点**：`SolutionTreeView` 的子元素数 = 根节点数（典型 2 个），每个是 `Tree`，`BoundingRectangle` 是那一行的矩形（125% 下行高 **26px**、缩进 **18–22px/级**）。展开后出现的一级/二级行**不会**出现在 UIA 里，所以"数 UIA 行数"不能用来判断是否展开，也不能用来定位深层行。
- **读文字（安全，实测）**：`ss_uimap.py treelabels` = `TVM_GETITEMW(0x113E)` + 远端 `TVITEMW` + 远端文本缓冲（`pszText` 也指向目标进程内存），读回即可。会崩软件的是"ANSI 变体 `0x110C`"和"本地指针跨进程传"两种写法（[pitfalls.md §54](pitfalls.md)）。Sysmac 存的标题尾部带空格补齐，用前 `rstrip`。
- **枚举结构**：`TVM_GETNEXTITEM(0x110A)`，`wParam` 取 `TVGN_ROOT(0)/NEXT(1)/PARENT(3)/CHILD(4)` 拿句柄，安全且不受展开状态影响。
- **枚举"当前可见行"**：`TVGN_FIRSTVISIBLE(5)` 起步、`TVGN_NEXTVISIBLE(6)` 逐行，拿到 `[(句柄, 文字)]`。行号就是屏幕顺序，是后续点击的唯一坐标依据。
- **选中靠消息，打开才靠真实输入**（2026-11-06 probe_select 复核，**推翻 0.4.2 的"TVM_SELECTITEM 到不了这棵树"**）：`TVM_SELECTITEM(TVGN_CARET, h)` 一次做完四件事——`TVGN_CARET` 回读等于 h、目标行**真的**带上 `TVIS_SELECTED`、上一行被取消选中、软件把该行滚进视野；窗口**最小化**时同样有效。深度无限制（`1.0.0.0.0` 也行）。所以 `编辑>复制/粘贴/删除` 这类"先选中再走菜单"的动作**不需要真实鼠标**。
  消息**做不到**的是"打开页面"：那要真实单击 + 真实 `{ENTER}`，或双击未选中的行（见 [project-tree.md §3.4](project-tree.md)）。
- **打开页面 = 双击"未选中"的行**。双击已选中的行会进入**行内重命名**（弹出编辑框，后续按键全进那个框）。所以顺序必须是：先点别处/空白取消选中，再双击目标；目标已经在编辑状态时先 `{ESC}`。
- **行矩形**：`TVM_GETITEMRECT(0x1104)`，契约见 [pitfalls.md §33](pitfalls.md)；只有可见行才拿得到，先 `ENSUREVISIBLE`。
- **展开**：`TVM_EXPAND(0x1102)` **只对根节点有效**，深层返回 0 且视觉不变；深层要展开就"caret 用消息放好 + 真实 `VK_RIGHT`"（`ss_uimap.py expand_node`，见 [project-tree.md §3.2](project-tree.md)），用 `TVIS_EXPANDED(0x20)` 验证。
- 默认根节点两条：`配置和设置`（index 0）与 `编程`（index 1）。新建工程后可见行典型 10 行：`配置和设置 / 编程 / POUs / 程序 / Program0 / Section0 / 功能 / 功能块 / 数据 / 任务`。

### 6.1 实测容器链与矩形（2026-11-06，当时实例）

```
Pane 'ToolWindowContainer-<guid>'            (17,381 250x922)   ← 左边这一条
├─ Button id='autoHideButton'                (244,386 20x20)  HelpText=自动隐藏
├─ Button id='optionsButton' cls=PopupButton (224,386 20x20)  HelpText=选项
├─ Text   id='title'                         (23,386 90x20)   ← 面板标题，UIA Name 恒为 'Title'
├─ Custom id='NX502' cls='IconView'          (218,414 40x40)  ← 设备图标，id 是**当前设备型号**，换工程会变
├─ ComboBox id='DeviceComboBox'              (24,420 148x28)  Name='DeviceComboBox'
├─ List id='DeviceListBox'                             0x0 off ← 下拉展开时才有内容
├─ Pane id='WindowsFormsHost'                (18,458 247x816)
│   └─ Pane id='GDISolutionView' cls='WindowsForms10.Window.8.*'  (18,458 247x816)
│       └─ Tree id='SolutionTreeView' cls='WindowsForms10.SysTreeView32.*'  (18,458 247x816)
│           ├─ Tree (18,458 129x26)   ← 根 0 那一行（Name 为空）
│           └─ Tree (18,484 78x26)    ← 根 1 那一行；UIA 只暴露这两条根行
└─ Group Name='筛选器' cls='Expander'        (18,1275 247x27)  ← 屏幕外，见 §3.1
    ├─ Button id='HeaderSite' Name='筛选器'  (19,1276 245x25)
    ├─ Button id='PushPin'                   (242,1277 22x23)
    └─ Custom cls='FilterWindow'     0x0 off
        ├─ ComboBox id='ConditionComboBox'   0x0
        ├─ Button id='ExecutionButton' Name='执行'   0x0
        ├─ Text  '没有与指定条件匹配的项。'           0x0
        └─ DataGrid id='FilterResultList'    0x0 off
```

- **树本体是 `Tree` 控件自己占满 `WindowsFormsHost`**：三个矩形完全相同，所以"给 `WindowsFormsHost` 算坐标"和"给 `SolutionTreeView` 算坐标"是一回事。行高 26px、第一条根行 top = 树 client top。
- **UIA 里的行只有两条根**，深层行不出现（§6 已述）；`SolutionTreeView` 的 `GetChildren()` 数 = 根数，可当"树重绘完成"的轻量判据。
- **`筛选器` 整块默认是折叠 + 屏幕外**：`FilterWindow`/`FilterResultList` 都读得到但 0×0，展开它要点 `HeaderSite`（而它在屏幕外）——要用筛选器必须先 `--fit` 或把窗口上移。
- `NX502` 这种"设备型号当 id"的 IconView 不能当定位锚点，用 `DeviceComboBox` 或 `WindowsFormsHost`。

## 7. 工具箱

```
Custom id='toolboxViewWindow' cls='ToolboxView'
├─ ComboBox id='searchCombo'  →  Edit id='PART_EditableTextBox'
└─ Custom id='toolboxItems'
   └─ Button id='groupToggle'  （Name = 组名，如 Math / Comparison / Counter …）
```

> 它在 UIA 树里挂在**右边那个 `ToolWindowContainer`** 下面，实测矩形与内部元素见 §10.1。

- 分组实测可见：`Analog Conversion` `BCD Conversion` `Bit String Processing` `Comparison` `Counter` `Data Movement` `Data Type Conversion` `FCS` `Math` `Motion Control` `OPC UA` `Other` `Program Control` …
- 空组显示 `Text id='emptyDescription'`。
- 搜到的指令项可用于拖到画布——**画布内的落点/接线未验证**（见 [pitfalls.md](pitfalls.md#8-gowpf-画布只有一块)）。

## 8. 编辑器区（TabbedMdiContainer）

- 每个打开的编辑器是它的一个子 `TabItem`（Name = 编辑器名，通常就是 POU 名）。
- 没有子节点 = 当前没有打开任何编辑器。实测 0 编辑器时 `TabbedMdiContainer-<guid>` 自己还挂在 `MainDockSite` 下（矩形 `(274,381 1390x665)`）但**状态是 off、`GetChildren()` 为空**——所以"有没有编辑器"用子节点数判断，不要用"容器存不存在"判断。
- 编辑器区左右两侧的分隔条是 `ContainerSplitter`（`(267,381 7x922)` / `(1664,381 8x922)`），下方是 `(274,1046 1390x7)`；三个都不该点。
- **编辑器实例本身不是 `TabItem`，是 `PaneControl cls='DocumentWindow'`**：它的 `Name` = 文档名（`FB_AxisAllow` / `全局变量` / `PrgMain - PRG_Example`），`HelpText` = 标题栏全名（多一段 `- new_Controller_0`）。见 §16.1。
- 开/关编辑器的可复现做法（2026-11-06 实测 15 种页面）已成文：**§16「编辑器内部形状」**，含每类页面的控件链、`closeButton` 的 Invoke 拒绝行为、以及 6 个"这工程里根本打不开"的节点。
- **`Text id='textEditor' cls='SyntaxEditor'` 是 ST 编辑器里唯一可寻址的文本主体**，但它没有 `ValuePattern` 可写（Actipro 自绘），读写仍要走键盘（§16.2）。梯形图画布内部元件依旧不可枚举（实测只能到 `RootControl cls='LadderEditorView'` 一大块，见 §16.2 与 pitfalls §8）。

## 9. 输出 / 编译面板

| 面板 | 定位 |
| --- | --- |
| 编译 | `Pane id='buildWindowsViewWindow' cls='BuildWindowView'` |
| 输出 | `Pane id='outputWindowsViewWindow'` |

面板已定位。**错误列表实测可读**（V1.68）：

| 元素 | 位置 / 取法 |
| --- | --- |
| 头部「N 错误」 | 两个 `Button`（HelpText=`显示或隐藏错误` / `显示或隐藏警告`），数字与文字是它们**自己的子 `Text`**，不在它们右边。矩形随窗口变，见 §9.1 |
| 错误/警告数字 | 取那两个 `Text` 的 `Name`（实测 `'0'` / `'0'`；另一工程实测 `'385'`），**不要**靠标题栏或状态栏猜 |
| 列表 | `DataGridControl`，`cls='ListView'` 且**没有 id/Name**，只能靠几何（在它所属容器下面、宽 >1000）定位；同类的 `id='FilterResultList'` 是筛选器结果，恒 0×0 |
| 行 | 每行 `GetChildren()` 里是若干 `TextControl`，列序稳定：`编号／说明／程序／位置`（见 §9.1 的实测列宽） |
| 全量读取 | 该网格支持 `ScrollPattern`（`VerticallyScrollable=True`）：`SetScrollPercent(-1, 5/10/…/100)` 逐屏收，按 `编号` 去重；不支持时退化为点网格 + `{Ctrl}{Home}` + `{PAGEDOWN}`（**uiautomation 没有 `{PgDn}` 键名**，写错抛 `ord()` TypeError，见 pitfalls §81） |
| 落盘 | **写 UTF-8 文件再读**（控制台 GBK 会乱码，见 pitfalls §18） |

现成脚本：`scripts/ss_build.py totals|list|run <pid> [out.txt]`。定位先按 `AutomationId='buildWindowsViewWindow'` 锚定编译面板，计数读面板内那两个按钮的子 Text；找不到面板 id 时退回**相对主窗口下半部**的几何兜底（窗口矩形现读，不用绝对 Y 常量）。

编译动作本身可用工具栏 `device_build`（HelpText=`编译控制器(B)`）或菜单触发，忙闲用状态栏 `ProgressBar` 判断。**仅"面板数字连续两次轮询不变"不能算编译结束**——刚点完读到的可能是上一轮陈旧计数；`run` 还要求有本轮真的编译过的证据（见过忙 / 计数变化 / 网格内容变化），任一不满足返回非 0（pitfalls §81）。

### 9.1 实测形状（2026-11-06，中下容器 `(274,1053 1390x250)`）

```
Pane 'ToolWindowContainer-<guid>'            (274,1053 1390x250)   ← 中下这一条
├─ Button id='closeButton'                   (1642,1058 20x20)  ← **别点**，点了面板就关了
├─ Button id='autoHideButton'/optionsButton  (1622,1058)/(1602,1058)
├─ Text   id='title'                         (280,1058 30x20)
├─ Pane id='outputWindowsViewWindow' cls='OutputWindowView'  Name='输出'  (274,1277 43x25)  ← 页签
│   └─ Text id='title' 'Title'                                                    (280,1279 30x19)
└─ Pane id='buildWindowsViewWindow'  cls='BuildWindowView'   Name='编译'  (317,1276 42x27)  ← 页签
    ├─ Button HelpText='显示或隐藏错误'      (279,1085 79x20)
    │   ├─ Image                           (279,1085 20x20)
    │   ├─ Text Name='0'                   (305,1085 8x20)   ← 数字格
    │   └─ Text Name='错误'                 (317,1085 41x20)
    ├─ Button HelpText='显示或隐藏警告'      (366,1085 79x20)  → Text '0' + Text '警告'
    └─ DataGrid cls='ListView'（无 id/Name） (275,1108 1388x168)
        Header cls='GridViewHeaderRowPresenter' (278,1108 1382x20)
        ├─ HeaderItem  ''      (278,1108 31x20)   ← 图标列，无标题
        ├─ HeaderItem  ''      (309,1108 38x20)   ← 编号列，无标题
        ├─ HeaderItem  '说明'  (347,1108 250x20)
        ├─ HeaderItem  '程序'  (597,1108 125x20)
        └─ HeaderItem  '位置'  (722,1108 187x20)
```

要点：

- **两个页签本身就是 `Pane`，`Name` 就是"输出"/"编译"**，矩形只有 43×25——它们是**页签头**，不是面板内容；`buildWindowsViewWindow` 的矩形里装着按钮和网格，所以判"编译面板可读"要读它**子元素**的矩形，不是它自己的。
- **头部计数是两个独立 `Text`（数字 + 文字）**，数字格就是 `ss_build.py totals` 取的 `Name`；实测本例 `0 错误 / 0 警告`。
- **列表头有 5 列，前两列没有标题**：所以"按表头文字找列"会漏掉图标列和编号列；取一行时按子 `TextControl` 顺序 = `编号、说明、程序、位置`（第 0 列是空文本）。
- `DataGrid` 的几何判据仍然成立：`id='FilterResultList'` 是**筛选器**的结果网格（恒 0×0），编译/错误网格是**没有 id 的那个** `cls='ListView'`。优先在 `buildWindowsViewWindow` 面板子树里找它；退回几何时用"同一容器内且宽 >1000"+**相对主窗口**的位置判断（`top>1100` 只是本机基线，不是跨机器常量）。
- 本例里 `1085/1108/1276` 这几行都在屏幕外（窗口底边 1351 > 1080）：**读文本没问题，真实点击不行**，需要 `--fit`。

## 10. 状态栏

实测（同一环境）：`StatusBar (9,1311 1920x31)`，里面**只有两个子元素**：

| 元素 | 矩形 | 说明 |
| --- | --- | --- |
| `Text` cls=`TextBlock` | `(0,0 0x0)` | 没有 Name/id；空闲时不占位。别指望从状态栏读工程名/在线态——那些在 `MainDockSite.Name` 和标题栏 |
| `ProgressBar` | `(1775,1316 125x22)`，**状态 = off** | 空闲时 `IsOffscreen=True` |

所以忙闲判据是：

- **`ProgressBar` 的 `IsOffscreen` 由 True 变 False（或矩形非 0×0）⇒ 软件正在忙**（编译中 / 导入中 / 正在打开工程）；轮询它比固定 `sleep` 可靠。
- 状态栏整条在屏幕外时**只能读不能点**（§3.1），ProgressBar 无需点击，不受影响。
- `mode=Online/Offline` 一律读 `MainDockSite.Name` 或 `ss.py state`，不从状态栏猜。

### 10.1 工具箱（右容器实测，`toolboxViewWindow (1673,409 247x893)`）

```
├─ RadioButton id='listRadioButton'  SELECTED   (0,0 0x0) off  ← 列表/网格视图切换，当前在"列表"
├─ RadioButton id='gridRadioButton'             (0,0 0x0) off
├─ ComboBox  id='searchCombo'                   (1675,415 183x25)
│   └─ Edit  id='PART_EditableTextBox'          (1677,416 155x23)
├─ Button（无 id，disabled）×2                   (1863,415)/(1893,415) 25x25  ← 搜索条件的 and/except 按钮
├─ Custom id='toolboxItems' cls='ToolboxItemsControl' (1673,443 247x729)
│   └─ Pane id='ScrollViewer' → ScrollBar id='VerticalScrollBar'（disabled）
├─ Thumb cls='GridSplitter'                     (1673,1172 247x5)
└─ Pane（描述区）cls='ScrollViewer'              (1673,1177 247x125)
    ├─ Text  '说明标题'                          (1673,1177 247x18)
    └─ Document cls='RichTextBox'                (1673,1195 247x21)
```

- **`searchCombo` 的 `HelpText` 就是搜索语法说明书**（实测：`例如 包含'切换'和'按钮':切换按钮 / 包含'切换'和不包含'按钮':切换-按钮 / 包含'切换按钮':"切换按钮"`）——要写筛选直接照这个语法，别自己发明。
- 指令项在 `toolboxItems` 里，折叠状态下**不出现**；展开某组用 `Button id='groupToggle'`（Name=组名，见 §7）。
- 底部 `RichTextBox` 是选中项的说明文本，是**读指令文档最便宜的路**：点一项 → 读这块。
- 两个 `RadioButton` 恒 0×0：视图切换按钮不在这里，别按 id 点它们。

## 11. 对话框族

| 对话框 | 出现时机 | 结构要点 |
| --- | --- | --- |
| 新建工程向导 | 启动页 `NewProjectToggle` | 见 §2 |
| 工程属性 | `文件>另存为` 第一步 | 工程名称 / 作者 / 注释可编辑；类型只读；密码区（**不要碰**）；`保存(S)` |
| 原生打开/导出 | `文件>导入`、`文件>导出` | 类 `#32770`；文件名预填 `<工程名>.smc2`；类型 `Sysmac Studio V1.08或更高的工程文件 (*.smc2)`；按钮 `保存(S)` / `打开(O)` |
| 确认另存为 | 导出覆盖已有文件 | **独立 `#32770`，不是导出框的子控件**：`ButtonControl 是(Y)` / `否(N)`（实测 125% DPI 下 `是(Y)` ≈ (988,541,1069,570)，位置随对话框变，别记坐标）。先 `SetForegroundWindow` 再点 |
| 退出前保存 | `导入` 会先关当前工程 | `是(Y)` / `否(N)` / `取消` |
| 多选复制 | 工程树右键 `POUs>选择并复制多个项目` | `MultiplePousCopyDialog`，见 [project-tree.md](project-tree.md#6-多选复制批量搬-pou的主路径) |
| 命名冲突 | 粘贴已存在的 POU | `存在具有相同名称的POU。确定要覆盖所有内容吗?`：是=覆盖 / 否=保留两者（自动加 `复制1_` 前缀）/ 取消 |
| 删除确认 | `编辑>删除` | 显示**内部名**，不一定是树上的显示名 |
| 库索引 | `工程>库(L)>显示索引(S)` | WPF 窗口，不是 `#32770`。表格列：库名称/命名空间/版本/作者/公司/创建时间/修改时间/注释/附件/ID；工具条 `+` / 删除 / 刷新；复选框"将引用库包含在工程中"（默认勾）；`确定`。详见 [library-and-tasks.md](library-and-tasks.md#2-给工程挂一个-slr-库库索引) |
| 引用库文件 | 库索引里点 `+` | 原生 `#32770`，默认目录是软件的库目录；`文件名(N):` Edit + `打开(O)`。**用 ValuePattern.SetValue 写完整路径** |
| 引用库（提示） | 选完 .slr 之后 | 独立小窗，`库中可能使用了当前控制器不支持的指令。…` + `确定`。必须先关它，库索引才继续 |
| 程序属性 | 工程树 `程序` 叶子右键/属性 | 只有 名称/命名空间/版本/作者/创建时间/更新时间/注释 —— **没有任务字段**；标题栏"关闭"是灰的，用 `取消` 关 |
| 导出文件 | `文件>导出(E)...` | `#32770`，实测矩形 (0,29,960,600)。`文件名:` 是 **ComboBox 套 EditControl**，里面那个 `EditControl` 的 **AutomationId = `1001`**（UIA Name 也是 `文件名:`，**不是** `文件名(N):`）；`保存(S)` 是 `AutomationId = '1'`。**必须先 `SetForegroundWindow(对话框)`**，否则键盘发到主窗口；文件名用剪贴板粘贴（`SendKeys` 打不了中文）；不要用 `ValuePattern.SetValue`（V1.68 抛 `COMError -2147220992`）。完整步骤见 [recipes.md](recipes.md#l-导出成-smc2含覆盖确认) |

> 注意：`工程>库(L)` 的子菜单里 `库设置(L)`/`创建库(C)` **只在库工程（标题带 `[库]`）里可用**，普通工程是灰的。


## 12. 控件类型 ↔ UIA Pattern 对照

| ControlType | 可用的操作 | 备注 |
| --- | --- | --- |
| `Button` | `InvokePattern` | 工具栏按钮外层无 id |
| `RadioButton` / `CheckBox` | `TogglePattern` / `SelectionItemPattern` | 启动页入口多是 RadioButton |
| `ComboBox` | `ExpandCollapsePattern` + 弹窗里的 `ListItem` | 下拉是独立窗口 |
| `Edit` | `ValuePattern.SetValue`；不行再 `Click`+`SendKeys` | 向导里大多无 AutomationId |
| `MenuItem` | `ExpandCollapsePattern` / `InvokePattern` | Name 带助记符 |
| `TabItem` | `SelectionItemPattern` | 编辑器中上区 |
| `TreeItem`（WPF） | `ExpandCollapse` / `SelectionItem` | 与 WinForms 树无关，别混 |
| `Tree`（WinForms 行） | 只能取矩形（**仅根节点有**） | 操作它下面的原生控件要靠 `TVM_*` |

## 13. 快速自检清单

1. `ss.py wins` 能列出实例，标题里有工程名 → 接上了。
2. `ss.py state <pid>` 的 `mode=Offline/Online`、`editors=N` 合理 → UIA 树可读。
3. `ss_tree.py struct <pid> 2` 能给出根节点与一级子节点数 → 原生消息通。
4. `ss_tree.py goto <pid> 1.0` 打印 `caret=<句柄> path=[1, 0] children=<n>` → 定位可用。
5. `ss_uimap.py panels <pid> --fit` 落盘后能看到 §3.1 那几层（`ControllerView`→`MenuControl`/`ToolBarControl`/`MainDockSite`→4 个容器）→ 骨架对得上，可以开始按 id 定位。
6. `ss_uimap.py open <pid> out.txt --fit --all --expand --close 1.0.2.3 0.3.0 1.1.1` 三行都是 `opened via enter:`、页面根类名分别是 `StructuredTextView`/`ConfigurationView`/`GlobalVariablesView`、`DefaultGroupDataGrid` 与 `GlobalNamespaceGroupDataGrid` 都出现、三个 `closed(click)` 且 `still open=[]` → 开页/展开/关页这条链通，编辑器内部形状表（§16）可用。
7. 七条都通过，再开始做写操作。

## 14. 数据类型页（结构体 / 命名空间）

`数据 > 数据类型` 打开后是一个多页编辑器，一页 = 一组结构体（导出后在 `.oem` 里就是一条 `type="DataType"` 实体，文件名里的 `<DataType Name="数据类型N">` 是页标题）。

| 元素 | 说明 |
| --- | --- |
| 文档选项卡 | 顶部 `PaneControl` 条（实测 y≈119..151），页名如 `数据类型` / `全局变量` / `任务设置` / `EtherCAT`。**先点选项卡再操作**，否则 UIA 矩形还是上一个视图的 |
| `NamespaceToggleButton` | 约 (281,163)（125% DPI，随窗口变）。点它显示/隐藏**命名空间面板**；**点到它边缘会把已展开的面板再折回去**，所以每次点完都要重新读控件矩形 |
| `NamespaceTreeView` | 命名空间树。根在 x≈270，子节点在 x≈314（缩进 44px）。行上没有 Name 可读，只能按几何点 |
| 面包屑 | 选项卡下方 y≈163，形如 `root > SysControl`，是**唯一能读到当前命名空间名的文本** |
| 网格 | 列：`名称 / 基本类型 / 偏移类型 / Byte偏移 / Bit偏移 / 注释`；未选中命名空间时，左侧会出现 `结构体` / `联合体` / `枚举类型` 分组标签（x 265..349） |

**建子空间（子命名空间）**：先单击结构体名称格（选中当前命名空间），再在结构体区域**右键** → 菜单里选"命名空间"类的项。这样建出的子空间才会让 `数据名称中含有无效值。` 消失；只改结构体名不解决。

**已知难点（实测未解决）**：

- 命名空间树的选中态很难用坐标点改（反复点到同一个节点），点偏一点就折叠面板；
- 页里出现**名称为空**的结构体行时删不掉，编译报 `数据类型名是空。`（与变量表的空名行同类，见 pitfalls §22）。

### 14.1 关键控件 id（2026-10-31 实测，64bit 版）

| 页面/区域 | 控件 |
| --- | --- |
| 数据类型/全局变量 文档页 | `PaneControl`，`ClassName=DocumentWindow`，`Name=数据类型/全局变量/EtherCAT/轴设置` |
| 数据类型列表 | `Tab id=DataTypeTabControl` → 三个 `TabItem`（结构体/联合体/枚举类型）→ `DataGrid id=PART_ListView`，行是 `DataItem`（`ListViewItem`，26 px 高） |
| 全局变量表 | `DataGrid id=GlobalNamespaceGroupDataGrid`，`ClassName=CellEditor`（**不是** `PART_ListView`）；行高 26 px |
| EtherCAT 拓扑 | `Custom cls=TopologyEditor` → `Tree id=TopologyView`（ControlType 是 TreeView，**AutomationId 才是 TopologyView**） |
| EtherCAT 工具箱关键字框 | `Edit id=SearchTextBox`（占位文字 `输入关键字`） |
| EtherCAT 搜索结果 | `List id=ItemListBox` → `ListItem`（38 px/行，内部 Text = 型号 + 描述） |
| EtherCAT 从站行 | `TreeItemControl`，**判据：直接子节点里有一个 `EditControl AutomationId=editBox`**（就是节点号框，`ValuePattern` 可读写）。行上还挂着 `ButtonControl`「+」，点了不展开；主设备行没有 `editBox`，可以据此区分 |
| EtherCAT 端口行 | 从站行**被选中并按 VK_RIGHT 之后**才出现在 UIA 树里，是 `TreeItemControl`，行文本以 `X`（`X2`/`X3`/`X4`…）或 `Internal Port` 开头。不按右方向键时 `TreeView` 只暴露第一行，`GetChildren()` 永远拿不到后面的从站和端口。**2026-11-08 更正**：`ExpandCollapsePattern.Expand()` 同样有效，且不需要选中行（§18.1） |
| EtherCAT 右侧参数表 | `Custom cls=NodeOutlineParameter` → `List id=list`，行是 `ListItem`，每行第一个 `TextControl` 是字段名（`从设备数量`/`设备名称`/`节点号`…）。**2026-11-08 更正**：`设备名称` 的值是 `TextControl AutomationId='text'`，**没有 ValuePattern**，只能点进去 Ctrl+A 粘贴（§18.4）；`节点号` 不在参数表里，在树行的 `editBox` 上 |

EtherCAT 拓扑的层级（2026-10-31 实测）：

```
TopologyView (Tree)
└─ 主设备行                 ← 无 editBox，Name 像 “EtherCAT_Master”
   ├─ 从站行                ← 有 editBox（节点号）
   │  ├─ X2 / X3 / Internal Port   ← 端口行，必须选中从站行按 VK_RIGHT 才进 UIA
   │  └─ （挂在端口下的下一级从站行）
   └─ 从站行 …
```

遍历做法：`ssk.walk(topo, 10)` 收所有 `TreeItemControl`，其中"直接子节点含 `EditControl aid=editBox`"的就是从站行；对每个从站行 `walk(row, 4)` 找文本以 `X`/`Internal Port` 开头且 `is not row` 的 `TreeItemControl` 即端口行。**不要缓存行对象跨操作**——每次插入/删除之后树会重建，旧引用会失效，必须重新枚举。

结构体成员的入口：**不需要另开成员页**。右键菜单里的 `新建成员(M)` 会把成员作为**同一张 `PART_ListView` 里的子行**插到该结构体行下面（缩进显示），紧接着就地录入 `名称` → `Tab` → `数据类型` → `Enter` 即可。

脚本做法（2026-10-31）：单击结构体行的名称格选中 → `Esc` 退出可能进入的就地编辑 → 在同一格右键 → 点 `新建成员(M)` → 优先用 `GetFocusedControl()` 拿到的 `EditControl` 粘贴名称、`Tab` 粘类型、`Enter`；没有焦点编辑框时按坐标点表格最后一行下方的新行写入。校验用"行第一列 Text 是否等于成员名"（成员行与结构体行同表，只能按名称列区分，不能用"行里含名字"判断）。

若某次 `新建成员(M)` 不可用，再退回旧路：双击结构体名称格（先单击提交编辑，再双击双击同一位置）打开成员页；不要在行中点双击（常落在"偏移类型"列）。

## 15. 轴设置页（单轴编辑，2026-10-31 录制实测）

从工程树的轴行打开：单击行 + `Enter`；选项卡 `PaneControl Name='轴名 (轴号)'`。

| 区域 | 控件 | 说明 |
| --- | --- | --- |
| 顶部 | `ComboBoxControl` ×2~3（y 递增） | 轴类型（`伺服器轴` 等）和关联节点（`节点:N 型号(E00x)`）；**不要按序号硬取**，展开后看选项内容认：含 `伺服器轴` = 类型，以 `节点` 开头 = 关联节点（实测 247/270/377 三行，类型在下拉挂在 270 那行） |
| 左侧导航 | `CustomControl aid=axes_scale` | 缩放设置：`GroupControl '单元'`（`RadioButton '毫米'/'度'/'英寸'/'脉冲'`）、`GroupControl '行程距离'` |
| 左侧导航 | `CustomControl aid=axes_dynamics` | 动作设置：`GroupControl '速度/加速度/减速度'`（3 个 `EditControl`：最大速度 / 最大加速度 / 最大减速度） |
| 左侧导航 | `axes_io` / `axes_limit` / `count_mode_set` / `servo` | IO / 限制 / 计数模式 / 伺服驱动器设置 |
| 默认面板 | `GroupControl '详细设置'` + `DataGrid id=list` | PDO 映射表，行是 `DataItem`，行内有 `ButtonControl aid=toggleUnit` |

要点：

- 导航图标是 `CustomControl`（外面套 `ButtonControl`），点它的中心即可切面板；
  **先点导航再找组**，否则组不在 UIA 树里。
- 组合框的下拉项不在组合框下面，而在主窗口 `Window(cls=Popup) > Pane > ListItem`；
  项文字在 `ListItem` 的直接子 `TextControl.Name` 里（`ListItem.Name` 是 ViewModel 类名）。
  位置契约：首项 top ≈ 组合框 bottom + 0~2，左边缘与组合框左边缘差 ≤ 5（项可以比框宽）。
- 组里的数值框没有 AutomationId；按「同行的 `TextControl` 标签 + 右侧 `EditControl`」
  配对（纵向中心差 ≤ 12 px、标签右边缘在输入框左边缘左侧）。
  标签读不到时按行序兜底：`速度/加速度/减速度` 组内 EditControl 自上而下
  就是 最大速度 / 最大加速度 / 最大减速度（实测 y=252/293/313）。
- `GroupControl '单元'` 有 `AutomationId=subsectionExpander`，可作面板已切换的判据。

## 16. 编辑器内部形状（2026-11-06，`ss_uimap.py open` 实测 15 页）

> 采集法：`open <pid|auto> <out> <树路径…> --fit --all [--close]`，路径是 `labels` 给的编号（如 `1.0.2.3`、`0.3.0`）。原始输出：`openA.txt`（程序/数据）、`openB.txt`（组态）、`openC.txt`（设置）、`openE.txt`（`--all` 重采）、`openD.txt`（打不开的取证），**不随 Skill 发布**，需要时按上法重跑。
> 所有矩形是"窗口 slide 到 `(-26,-26)`"之后读的（§3.1），**只有结构和 id/Name 可移植，矩形只用来比大小和相对位置**。被测工程是某库工程，离线态。

### 16.1 每一页共有的外壳

```
Pane  cls='DocumentWindow'   Name='<文档名>'   HelpText='<文档名> - new_Controller_0'
├─ Button id='closeButton' Name='Close' HelpText='关闭'    15×15   ← 关这一页
├─ Image id='image'                                        20×20
├─ Text   id='title'   Name='<文档名>'                      ← 页签上的文字（页签宽度随它变）
└─ Custom cls='<页面根>'  (249,134 1388x632)               ← 真正的内容区，下面各节都从这里开始
```

- **`DocumentWindow` 自己的矩形只是页签**（`FB_AxisAllow` 是 `(248,102 140x32)`，`PrgMain - PRG_Example` 是 `(248,102 235x32)`）——别拿它当页面范围；内容区永远是那个 `(249,134 1388x632)` 的 `Custom`。
- **"有没有开页 / 开了哪几页"就数 `cls='DocumentWindow'` 的 `Pane`**，它的 `Name` 是文档名列表；`ss_uimap.py` 里对应 `doc_panes()`，`open` 用它比对开页前后的差集，`close` 用它记录 `# before:` / `# after:`。
- 多语言 POU 的文档名带父程序：实测 `PrgMain - PRG_Example`（不是 `PrgMain`）。**按名字找页必须精确匹配 `Name`**，`in`/前缀会误命中。
- `closeButton` **挂着 `Invoke` 模式却调不动**（`--pat` 实测 `PAT=Invoke`，但 `Invoke()` 抛异常，所以日志一律 `closed(click)`）：必须 `force_foreground(主窗口)` 再按它的矩形真点。关掉一个没改过的编辑器：不弹保存框、不冒新窗口（开页前存的 `popup_roots` 差集为空）。
- **`--pat` 实测出来的模式分布**（`openF.txt`）：`DocumentWindow` 自己**没有任何模式**；`textEditor`（`SyntaxEditor`）只有 **`Text`**（没有 `Value`）；`EditorView-Right` = `Scroll`；两条 `ScrollBar` = `RangeValue`；`Expander` = `ExpandCollapse`，它的 `HeaderSite` = `Toggle`；折叠块按钮 `ToggleButton-L*` = `ExpandCollapse`。判"这页能不能程序化读写"只看这几位，别猜。
- **`--all` 才看得全**：`全局变量` 页的 `TabItem '全局'` 状态是 off，默认遍历把它的整棵子树裁掉了，只剩 `VariableGroupTabControl` 空壳（`openA.txt` 那页 10 行 vs `openE.txt` 52 行）。凡"根在、内容空"的页，先加 `--all` 重采再下结论。

### 16.2 程序编辑器：ST 与 LD

判语言只看页面根 `ClassName`：`StructuredTextView` = ST，`LadderProgramView` = LD——不用读代码文本就能分流。

ST（`FC_TimeTransfer`、`FB_AxisAllow`…）：

```
Custom cls='StructuredTextView'
├─ Group cls='Expander'  → Button id='HeaderSite' → Text '变量'   1388×27   ← 变量声明区，默认折叠
├─ Thumb cls='GridSplitter'  (disabled)
└─ Custom cls='SyntaxEditorView'  (249,161 1388x605)
   └─ Text id='textEditor' cls='SyntaxEditor'   [kbd]
      └─ Pane id='EditorView-Right' cls='EditorView'
         ├─ Pane cls='TextViewLayerStack'            ← 正文画在这里，UIA 里没有字符节点
         ├─ Pane id='EditorLineNumberMargin'         43 px 行号槽
         ├─ Pane id='EditorOutliningMargin'  → Button id='ToggleButton-L2'   折叠块
         ├─ ScrollBar id='horizontalScrollBar'（ST 里常 disabled）
         └─ ScrollBar id='verticalScrollBar' → RepeatButton LineUp/PageDown/LineDown + Thumb
```

LD（`PrgMain`）：

```
Custom cls='LadderProgramView'
├─ Group cls='Expander' → Button id='HeaderSite' → Text '变量'
├─ Thumb cls='GridSplitter' (disabled)
└─ Custom id='RootControl' cls='LadderEditorView'
   ├─ Button id='ActivateRungCommentListButton'      → Text '行注释列表'   （25×302 竖排）
   ├─ Button id='LadderEditorGuideListToggleButton'  → Text '快捷键列表'   （25×303 竖排）
   └─ Pane cls='ScrollViewer'  [kbd]
      ├─ Text id='rungNumber'  Name='0'              ← 梯号
      ├─ Text id='PART_TextBlock' Name='STMultiSection(<GUID>)'
      ├─ Custom cls='SyntaxEditorView' → textEditor → EditorView-Right   （梯级内嵌一份 ST 结构）
      ├─ Thumb id='rightBottomThumb' / 'bottomThumb' / 'rightThumb' / 'thumb'   ← 画布内把手，别点
      ├─ ScrollBar id='PART_VerticalScrollBar'   (disabled)
      └─ ScrollBar id='PART_HorizontalScrollBar' (disabled)
```

- `textEditor`（`cls='SyntaxEditor'`，`IsKeyboardFocusable=True`）是**唯一可寻址的书写目标**，而 `--pat` 实测它**只暴露 `Text` 模式，没有 `Value`** ⇒ `ValuePattern.SetValue` 这条路根本不存在；写入仍是"点它 + 键盘/剪贴板"（见 pitfalls §31）。用 `TextPattern` 能否**读出**全文还没测（extending.md 待验证清单）。
- `STMultiSection(<GUID>)` 里的 GUID 是文档内部标识，**跨工程、跨保存都不稳定**，只能当"这一梯里嵌了一段 ST"的记号，不能当锚。
- 变量声明区是 `Expander`（`HeaderSite` 的子 `Text` = "变量"），**默认折叠 ⇒ 整张变量表不在 UIA 树里**。`open … --expand` 会对页内每个 `ExpandCollapse` 调 `Expand()` 再重走一遍，展开后的实测形状见 §16.7。
- 左侧那两个竖排按钮（`行注释列表` / `快捷键列表`）会占住 x=249 一列 605 px 高，点它们只弹浮层，不动数据——但会给后续 `--fit` 采样带来额外顶层窗口，采完记得 `Esc`。

### 16.3 数据页

`数据类型`（`1.1.0`）：

```
Custom cls='NamespaceDataTypeView'
├─ Button id='NamespaceToggleButton' → Custom id='namespace_tree_normal' cls='IconView'  ← 开/关命名空间树
├─ Button id='SelectedNamespaceToggleButton'                                (26×25)
├─ Edit   id='SelectedNamespaceTextBox' → Pane id='PART_ContentHost'        ← 当前命名空间路径的文本出口
├─ List   id='NamespaceBreadCrumbControl' cls='ListBox'
│   └─ ListItem Name='Omron.Cxap.Modules.DataType.ViewModels.NamespaceViewModel'
│      ├─ Button id='root' → Text 'root'
│      └─ Button（无 id，22×18）= 层级分隔箭头
└─ Custom cls='DataTypeView'
   └─ Tab id='DataTypeTabControl'
      ├─ TabItem '结构体' [SELECTED] → DataGrid id='PART_ListView' cls='ListView'
      ├─ TabItem '联合体'
      └─ TabItem '枚举类型'
```

`PART_ListView` 的表头是 7 列：第 0 列**无标题**（25 px，展开/图标）、`名称` 250、`基本类型` 335、`偏移类型` 188、`Byte偏移` 187、`Bit偏移` 188、`注释` 187。行 = `DataItem cls='ListViewItem' Name='…DefinedTypeViewModel'`（26 px 高），格 = `Custom cls='ContentPresenter'` → `Text`（名称/基本类型/注释）或 `ComboBox`（偏移类型）。**格上挂着 `disabled` 是常态**（没进入编辑态），不代表离线只读；实测行如 `st_Balluff / STRUCT / 巴鲁夫EIP模块`。

`全局变量`（`1.1.1`，**这一页必须 `--all`**）：

```
Custom cls='GlobalVariablesView'
└─ Custom cls='VariablesView'
   └─ Tab id='VariableGroupTabControl'
      └─ TabItem '全局' [SELECTED]（off，非 --all 时整棵被裁）
         ├─ Text '组筛选器'
         ├─ Button id='ToggleGroupButton'  HelpText='筛选/清除'
         ├─ ComboBox id='GroupingSelectionComboBox'
         ├─ DataGrid id='GlobalNamespaceGroupDataGrid' cls='CellEditor'
         │   └─ Header id='PART_ColumnHeadersPresenter'   8 列（HeaderItem 的 id 全是
         │       'CellEditor.Internals.Sorting'，即点标题=排序）：
         │       名称 150 / 数据类型 311 / 初始值 125 / 分配到 268 / 保持 75 / 常量 75 / 网络公开 150 / 注释 125
         │       每列两侧 PART_LeftHeaderGripper / PART_RightHeaderGripper（10 px 分隔把手）
         └─ Button Name='数据为空。点击此处添加项。'（1380×627，整块占位，可点）
```

- 与 §14 的分工：**"全局变量表可读"判 `id='GlobalNamespaceGroupDataGrid'`（`cls='CellEditor'`），"数据类型表"判 `id='PART_ListView'`（`cls='ListView'`）**，别互相套用。
- 空表时网格仍在树里、且外面盖一层 `数据为空。点击此处添加项。` 的 `Button`；**别把这行文本当错误**，也别在只需读表时点它（它的作用是按提示新增行）。

### 16.4 设置页家族（`ConfigurationView`）

本轮 9 个设置类页面里 **5 个根类都是 `ConfigurationView`**：`操作设置`(0.3.0)、`内存设置`(0.3.2)、`任务设置`(0.7)、`OPC UA服务器设置`(0.9.0)、`DB连接服务设置`(0.10.0.0)。形状：

```
Custom cls='ConfigurationView'
├─ Pane cls='ScrollViewer'  (249,134 75x632)                 ← 左侧导航条
│   └─ Custom cls='SectionView' × N  (58×78，纵向间隔 83 px)
│       ├─ Button (52×52) → Custom id='<图标名>' cls='IconView' (40×40)   ← 这一节的锚
│       └─ Text（Name 为空，58×18）                                       ← 节标题（本例读不到文字）
└─ Custom cls='<××>SectionDetailsView'  (349,136 1288x627)   ← 右侧正文（类名逐页不同）
    ├─ Text id='TitleTextBlock'  Name='基本设置' / 'CJ系列单元的内存设置' / '服务器设置'
    ├─ Custom id='<同一个图标名>' cls='IconView' (40×39)
    └─ Pane cls='ScrollViewer'
        └─ Group cls='Expander' id='subsectionExpander'      ← 小节；Name = 小节标题
            ├─ Button id='HeaderSite'  Name='操作设置' / 'SD内存卡设置' / '安全设置' …
            └─ Custom cls='ComponentsFieldView' × 每行一项
                ├─ Text '启动模式'                            ← 标签
                ├─ RadioButton '运行模式' [SELECTED] / '编程模式'
                ├─ Edit cls='TextBox' → Pane id='PART_ContentHost'
                └─ Text 's'                                   ← 单位，不是值
```

- **右侧正文的类名不固定**（实测 `HelpDefaultButtonWithinSectionDetailsView` / `SectionDetailsView` / `CjMemorySettingSectionDetailsView`），别按类名匹配；判据用"它是 `ConfigurationView` 的子元素、矩形 `(349,136 1288x627)`、且下面有 `TitleTextBlock`"。
- 图标 `id` 就是节的稳定名：`操作设置` = `CPU_setting` / `fins` / `eventlevel_setting_normal`；`内存设置` = `CJunit_memory_setting_L_normal`；`OPC UA` = `opcua_svr_setting_L_normal`；`DB连接服务` = `DB_service_setting_L_normal`。**切节 = 点那层 52×52 `Button` 的中心**（点 `IconView` 也行，它在 Button 正中）。
- `任务设置` 的 6 个节**不是 IconView**，`Custom` 没有 id、只有类名：`BaseTaskGeneralSetting` / `BaseTaskUnitSetting` / `BaseTaskPOUSetting` / `BaseTaskInterfaceSetting` / `BaseTaskStatusMonitor` / `BaseTaskTimeMonitor`。所以判据要退化成 `cls` 前缀 `BaseTask`；**这 6 个 id/类名就是任务设置里唯一稳定的节锚**。
- 设置项一律"标签 `Text` + 同排控件"配对（和 §15 同一条规矩），`ComponentsFieldView` 一层就是一行；`RadioButton` 是互斥组、`Edit` 收数值、`ComboBox` 收枚举。个别行是 `Button '编辑'`（离线态 disabled，实测在 SD 内存卡两处）。
- **这些页面没有"应用/确定"按钮**：改动直接写进工程，落盘靠保存。别去找确认按钮，也别因为找不到确认就重复点。
- `任务设置` 正文里是任务表：`Custom cls='TaskGeneralSettingsView'` → `Pane id='DG_ScrollViewer'` → 9 列（第 0 列无标题、`任务类型` 206、`任务名称` 125、`周期/执行条件` 125、`详细执行条件` 125、`任务周期超出检测` 125、`任务超时检测时间` 125、`执行优先级` 25、`变量访问时间[%]` 37）+ 每行 `DataItem cls='DataGridRow'`（**`Name` 为空，23 px**，任务名要从 `任务名称` 列的格子里读）。表下两个 `Button`：`Name` 为空、**`HelpText='添加任务' / '删除任务'`**（删除在离线未选中时 disabled）。

### 16.5 组态页：EtherCAT / CPU 机架 / I/O 映射 / 事件设置

`EtherCAT`（`0.0`）：

```
Custom cls='MainEditorWindow'
├─ Custom cls='TopologyEditor'  (923 宽)
│   └─ Tree id='TopologyView' cls='TreeView'
│       └─ TreeItem Name='…NexEcatConfigurationEditor.ViewModel.MasterDeviceTreeNode' [SELECTED]
│          ├─ Button（44×19，无 id）        ← 点了不展开（见 §14.1 从站行）
│          ├─ Custom id='NEX' cls='IconView'
│          └─ Text '主设备' ×2              ← 同一行的"名称"和"型号"两格
├─ Thumb cls='GridSplitter' (4×632)         ← **别点**
└─ Custom cls='NodeOutlineParameter'
    ├─ Custom cls='ParameterSettingTable' → List id='list' cls='ListBox'（行高 20/21）
    ├─ Thumb cls='GridSplitter' (449×4)
    └─ Group cls='GroupBox' Name='设备名称' → Pane cls='ScrollViewer'（该字段的说明文字）
```

`CPU机架: X总线`（`0.1.0`）左侧换成 `Custom cls='MainEditorView'` → `LeftSideBusEditorView` → `Pane cls='ScrollViewer'` → `List id='unitList'`（`ListItem Name='…LeftSideBusMasterItemViewModel'`，整列 628 px）+ 一个 18×138 的 `Expander`；**右侧与 EtherCAT 完全同构**（`GridSplitter` → `UnitSettingsView` → `ParameterSettingTable` → `list`，再加 `GroupBox '设备名称'`）。

`ParameterSettingTable` 的行类名后缀**直接告诉你这行怎么读写**——这是本轮最有用的发现：

| `ListItem` 类名后缀 | 实测字段 | 值控件 | 读写 |
| --- | --- | --- | --- |
| `StringParameterItem` | 设备名称 | `Text id='text'` | 可改（就地编辑，本轮未做写入） |
| `LabelParameterItem` | 机型 / 产品名称 / 从设备数量 / 参考时钟 / 单元版本 / 型号 / 单元宽度 | `Text`（`Name`＝`HelpText`＝值） | **只读** |
| `IntegerParameterItem` | 电缆总长度 / 从设备启动等待时间 / PDO通信超时检测次数 | `Text id='text'` + 单位 `Text` | 数值 |
| `BooleanParameterItem` | 故障弱化操作设置 | `ComboBox id='editControl'` | 下拉（使用/不使用） |
| `EnumerableParameterItem` | 版本检测方法 / 串口号检测方法 / 序列号检查 | `ComboBox id='editControl'` | 下拉 |
| `LabelWithButtonParameterItem` | 传送延迟时间 | `Button id='OpenTransmissionDelayTimeSetting'`（文案「编辑设置」） | **开子对话框**，本轮未进（留给 #31） |

- 字段名 `Text` 的 `Name` 与 `HelpText` 相同；值格也常把自身文本抄进 `HelpText`，所以**读值优先 `Name`，`Name` 空再看 `HelpText`**。
- `Text|||TextBlock||-|(0,0 0x0)` 这种 0×0 空格是**行模板里的占位格**，不代表数据丢了。
- 单位文字（`微秒` / `米` / `秒` / `次` / `W` / `mm`）是独立 `Text`，永远不要当值。

`I/O 映射`（`0.2`）：

```
Custom cls='IOMapBaseView' → Custom cls='IOMapView'
└─ Custom id='dataGridControl' cls='IOMapDataGrid'
   └─ DataGrid cls='DataGridEx'
      ├─ Header id='PART_ColumnHeadersPresenter'  8 个 HeaderItem：
      │     位置 75 / 端口 312 / 说明 188 / R/W 43 / 数据类型 88 / 变量 125 / 变量注释 250 / 变量类型 125
      └─ DataItem cls='DataGridRow' Name='…IOMapItemViewModel'（24 px/行）
         ├─ HeaderItem cls='DataGridRowHeader'（25 px 行头）
         └─ Custom cls='DataGridCell'  Name='项: …IOMapItemViewModel，列显示索引: N'
            ├─ Text（格内文本；变量格 id='textVariable'）
            └─ Image id='imageUnit'（端口列的设备图标）
```

- **认列要用格 `Name` 里的"列显示索引" + 矩形左边缘，不能数第几个子节点**：本例出现的索引是 `0,1,2,3,5,7,8,9`（4 和 6 被隐藏/合并），而表头只有 8 个；按序号对齐会把"数据类型"当成别的列。
- 索引 1（端口）格里的文本形如 `EtherCAT网络配置`，真正的从站/端口层级在 §14.1 的 `TopologyView` 里，不在这张表。

`事件设置`（`0.6`）—— 只有一根 `EventTableView`，是这几页里唯一带明确增删按钮的表：

```
Custom cls='EventTableView'
├─ CheckBox Name='编辑多个表'
├─ ComboBox id='LanguageComboBox'（disabled）
├─ Text '注释' + Edit（1080 px 宽）
├─ DataGrid id='DataGridView' cls='DataGrid'   5 列：事件代码 61 / 事件名称 61 / 事件等级 61 / 组 25 / 详细 1152
├─ Button id='AddButton'（38×31） / Button id='DeleteButton'（disabled）
├─ Text '发生严重的控制器错误时，编辑在界面上显示的事件详细信息。'
└─ Edit id='SystemAlertMessageTextBox'
```

### 16.6 打不开的节点（本工程实测，别再试第二遍）

`0.4.0 轴设置`、`0.4.1 轴组设置`、`0.5 Cam数据设置`、`0.8 数据跟踪设置`、`1.2.0 PrimaryTask`、`1.2.1 TempCtrlTask`：Enter 与"取消选中 + 真双击"两条通道都试过，每行都留了取证（`openD.txt`）：

```
## 0.4.0  轴设置  enter then dblclick did not open a document
   (tree focus=True, row hit by click=True/True, caret kept=True, rows 85->85,
    kids=0, new windows=[], ancestors: 0=expanded, 0.4=expanded)
```

判读：`tree focus=True` + `row hit by click=True/True` 说明点击确实落在目标行；`rows 85->85` 说明没有增删行；`new windows=[]` 说明没弹对话框——**所以这不是定位失败，而是这类节点在没有对应实体（轴 / 轴组 / 数据跟踪 / 任务分配）时根本没有可打开的文档**。`1.2.1` 是唯一 `kids=1` 的（任务下挂着 POU），仍然不开页。

- 与 §15 的关系：2026-10-31 那份"轴设置页"是从**有轴实体的工程**里打开的（页签 `Name='轴名 (轴号)'`），点的是轴行而不是 `0.4.0` 这个容器行。要在库工程里读轴设置，得先按 #29 记的右键菜单在 `0.4.0` 下新建轴，之后 §15 的控件表才适用。
- 采完一轮记得收尾：`open … --close` 在同一轮里开→测→关，或补跑 `close auto <out> --all`。留编辑器过夜会让下一轮的 `panels`/`--fit` 采样混进脏页（本轮就靠 `close01.txt` 那次把残留的 3 页清成 `# after: []`）。

### 16.7 展开后的 POU 变量表（`open --expand` 实测，`openG.txt`）

`open … --expand` 对页内每个 `ExpandCollapse` 调 `Expand()`，然后**重走整页**。ST 与 LD 展开后露出的东西一模一样（变量表是 POU 级的，与语言无关）：

```
Custom cls='StructuredTextView' | 'LadderProgramView'        ← 折叠的那条 Expander 现在占了 1388x160
├─ Group cls='Expander'  → Button id='HeaderSite' → Text '变量'   (249,134 1388x27)
├─ Custom cls='VariablesView'                                 (249,161 1388x160)
│  ├─ Group id='UsingExpander' cls='Expander' → Text '命名空间 - 使用'   ← USES 列表，还能再折一层
│  └─ Tab id='VariableGroupTabControl'
│     ├─ TabItem '内部'    [SELECTED]  （程序：内部 / 外部；功能：内部 / 输入/输出 / 外部 / 返回值）
│     │   ├─ DataGrid id='DefaultGroupDataGrid' cls='CellEditor'   ← 就是这张 POU 变量表
│     │   │   Header id='PART_ColumnHeadersPresenter'  7 列（每列 id='CellEditor.Internals.Sorting'）：
│     │   │     名称 188 / 数据类型 150 / 初始值 125 / 分配到 100 / 保持 75 / 常量 75 / 注释 125
│     │   │   └─ DataItem cls='DataGridRow' Name='Omron.Cxap.Modules.Variables.ViewModels.VariableViewModel'（25 px/行）
│     │   │      ├─ HeaderItem cls='DataGridRowHeader' 37 px（行号格，无文字）
│     │   │      └─ Custom cls='DataGridCell' × 每列一个（下面讲怎么认）
│     │   └─ Button '数据为空。点击此处添加项。'（这一组空表时才在）
│     ├─ TabItem '输入/输出'   ← 功能才有；没切过去时它的子树是 off
│     ├─ TabItem '外部'
│     └─ TabItem '返回值'      ← 功能才有
├─ Thumb cls='GridSplitter'（展开后才带 kbd，(249,317 1388x4)）
└─ 代码/画布区被挤到 (249,321 1388x445)（折叠时是 161/605）
```

**变量表单元格怎么认（这条最实用，直接对上 pitfalls §22 的痛点）**：

| 情况 | 实测 | 判据 |
| --- | --- | --- |
| 格有值 | `Custom\|aiTempMeasRaw\|\|DataGridCell\|aiTempMeasRaw\|kbd` | **`Name` 与 `HelpText` 都等于该值**；子 `Text` 也是同一串 |
| 格为空 | `Custom\|项: …VariableViewModel，列显示索引: 2\|\|DataGridCell\|\|kbd` | **`Name` 形如 `项: <ViewModel>，列显示索引: N`、`HelpText` 空**，子 `Text` 是空串 ⇒ **这就是"空名/空值行"的机器可读形态** |
| 布尔格（保持 / 常量） | `…列显示索引: 4` / `5` 里面是 `CheckBox`（20×20） | 用 `Toggle` 模式或点它，不要按文本读 |
| 列次序 | 索引 0=名称、1=数据类型、2=初始值、3=分配到、4=保持、5=常量、6=注释 | **有值的格子 `Name` 不带索引**，所以"按索引认列"只对空格有效；认列一律用**矩形左边缘 + 表头顺序**（和 §16.5 I/O 映射同一条规矩） |
| 行在屏幕外 | 最后一行整行带 `off` | `--all` 才收得到；只读文本不受影响，真点要先 `--fit` |

展开动作本身**不改数据**（只是视图状态），实测展开后照样 `closed(click)` 且不弹保存框。

`VariableGroupTabControl` 的页签集合**按 POU 种类变**（实测三类，`openG.txt` / `openH.txt`）：

| POU 种类 | 实测页签 | 备注 |
| --- | --- | --- |
| 程序（`1.0.0.0.0 PrgMain`，LD） | `内部`[SELECTED] / `外部` | 只有 2 个 |
| 功能（`1.0.1.0 FC_TimeTransfer`，ST） | `内部` / `输入/输出` / `外部` / `返回值` | `返回值` 是功能独有；"输入/输出"是**一个**页签，名字里带斜杠 |
| 功能块（`1.0.2.3 FB_AxisAllow`，ST） | `内部` / `输入/输出` / `外部` | 没有 `返回值` |

要点：**只有选中的页签里有已实化的网格**，其余页签的子树是 `off`——要读全一张 POU 的变量，必须逐个 `TabItem` 切过去再走（切页签本身未测，`SelectionItem.Select()` 是否可用属未知）。空的那一组仍然挂着 `Button '数据为空。点击此处添加项。'`（`off`）。

`--expand` 对其他页也照样跑，但**只有"页里真有折叠区"时才有增益**，实测两种结果都要预期到：

- **设置页**（`0.3.0 操作设置`）：`--expand` 点到 6 个 `Group id='subsectionExpander'`（`操作设置` / `SD内存卡设置` / `SD内存卡程序传送设置` / `SD内存卡恢复设置` / `事件记录设置` / `安全设置`），**它们本来就是展开的**，`Expand()` 是无操作——展开前后两次落盘逐行相同（138 行 vs 138 行，只差页头）。所以 §16.4 的"读不到某项设置"不能靠 `--expand` 解决，那是**节没切对**（点左导航 `SectionView`）的问题。
- **全局变量页**：`--expand` 点到的是 `GroupingSelectionComboBox`（它带 `ExpandCollapse`），落盘内容不变。**注意这条通道对组合框调 `Expand()` 会真的把下拉打开**，本轮实测它没有留下展开态、也没弹新窗口，但**换版本后不保证**——只要下拉卡住就 `esc(1)`。
- ST/LD 里折叠块按钮 `ToggleButton-L*`（`ExpandCollapse`）会被一并 `Expand()`，实测无害。

顺带露出来的两处（折叠/未走时看不到）：

- ST 编辑器 `EditorView-Right` 里还有 `EditorIndicatorMargin` / `EditorSelectionMargin` / `EditorRulerMargin` / `EditorWordWrapGlyphMargin`（全部 `off`）和一组 `Text '跳转: '` + `Edit` + `Button`（跳转行的控件，`off`）。
- `Custom cls='InstanceSelectorView'`（`off`，与代码区同矩形）：`Text '请选择一个监测实例。'` + `Button id='SelectButton'`（文案「选择」）+ `List id='InstanceListBox'`。**这是在线监视时选实例的面板，离线态恒 off**——将来做在线功能时它是入口，但现在别点（会牵扯在线状态，见 SKILL §7 红线 2）。
- 判"POU 变量表可读"用 `id='DefaultGroupDataGrid'`；**全局变量页是 `GlobalNamespaceGroupDataGrid`**（§16.3）。两者都 `cls='CellEditor'`，列序前 6 列完全一样（名称/数据类型/初始值/分配到/保持/常量），差别只在**全局多一列 `网络公开`**（7→8 列）。**任何按列序取值的代码都必须先确认是哪一个 id**。

### 16.8 被引用库的 FB 源码页（`转到下层`）与工具箱库分组（2026-11-21 实测）

引用库（`.slr`）里的 POU **不在工程树里**，只能从"库 FB 的实例"往下钻。整条链实测如下：

```
Button| <库名> ( <版本> )|groupToggle|Button||kbd      ← 工具箱库分组（折叠时不暴露子项）
Button|||Button|kbd                                                          ← 每个 POU 一行
  Custom|||FunctionBlockToolboxControl|                                      ← FB（Function 是 FunctionToolboxControl）
  Edit|textBox|TextBox
    Text| <FB名>|TextBlock                                           ← POU 名（带前导空格）

右键梯形图上的库 FB 实例 → MenuItem '转到下层'（Ctrl+Shift+L）→ 新 DocumentWindow：
Pane|<FB名>||DocumentWindow|<FB名> - <实例名>|kbd
  Custom|||StructuredTextView|(275,295 1385x632)
    Group|||Expander|kbd                       ← 变量表折叠区（Button|HeaderSite → Text|变量）
    Custom|||SyntaxEditorView|(275,322 1385x605)
      Text||textEditor|SyntaxEditor|kbd        ← 全文在这里
        Pane|Editor View|EditorView-Right|EditorView
          Pane|||TextViewLayerStack
          Pane|Editor Line Number Margin|EditorLineNumberMargin
          ...
```

要点：

- `SyntaxEditor` 的 `Name` 为空、`AutomationId` 恒为 `textEditor`、`class='SyntaxEditor'`，**只有 `Text` 模式**（无 `Value`）；
  `TextPattern.DocumentRange.GetText(-1)` 一次拿到整段 ST（实测原始字符数与归一化后字符数不同，差异只在换行）。
- 文档窗口 `Name` 是**短名**（`<FB名>`），完整标题在 `ClassName` 后面的 `DocumentWindow` 显示名里
  （`<FB名> - <实例名>`）；`--title` 过滤按短名前缀匹配。
- 梯形图里的 FB 实例**不在 UIA 树里**（编辑器只暴露外壳 + 变量表 + 语法编辑器），所以 `转到下层` 只能靠**坐标右键**；
  但菜单项要**按 Name Invoke**，不要按坐标点——菜单位置随 DPI/布局变。
- 工具箱分组按钮的 `AutomationId` 是 `groupToggle`；分组名形如 ` <库名> ( <版本> )`（**带前后空格**），
  按 `in` 匹配而不是 `==`。

## 17. 轴设置表（WinForms）与轴 PDO 过程数据（2026-11-07 实测）

> 被测：某运动控制工程（34 个 EtherCAT 从站 / 6 根轴），Sysmac V1.68 64bit；实测基线（1920×1080 最大化、125% 缩放），换环境先重测几何。
> 原始落盘：`axcell.txt`、`axhwnd1.txt`、`set_out1_a1.txt`、`devprobe_a1.txt`、`pd_a1_28b.txt`、`pdoapp1b/1c/1e.txt`，**不随 Skill 发布**，需要时按 recipes §R 重跑。
> 端到端做法与脚本见 [recipes.md §R](recipes.md#r-轴从站绑定与-pdo-过程数据映射2026-11-07-实测-唯一可行界面路线)。

### 17.1 轴设置表：UIA 全盲，但格子里有一个真的 Win32 组合框

`轴设置` 节点右键 → `轴设置表(S)` 会开一个文档页签 `轴设置表`，页面根是
`CustomControl ClassName='AxisSettingTableView'`，里面是 `WindowsFormsHost` 宿主的一张
WinForms 网格。**UIA 树到此为止——没有任何 `DataItem`/`Edit`/`ComboBox` 子元素**（`scan`/`--all`
都只看到一个空 Custom）。别再花时间找单元格。

但**真点一格会浮出一个 Win32 编辑控件**（`EnumChildWindows(主窗口)` 抓得到，不在 UIA 树里）：

```
class='WindowsForms10.COMBOBOX.app.*'   rect=格子矩形 (608,510,757,538)   ← app 后缀每次运行随机，按前缀匹配
CB_GETCOUNT(0x0146)=34   CB_GETCURSEL(0x0147)=21   CB_GETLBTEXT(0x0148) → '节点:39 <型号>(<设备名>)'
```

- `cursel` **就是模型真值**，不是显示态；`items()` 列出全部 34 个从站（轴页顶部那个"只显不写"的
  输出设备框给不了这些）。
- 提交路线：对**已聚焦的关闭态**组合框逐次 `{UP}`/`{DOWN}` → `{ENTER}`。关闭态方向键改选中会发
  `CBN_SELCHANGE`，这正是网格监听的信号；**`CB_SETCURSEL` 只改文字、不发通知，不能用**。
- 读消息必须先把 `SendMessageW` 的原型改回来（`import uiautomation` 会把它改成 32 位 `LPARAM`，
  64 位 `HWND` 会被截断——与 §16 前面 `TVM_*` 那个坑同源）：
  `u.SendMessageW.restype = ctypes.c_ssize_t`，`argtypes=[HWND, c_uint, c_void_p, c_void_p]`，
  `CB_GETLBTEXT` 的缓冲用 `ctypes.cast(b, c_void_p)` 传。

**几何（1920×1080 最大化实测，只能当"本轮现读"的基线，跨机器必须重测）**：

- 值列每条 150 px，`轴名称` 结束于 x=607；列中心 `轴0 533` / `轴1 683` / `轴2 833` /
  `轴3 983` / `轴4 1133` / `轴5 1283`（示例键名与 `ss_axtable.py` 默认 COL 一致；列头顺序＝轴号顺序，**用 `ss_axtable.py geom <png>` 量竖线，别用眼睛看缩略图**）。
- 第一条数据行 top=236，行距 25 px；行序：`轴号0 运动控制1 轴使用2 轴类型3 反馈控制4
  输入设备1=5 通道6 输入设备2=7 通道8 输入设备3=9 通道10 输出设备1=11 通道12 输出设备2=13
  通道14 输出设备3=15 通道16`，`单位换算设置` 组头在 y≈660。
- 量坐标的算法：截图 → 逐列/逐行找"连续同色段"（`ss_axtable.py` 里的 `vlines()`/`hlines()`，
  子命令 `geom`）。Read 工具给的缩略图是缩放过的，**按它估坐标必然偏**。

**2026-11-17 补充：行集合漂移 + 剩余行的真实通道**（Read-only probe，V1.68 实测）

- 本轮工程的表头下多了一行 `轴名称`，旧基线 17 行序列实际整体下移一行。不要硬套 `Y0=236`；先用 `ss_axtable.py geom` 找水平分隔线，再用已知有值的 `输出设备1` 格做校准：双击后应浮出 `WindowsForms10.COMBOBOX.app.*`，`CB_GETCOUNT` 为从站数（本轮 34）+ `＜未分配＞`，`CB_GETCURSEL` 指向当前绑定。校准成功后再推其它行坐标。
- `输出设备2` / `输出设备3`：**单击只画出编辑器外观，不产生 Win32 子窗口；真实双击才浮出 `WindowsForms10.COMBOBOX.app.*`**。因此 `ss_axtable.py set/get` 的单点击路线只保证 `out1`，`out2/out3` 必须先双击 realizing combo（可写一个只做“双击 → `CB_*` 读”的包装脚本）。
- 本轮工程所有轴的 `输出设备2/3` 与各 `通道` 归档值都为空。实测 `out2`/`out3` 的 combo 只有 **1 项 `＜未分配＞`**；`in1ch/in2ch/in3ch/out1ch/out2ch/out3ch` 双击后 **既不出现 COMBOBOX 也不出现 EDIT**。由此得到的是可移植结论：**通道行没有通过这套 Win32 编辑控件写入的证据**；`out2/out3` 虽有 combo，但在没有可选目标的工程里无法验证提交通道，记为 `INCONCLUSIVE / NON_TRANSFERABLE`，不要声称已打通。
- 若换到确有 secondary 设备/通道分配的工程，应重跑同一 probe：只有 combo 出现 **≥2 项** 且 `cursel` 可读到非 `＜未分配＞` 值时，才继续做“原值写回”的可逆写入验证；否则不写。

### 17.2 轴页 PDO 映射表（`MultiPDOTableFieldView 详细设置`）

轴页 `轴基本设置` 底部那个 `GroupControl '详细设置'` 展开后是 WPF 网格
（`DataGridControl id='list'`），列 = `功能名称 / 设备 / 过程数据`：

```
Custom cls='MultiPDOTableFieldView'  →  Group '详细设置'(subsectionExpander)   ← 它自己也是折叠 Expander
└─ DataGrid id='list'
   ├─ DataItem cls='DataGridRow'  '输出(控制器到设备)'   ← 组行
   │   └─ Custom cls='DataGridCell'
   │        ├─ Button id='toggleUnit' PAT=Toggle          ← 开关是 **Button**
   │        │    └─ Text id='toggleButton' Name='+'|'-'   ← '+'=折叠 / '-'=展开，状态在**子 Text** 上
   │        └─ Text '输出(控制器到设备)'（另有一份 IsOffscreen 的同名副本）
   │   └─ （展开后才有子行）DataItem '1. Controlword'
   │        ├─ Text  '1. Controlword'                    ← 功能名，前缀是 FunctionNumber
   │        ├─ ComboBox id='comboDevice'
   │        └─ ComboBox id='comboProcessData'
   ├─ DataItem '输入(设备到控制器)' …
   └─ DataItem '数字输入' …
```

- **组行折叠时子行根本不在 UIA 树里**，`comboDevice`/`comboProcessData` 也不存在；看起来"绑上了却没写 PDO"基本都是这个。
- 折叠状态**只能读 `toggleUnit` 里面那个 `Text id='toggleButton'` 的 Name**（`ss_axpdo.py peek` 是抓这个形状的工具）；按"`AutomationId=='toggleUnit'` 的 TextControl"去找是找不到的，会退化成"零点击的成功"，详见 [pitfalls.md §67](pitfalls.md#67-pdo-组的-toggleunit是-button-不是-text第一遍读值会说谎2026-11-07-实测)。
- 每个**子功能行也带一个 `toggleUnit`**，点它永远读 `'+'`（点了也不变），别去点它——只点三个组行的。
- 网格是虚拟化的：滚动时 `DataGridRow` 元素被回收，**任何"先抓控件再回来写"的写法都会拿到过期元素**；必须"找行→写行→再找行"一次一个（`find_row()` 先滚到底再回顶，计划按网格顺序排最省）。
- `设备` 下拉**按已绑定设备过滤**：绑定对时只给 `节点:20 <型号>(<设备名>)` + `＜未分配＞`；绑定不对时只有 `＜未分配＞`——这就是免保存判断绑定真伪的探针。

### 17.3 `过程数据` 下拉的文本契约（本轮最容易被 substring 咬死的一条）

- 一项 = **一个位**，不是对象：`'60FDh-00.1(Transmit PDO mapping 1_Digital inputs_60FD_00)'`；实测某伺服共 **257 项**，顺序 = 各 PDO 组的对象次序（`6040h(16) 6060h(8) 607Ah(32) 60B8h(16) 603Fh(16) 6041h(16) 6061h(8) 6064h(32) 60B9h(16) 60BAh(32) 60F4h(32) 60FDh(32) ＜未分配＞`）。
- **匹配一律 `caption.startswith(key + '(')`**：`'60FDh-00.1'` 是 `'60FDh-00.10'` 的子串，按 substring 会静默映射到错的位。
- 下拉**打开时就定位到当前选中项**（未分配 → 列表底部），所以扫描必须**先向上再向下**；滚轮要点在**弹层自己的矩形中心**（点 `组合框中心+偏移` 会滚到网格上去，列表一动不动）。
- 虚拟化：一次只实化约 60 项，其余枚举得到但 `IsOffscreen=True`，**矩形是过期的，绝不能点**；`SelectionItemPattern` 在这些行上是 `None`（`Select()` 不可用），`ScrollItemPattern` 在 `uiautomation` 包装上直接 `AttributeError`。可用的兜底是**键入键名**（WPF 文本检索把高亮跳到该项）再 `Enter`。

**跨轴/型号是否同集合（2026-11-18 只读测绘，见 §17.6）**：不必逐轴去点 257 项下拉——`.smc2` 内 EtherCAT 配置 `.dat`（.NET BinaryFormatter，内嵌 `<Dictionary>` XML 对象字典）里就有各从站型号的对象字典全集，可离线按型号哈希比对；本工程 5 个字典只落 **3 种集合**。

### 17.6 PDO 过程数据项集合的跨轴/型号覆盖（2026-11-18 只读测绘）

**结论：项集合由所连从站型号的 ESI 对象字典决定，不是每轴一套。** `.smc2` 里 `<GUID>/<EtherCAT 配置>.dat`（数 MB，.NET BinaryFormatter）内嵌若干 `<Dictionary>…</Dictionary>` XML 对象字典（`ETG.2000` 风格 `<Object><Index>#x…</Index><Name>…</Name>`），每一项过程数据 = 某个 PDO 映射对象（`0x1Axx` 发送 / `0x16xx` 接收）里的一个位，下拉的 257 项就是按位展开的。

本工程 5 个 `<Dictionary>`，按对象索引集合的 SHA256 归为 **3 种**（可离线从归档按索引集 SHA 复现，全程不碰 UI）：

| 字典 | 从站型号 | ProductCode | 对象数 | TPDO / RPDO | 索引集 SHA | 对应轴 |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | InoSV660N | `000C010D` | 36 | 1 / 1 | `338394e3…` | 某系列（24 行映射） |
| 1 | MEDLT83BM | `6158000A` | 637 | 4 / 4 | `20edd589…` | 某型号伺服系列 A（4 轴） |
| 2 | MBDLT25BM | `61580006` | 637 | 4 / 4 | `20edd589…` | 某型号伺服系列 B（4 轴） |
| 3 | MCDLT35BM | `61580007` | 637 | 4 / 4 | `20edd589…` | 某型号伺服系列 C（4 轴） |
| 4 | CTEU-EtherCAT（Festo 阀岛） | `572556` | 27 | 1 / 0 | `c04a499c…` | 阀岛（非轴，未参与 PDO 映射） |

- **可推广边界**：三款 Panasonic(6158…) 伺服虽然型号名不同，**对象索引集合逐字节相同**（同一 SHA `20edd589…`），其 `过程数据` 下拉项集合可视为同一套；InoSV660N（36 对象）与 Panasonic（637 对象）是**两套不同集合**，不能拿一款的下拉项去配另一款。按型号分组判断即可，不必逐轴点下拉。
- **归档侧佐证**：34 轴里 32 轴有 PDO 映射，分两族——17 行映射（11 个唯一对象，Panasonic 系列）/ 24 行映射（18 个唯一对象，InoSV660N 与 R88D-KN04H-ECT）；2 个 spare 轴（轴0/26）无映射。（可按轴统计映射行数离线复核）。
- **UI 交叉验证的边界**：只读点开轴1（Panasonic 伺服）`1. Controlword` 行的 `过程数据` 下拉，弹层高仅 70 px、只实化 3 项（当前 `6040h-00.0`、`60F4h-00.0`、`＜未分配＞`），滚轮 80+600 步都不新增 ⇒ **该行下拉是按功能/设备上下文过滤后的短列表，不是 257 项全集**。所以 §17.3 的"257 项"来自能展开全量的行/设备，不能假设每行都给全集；这属于 `INCONCLUSIVE`（未在能出全量的行上重测）。全程 Esc 关闭、未点任何项、未改值。
- **R88D-KN04H-ECT**（轴4/27 的设备）在本工程 ESI `.dat` 中**只有设备引用**（节点 GUID→型号串 + `6040:00…` 映射），没有独立 `<Dictionary>` 块 ⇒ 其 257 项全集来自本机已安装 ESI、不在工程归档里；"换机器是否仍同集合" `INCONCLUSIVE`。
- 复现配方：离线从归档提取各 `<Dictionary>` 索引集并分组 + 按轴统计映射族；UI 只读 `ss_axpdo.py collect`（不动折叠）+ 开下拉滚轮收集后 Esc（不点项）。

### 17.4 界面上灰掉、因此"抄不过来"的轴参数（两份工程都 `IsEnabled=False`）

| 轴 | 参数 | 源 / Copy |
| --- | --- | --- |
| 轴0（未使用的轴） | `NexAxisAxisType` | `NexAxisServoType` / `NexAxisVirtualServoType` |
| 轴0 | `NexAxisUnitsNumerator` / `Denominator` | `262144/2` / `10000/10000` |
| 轴0 | `NexAxisMaxVelocity` / `NexAxisMaxJogVelocity` | `100/1` / `400000000/1000000` |
| 每一轴 | `NexAxisHoming/NexAxisStartDirection` | 轴1 源=`NegativeDirection`，Copy=`PositiveDirection` |

`轴使用` 在两边都是 `NexAxisNotUsingAxisNotChangable`（"不可更改为使用轴"那一档），所以这些格子的灰置是**软件按其它条件算出来的**，不是缺权限。**结论：这类差异不能靠界面消除，只能如实报告**（改文件属 [offline-surgery.md](offline-surgery.md) 范畴，且不是用户要的"照着添加照着修改"）。

- 判据在归档里就能读出来，不用去界面摸：`NexAxisUseAxis` 的值带 `NotChangable` ⇒ 该轴**整页**参数（类型/单位/速度）必然灰；`NexAxisStartDirection` 在**已使用**的轴上也是 `en=false`（实测 轴1 两边都灰），说明它由同页另一个选择项（原点返回方式一类）派生——**别为了改它去翻那个上级开关**。
- **不要试图"临时打开 `轴使用` 把格子变活再改"**：未实测，而且 `轴使用` 一改成使用，软件会去建/占用 `AXIS_REF` 全局变量与任务分配（本轮就为清理这类残留行做过一整轮，见 SKILL §1 里"删除变量表空名行"相关的坑 §22），改回来未必清干净——用一个 spare 轴的 5 个灰值去换工程重新变脏，不值。

### 17.5 灰置参数的三种独立派生判据（2026-11-18 全 34 轴归档对照 + UI 交叉验证）

上一节把"未使用轴"当成灰置的唯一原因，**不完整**。对一次性副本全部 34 轴逐轴比对 `NexAxisUseAxis` / `NexAxisAxisType` / 各字段 `IsEnabled`，灰置实际上有**三条互相独立的派生链**，判据在 `.oem` 归档里就能读，不必去界面摸：

| 派生链 | 归档判据 | 被灰掉的范围 | 本工程样本 |
| --- | --- | --- | --- |
| A 未使用轴 | `NexAxisUseAxis = NexAxisNotUsingAxisNotChangable` | 轴类型 / 单位换算 / 最大速度 / 原点返回整组 / 输出设备1 全灰 | 轴26（唯一真正未使用的轴） |
| B 虚拟轴型 | `NexAxisAxisType` 含 `Virtual`（`NexAxisVirtualServoType` / `NexAxisVirtualEncoderType`） | 即便 `轴使用=使用的轴`，单位换算 / 最大速度 / 原点返回 / 输出设备1 仍灰；但 `轴使用` 与 `轴类型` 两行本身可编辑 | 轴0（用轴 + 虚拟伺服型） |
| C 原点方式派生 | `NexAxisHomingMode = OriginPreset`（零位置预设） | `NexAxisStartDirection`（原点返回开始方向）及其余原点信号/速度行灰 | 全部 34 轴（含所有已用实轴） |

关键修正与边界：

- **轴0 不能再用"未使用轴"解释**：它在工程里是 `NexAxisUsingAxis`，轴类型也是 `en=true`，但单位/速度/原点/输出设备全 `en=false`——这是**链 B 虚拟轴型**导致，不是链 A。此前 §17.4 说"轴0 两边都是 NotUsing"是另一对工程的状态，不可照搬到本工程。判读顺序应为：先看 `NexAxisUseAxis`，再看 `NexAxisAxisType`，最后看 `NexAxisHomingMode`。
- **`StartDirection` 全 34 轴 `en=false`，与用轴/轴型无关**：UI 侧交叉验证——八子页导出里，一个已用实轴的 `原点返回方法=零位置预设`，其 `原点返回开始方向` 为 `none+disabled` / `IsEnabled=False`，与归档一致。链 C 判定为 `PASS`（当前工程内一致）。
- **"改成别的原点方式就能激活 StartDirection" 标 `INCONCLUSIVE`**：本工程 34 轴的 `NexAxisHomingMode` **全是** `OriginPreset`，没有第二种取值做对照，无法证明反向派生；不要为验证它去改原点方式。
- **`NexAxisMceTypeSelect` / `NexAxisControlType` 也是灰的**：前者全 34 轴 `en=false`（本工程无对照值），后者枚举只有 `NexAxisWithoutControlLoop` 单项 ⇒ 属"无可选值"型灰置，同样不要试图绕开。
- **可绕开性结论**：三条链都**没有界面开关**；链 A/B 若强行改上游（`轴使用` 或 `轴类型`）会引入 `AXIS_REF` 全局量、任务分配或轴语义变更，链 C 需改原点方式，均有副作用且**未实测**；离线直接改归档灰字段与 UI 派生不一致（见 [offline-surgery.md](offline-surgery.md)），**NON_TRANSFERABLE / 未验证**。正确做法是如实报告差异，不为消除灰值改动工程。
- 判据可离线复现：`ss_axisparams.table_of(<archive>)` 取每轴行字典，读 `NexAxisUseAxis`/`NexAxisAxisType` 的当前值与各字段 `IsEnabled` 分组即可（按轴行字典分组即可），全程不碰 UI。


## 18. EtherCAT 拓扑树 / 工具箱 / ESI库（2026-11-08 实测，右击插入路线）

### 18.1 树与行

| 对象 | UIA 形状 |
| --- | --- |
| 拓扑树 | `TreeControl AutomationId='TopologyView'`（`ClassName=TreeView`），外包 `Custom cls=TopologyEditor` |
| 主设备行 | `TreeItemControl`，**`Name` = `…MasterDeviceTreeNode`**，行内无 `editBox` |
| 从站行 | `TreeItemControl`，**`Name` = `…SlaveDeviceTreeNode`**，行内有 `EditControl AutomationId='editBox'`（节点号，`ValuePattern` 可读写） |
| 端口行 | `TreeItemControl`，**`Name` = `…PortTreeNode`**，行文字 `X2 | Redundancy` / `Internal Port | Redundancy`；挂在从站行**下面**（是子节点） |
| NX 耦合器 | 也是 `SlaveDeviceTreeNode`（`NX-ECC203` 等），没有端口子行 |
| 行矩形 | **不是行高**：`(275, 186, 902, 1950)` = 本行 + 全部展开子孙的总高。点标题带 `(x+min(300,max(60,w//3)), y+18)` |
| 行文字 | `find_by_type(row,'TextControl')` 会带出所有子孙行的字 ⇒ 必须过滤掉中心点落在子 `TreeItem` 矩形内的 Text（`row_texts()`） |
| 展开 | `ExpandCollapsePattern.Expand()` 直接可用（不必再"选中行 + VK_RIGHT"）；`ExpandCollapseState`: 0=collapsed / 1=expanded / 2=partial / 3=leaf |
| 视口 | 树高 1950 px、视口约 700 px，**只有视口附近的行会实化** ⇒ 从根 `GetChildren()` 会缺行（pitfalls §73） |

`ss_ecat_build.py` 的遍历判据（`kind_of`）就用 `Name` 里的 VM 类名 + 行首文字，比"有没有 editBox"稳。

### 18.2 右下停靠：工具箱 vs 查找和替换

- 两个**同一组页签**，但类型是 **`PaneControl`**，不是 `TabItemControl`：
  `工具箱 (1672,1030,57,25)`、`查找和替换 (1729,1029,250,27)`。
- 「查找和替换」在前时 `SearchTextBox` / `ItemListBox` **整个从 UIA 消失** ⇒ 脚本要先点回「工具箱」（`ensure_toolbox()`）。

### 18.3 工具箱

| 控件 | id / 形状 |
| --- | --- |
| 关键字框 | `EditControl AutomationId='SearchTextBox'`（**读不回值**，判成功只看结果） |
| 结果列表 | `ListControl AutomationId='ItemListBox'` → `ListItemControl`（38 px/行，文字 = 型号 + 描述 + `Rev:x`） |
| 显示所有版本 | `CheckBoxControl Name='显示所有版本'`（`TogglePattern`）；关 = 只列推荐版本 |
| 插入菜单 | 结果行右键 → 唯一一项 **`插入(I)`**（`MenuItemControl`，`InvokePattern` 可用） |

搜索只匹配**设备名**：`GX-JC06` 命中 4 条（Main/Sub × GX-JC06/GX-JC06-H，Rev:1.1）；
`GX-JC06(IN,X2,X3) Main device` 命中 0 条。`NX-ECC203` → Rev:1.7；`SV660` → `InoSV660N Rev:0x00010000`；
`CTEU` → `CTEU-EtherCAT Modular Rev:0x00000008`；`R88D-KN04H-ECT` → Rev:2.1（另有 `-L` Rev:1.1）。

### 18.4 右侧参数表

`Custom cls=NodeOutlineParameter` → `Custom cls=ParameterSettingTable` → `ListControl id='List'`。
行 = `ListItemControl`，第一段 Text 是字段名。

| 字段 | 值在哪 |
| --- | --- |
| `从设备数量` | 行内最后的 Text（只读）；选中主设备才刷新 |
| `设备名称` | 行内 `TextControl AutomationId='text'`（**没有 ValuePattern**）⇒ 点单元格 → Ctrl+A → 粘贴 → Enter |
| `节点号` | 不在这里，在**树行**的 `editBox` 上 |

### 18.5 ESI库 与消息框

- `显示ESI库`（主设备右键）→ 独立顶层窗 `ESI库`：`Custom cls='ProfileLibraryView'` + `TreeControl id='EsiProfileTreeView'`；
  按钮 `installFileButton` / `installFolderButton` / `unInstallButton` / `cancelButton`。
- 安装文件对话框：Win32 `#32770`，文件名 `EditControl id='1148'`，打开 `ButtonControl id='1'`。
- Sysmac 自己的消息框：顶层窗 `Name='Sysmac Studio'`、**`AutomationId='MessageBoxView'`**（`ClassName` 只是 `Window`），
  正文是 `ScrollViewer` 里的只读 Edit，按钮是 `ListBoxItem` 包着的 `ButtonControl`。

## 19. 配置对话框与相邻配置页（2026-11-17 只读实测）

> 来源：一次性工程副本；全程只“打开 → dump UIA → 取消/关闭”，**没有**点确定/应用、没有在线/传送/下载/真实轴运动。工程树路径下标随工程变化，按**节点标签**定位；下表只写可移植的控件形状与稳定锚点。

### 19.1 菜单触发的配置对话框 / 文档

| 菜单入口 | 实际形态 | 稳定 UIA 锚点 / 结构 | 只读结论 |
| --- | --- | --- | --- |
| `工具(T) > 选项(O)...` | 顶层窗 `选项` | 左 `ListControl id='SectionList'`（20 项），右 `Pane cls='ScrollViewer'` 中逐页 `Custom cls='<…>SettingsSectionView'`，底部 `ImportButton` / `ExportButton` / `OkButton` / `CancelButton` | 逐页切换用 `SelectionItemPattern.Select()`，不要点坐标；**只点 `CancelButton`**，绝不 OK/导入/导出 |
| `工程(P) > 内存使用(M)` | 主窗口内停靠文档，不是独立弹窗 | `Pane cls='DocumentWindow' Name='内存使用情况'` → `Custom cls='NexMemoryUsageView'` → `TabItem` `总数` / `详细`；总数页 8 组 `Custom cls='BarGraphControl'` | 必须 dump 主窗口树才看得到；页签自身有 `closeButton` |
| `工具(T) > 事件日志查看器...(V)` / `EtherCAT诊断/统计信息查看器...(V)` | Win32 打开文件对话框（`#32770`，标题为“打开文件”或“打开”） | 标准文件名框 + 打开/取消按钮 | `...` **不等于**直接进入查看器；本次只读取消，未选择文件 |
| `工具(T) > 自定义快捷键...(S)` | 顶层窗 `快捷键自定义` | `设置目标(T)` ComboBox、命令树 `TreeControl cls='TreeListView'`（主菜单 10 类 + 编辑窗口等）、`Edit id='KeyAssignedTextBox'`、`List id='AssignedCommandListBox'`、`删除快捷键(R)` / `恢复快捷键(O)`（选中项前灰）、`导入` / `导出` / `OK` / `取消` | 只读可完整枚举命令树；不要分配/删除快捷键 |
| `帮助(H) > 关于Sysmac Studio(A)` | 顶层窗 `关于 Sysmac Studio` | 版本文本（实测 `模块版本 1.68.0.64010` / `标准版 Ver.1.68`）、`List id='InstalledName'`、`确定` | 版本/许可信息可直接读；`确定` 或标题栏关闭均可 |
| `控制器(C) > 通信设置(C)...` | 顶层窗 `通信设置` | 4 组 `GroupControl`：`连接类型`（radio id `usbDirectRadioButton` / `etnDirectRadioButton` / `usbRemoteRadioButton` / `etnRemoteRadioButton` / `selectRadioButton` + checkbox id `useUsbDirect` / `useEtnDirect` / `useUsbRemote` / `useEtnRemote`）、`远程IP地址`、`选项`、`响应监测时间`；底部 `ButtonOk` | radio/checkbox id 稳定；测试按钮按连接类型灰/亮；只读取消 |
| `视图(V) > 变量管理器(V)...` | 顶层窗 `变量管理器` | 独立大窗口，完整 UIA 树可直接 dump | 与工程树 `数据>全局变量` 页不是同一个窗口 |
| `工程(P) > 库(L) > 显示索引(S)` | 顶层窗 `库索引` | `Button id='CreateLibraryReference'`、两个 `CheckBox`（“将引用库包含在工程中。”/“如果工程中的库ID与引用库文件ID不匹配，则通知。”）、`确定` | 点确定会改引用库；只读时只取结构 |
| `控制器(C) > 安全性(E) > 用户程序执行用ID(I)...` | 顶层窗 `用户程序执行ID(程序)` | 两个 `PasswordBox`（ID + 确认）、长段一次性警告文本、`确定`（空框时灰）/`取消` | 警告原文强调**只能设置一次**且需备份工程；只读取消 |
| `视图(V) > 管理窗口布局模板...(L)` | 顶层窗 `窗口布局模板管理` | `List id='WindowLayoutTemplatesListView'` + `UpdateButton` / `ApplyButton` / `CreateButton` / `RenameButton` / `RaiseButton` / `LowerButton` / `DeleteButton` / `CloseButton` | 未选中模板时多数按钮灰；只读关闭 |
| `工具(T) > EtherNet/IP连接设置(N)` / `帮助(H) > 正在升级信息(U)` | 离线态无新顶层窗口 | — | 记为“本次上下文未打开新窗口”，不要推断功能不存在 |

### 19.2 `选项(O)...` 的 20 个设置页

左栏顺序（与 `SectionList` 一致）：`颜色主题` `启动` `工程设置` `窗口` `梯形图编辑器` `ST编辑器` `HMI` `HMI 代码编辑器` `HMI页面编辑器` `程序检查/编译` `变量` `变量和数据类型的注释` `参数编辑器` `同步` `安全` `自动回放` `V+ 程序` `V+变量` `V+ 保存配置` `3D可视化器`。

常见页内锚点：`颜色主题` = `ColourThemeSettingsSectionView`（radio 灰色(默认)/白色）；`梯形图编辑器` = 4 个位置 radio + `CheckBoxAlignRightBusBar` / `RungMinimumWidthSlider` / `FitToEditPaneWidth` / `GuideDisplayCheckBox`；`ST编辑器` = `EnableAutoCompleteCheckBox` / `FontFamilyComboBox` / `EnableArrayIndexMonitorCheckBox` / `Default`；`程序检查/编译` = `doubleCoilCheckBox` / `duplicatedInstanceCheckBox` / `internalVariableReadWriteCheckBox` + `无/警告/错误` radio + `BackgroundBuildCheckBox`；`安全` = 内部/全局变量选择、曝露变量、安全单元恢复文件传送等 checkbox；`3D可视化器` = 多组 `低/中/高` radio。各页还有 `Default` 重置按钮与全局 `ImportButton/ExportButton/OkButton/CancelButton`，**只读探索一律 Cancel**。

### 19.3 工程树相邻配置页（按标签，不按数字路径）

| 节点标签 | 页面根 / 关键结构 | 结论 |
| --- | --- | --- |
| `内置EtherNet/IP端口设置` | `Custom cls='ConfigurationView'` → 左 `SectionView` 9 节；`IconView id`依次为 `tcp_ip` `link` `ftp` `ntp` `snmp` `snmp_trap` `fins` `tcpudp_msg_svs_setting_L_normal` `cip`；TCP/IP 正文有 13 个 `Expander`（IP地址-端口1/2、本地主机名、内部网络、默认网关、DNS、主机名-IP地址、KeepAlive、IP路由表、包转发、数据包过滤器等） | 可开；节 id 是稳定锚点，切节点 52×52 `Button` 的中心 |
| `EtherNet/IP端口设置[单元…]`（CPU/扩展机架下的单元） | 同为 `ConfigurationView`，但只有 5 节：`tcp_ip` `link` `snmp` `snmp_trap` `cip`；TCP/IP 子项文案与内置端口略有差异（如“保持激活”/“IP路由器表”/“端口转发”） | 可开；不要假设与内置端口的节集合相同 |
| `事件设置` | `Custom cls='EventTableView'` → `CheckBox '编辑多个表'`、语言 ComboBox、注释 Edit、`DataGrid id='DataGridView'`（列：事件代码/事件名称/事件等级/组/详细）、`AddButton` / `DeleteButton` / `SystemAlertMessageTextBox` | 可开；整表 UIA 可读 |
| `CPU机架: NX总线` | `Custom id='mainEditorView' cls='MainEditorView'` → `Custom id='editor' cls='NXBusEditor'` → `List`（`NXBusMaster` / `NXBusUnit` / `NXBusEndCover` 三类 `ListBoxItem`）+ `GridSplitter` + `UnitSettingsControl > ParameterSettingTable > List id='list'` | 与 X 总线的 `MainEditorView` 同构，只是左侧编辑器类名不同 |
| 从站节点下的 `参数` | `Custom cls='ParameterEditorControl'`；顶部按钮 `导入` / `导出` / `复制设置` / `Config操作`（本次灰）；`ComboTreeView` 当前显示“所有参数”；`DataGrid id='ParameterGrid' cls='DataGridControl'` 列含 序号 / OD / 描述 / 值 / 驱动值 / 默认 | 可开；离线从站也能看参数表，但导入/导出/Config 按钮不要点 |
| `DB连接设置` / `轴组设置` / `Cam数据设置` / `数据跟踪设置` / 从站下的 `数据跟踪设置` | `ss_uimap.py open` 取证：`tree focus=True`、`row hit by click=True/True`、`rows` 不变、`new windows=[]` | **没有对应实体就没有文档**，不是定位失败；见 §16.6 同类判据 |
| 某些深层子单元行 | `open` 报 `no reachable row`（祖先展开失败） | 记为**该行不可达 / INCONCLUSIVE**，不要靠反复双击碰运气；换工程或先手工展开祖先再测 |

### 19.4 只读导出配方

1. 菜单对话框：先用 `ss_uimap.py menus` 拿真实 `Name`（含访问键后缀），再用精确名点击；新窗口出现后 dump 其 HWND 的 UIA 树。
2. `选项` 多页：找到 `SectionList`，对每个 `ListItemControl` 用 `SelectionItemPattern.Select()`，每次重 dump 主窗口/对话框；跳过 `SectionList` 子树避免重复。
3. 停靠文档：不要只看 `ss.py popups`；没有顶层弹窗时直接 dump 主窗口树，找 `Pane cls='DocumentWindow'`。
4. 收尾：按 `CancelButton` / `CloseButton` / 页内 `closeButton` 关闭；最后 `ss_uimap.py close <pid> <out> --all` 清掉遗留页签；实例用 `TerminateProcess` 不保存关闭并核对副本哈希。
5. 任何 `确定` / `应用` / `导入` / `导出` / 在线 / 传送 / 真实轴动作都不属于只读探索，需单独授权。

## 20. 轴页八子页全字段 ↔ 归档字段映射（2026-11-17 只读实测）

采集法：先用 `ss_axis.py read <pid> <out> <tree.path>` 展开全部 `ExpandCollapse`（包括 `单位换算设置` 的 `subsectionExpander` 与 `轴基本设置` 的第二层 `详细设置`），逐页导出 `label / ControlType / 当前值 / group / enabled / 矩形 / AutomationId`；再用离线 `ss_axisparams.py --all --csv` 读同一轴的 `<AxisSettingEntity> .xml` 叶节点，按当前值、选项枚举、顺序和 Group 交叉配对。**结论仅限“界面可见行 ↔ 归档叶节点”的映射**，不把归档里没有显示成独立行的单位/PDO 内部字段说成界面项。

实测规模：8 个子页共 **92 个实化 UIA 字段行**（`basic_setting` 23、`axes_scale` 13、`axes_dynamics` 16、`axes_io` 9、`axes_limit` 5、`back_original_point` 16、`count_mode_set` 5、`servo` 5）；同一轴归档有 290 个叶节点。多出来的主要是 `*Value2` 单位字段、`PDO0..PDO27` 六元组、版本/历史标记，以及不显示的派生字段。

### 20.1 轴基本设置 `basic_setting`

| UI 标签 | 控件 | `.oem` 字段 | 备注 |
| --- | --- | --- | --- |
| 轴号 | Edit | `NexAxisAxisNumber` | 标量 |
| 运动控制 | ComboBox | `NexAxisMceTypeSelect` | 枚举；本次 disabled |
| 轴使用 | ComboBox | `NexAxisUseAxis` | 枚举 |
| 轴类型 | ComboBox | `NexAxisAxisType` | 枚举 |
| 反馈控制 | ComboBox | `NexAxisControlType` | 枚举 |
| 输入设备1 | ComboBox | `NexAxisInputDevice1` | 设备引用 |
| 通道 | ComboBox | `NexAxisInputDevice1Channel` | 随输入设备1 灰置 |
| 输入设备2 | ComboBox | `NexAxisInputDevice2` | 本次 disabled |
| 通道#2 | ComboBox | `NexAxisInputDevice2Channel` | 同上 |
| 输入设备3 | ComboBox | `NexAxisInputDevice3` | 本次 disabled |
| 通道#3 | ComboBox | `NexAxisInputDevice3Channel` | 同上 |
| 输出设备1 | ComboBox | `NexAxisOutputDevice1` | 归档存实体 GUID，界面显示解析后的节点/型号 |
| 通道#4 | ComboBox | `NexAxisOutputDevice1Channel` | 归档 `IsEnabled=False` |
| 输出设备2 | ComboBox | `NexAxisOutputDevice2` | 设备引用 |
| 通道#5 | ComboBox | `NexAxisOutputDevice2Channel` | 灰置 |
| 输出设备3 | ComboBox | `NexAxisOutputDevice3` | 设备引用 |
| 通道#6 | ComboBox | `NexAxisOutputDevice3Channel` | 灰置 |
| 输出(控制器到设备) | ComboBox `id=comboDevice` | `NexAxisPDOMappingTable` + `PDO<n>PDOPathName/FunctionNumber/...` | DataGrid 第 2 列，不是标量 |
| 输出(控制器到设备)#2 | ComboBox `id=comboProcessData` | `PDO<n>PDOPathName` / `PDO<n>FunctionNumber` | DataGrid 第 3 列 |
| 输入(设备到控制器) | ComboBox `id=comboDevice` | 同上 PDO 家族 | DataGrid 第 2 列 |
| 输入(设备到控制器)#2 | ComboBox `id=comboProcessData` | 同上 PDO 家族 | DataGrid 第 3 列 |
| 数字输入 | ComboBox `id=comboDevice` | 同上 PDO 家族 | DataGrid 第 2 列 |
| 数字输入#2 | ComboBox `id=comboProcessData` | 同上 PDO 家族 | DataGrid 第 3 列 |

`详细设置` 展开后 `DataGrid id='list'` 的列头是 **功能名称 / 设备 / 过程数据**。展开态下只有 3 行有实化矩形，其余为 `IsOffscreen=True` 的 `DataItem`；**本映射不宣称已逐行枚举全部 PDO 行**，逐项集合另见 §17.6。

### 20.2 单位换算设置 `axes_scale`

| UI 标签 | 控件 | `.oem` 字段 | 备注 |
| --- | --- | --- | --- |
| 脉冲 / 毫米 / 微米 / 纳米 / 度 / 英寸 | RadioButton | `NexAxisUnitsConversion=EnumElement1..6` | 顺序对应，实测选“毫米”= `EnumElement2` |
| 电机转一周的指令脉冲数 | Edit | `NexAxisUnitsNumerator` | 伴随 `NexAxisUnitsNumeratorValue2` |
| 不使用变速箱 | RadioButton | `NexAxisReducerUse=EnumElement1` | 关闭齿轮箱 |
| 电机转一周的工作行程 | Edit | `NexAxisUnitsDenominator` | 伴随 `NexAxisUnitsDenominatorValue2` |
| 使用变速箱 | RadioButton | `NexAxisReducerUse=EnumElement2` | 打开齿轮箱；会改变下面三行的 enabled |
| 工作每转的工作行程距离 | Edit | `NexAxisTravelDistancePerWorkRotation` | 本次因未用齿轮箱而灰置 |
| 工作齿轮比(减速比的分子) | Edit | `NexAxisWorkGearRatio` | 同上 |
| 工作齿轮比(减速比的分母) | Edit | `NexAxisMotorGearRatio` | 同上 |

`NexAxisPulseDenominator` / `NexAxisPulseDenominatorValue2` 在归档里有值但不对应独立可见行，属于内部换算伴随字段，不能拿 UIA 行数去反推归档参数数。

### 20.3 操作设置 `axes_dynamics`

| UI 标签 | `.oem` 字段 |
| --- | --- |
| 最大速度 | `NexAxisMaxVelocity` |
| 速度警告值 | `NexAxisWarningVelocityLimit` |
| 启动速度 | `NexAxisStartVelocity` |
| 最大点进速度 | `NexAxisMaxJogVelocity` |
| 最大加速度 | `NexAxisMaxAcceleration` |
| 加速度警告值 | `NexAxisWarningAccelerationLimit` |
| 最大减速度 | `NexAxisMaxDeceleration` |
| 减速度警告值 | `NexAxisWarningDecelerationLimit` |
| 加速度/减速度超出 | `NexAxisAccDecOveractive` |
| 换向操作选择 | `NexAxisReverseMovementMode` |
| 正扭矩警告值 | `NexAxisWarningTorqueLimitPositive` |
| 负扭矩警告值 | `NexAxisWarningTorqueLimitNegative` |
| 定位范围 | `NexAxisInPositionBand` |
| 定位检查时间 | `NexAxisInPositionCheckTime` |
| 实际速度滤波器的时间常数 | `NexAxisActualVelocityFilterTime` |
| 零位置范围 | `NexAxisZeroPositionBand` |

上表所有数值项都有同名 `...Value2` 单位伴随字段；界面显示的是数值，单位由当前单位制决定。

### 20.4 其它操作设置 `axes_io`

| UI 标签 | `.oem` 字段 |
| --- | --- |
| 立即停止输入停止方法 | `NexAxisEmergencyStopMode` |
| 限位输入停止方法 | `NexAxisLimitInputStopMode` |
| 驱动器错误重置监测时间 | `NexAxisDriverAlarmResetTime` |
| 正扭矩限位最大值 | `NexAxisMaxPositiveTorqueLimit` |
| 负扭矩限位最大值 | `NexAxisMaxNegativeTorqueLimit` |
| 立即停止输入逻辑反转 | `NexAxisImmediateStopInputLogicInversion` |
| 正限位输入逻辑反转 | `NexAxisPositiveLimitInputLogicInversion` |
| 负限位输入逻辑反转 | `NexAxisNegativeLimitInputLogicInversion` |
| 首页接近输入逻辑反转 | `NexAxisHomeProximityInputLogicInversion`（标签与字段名措辞不同，按当前值/选项/顺序配对） |

### 20.5 限位设置 `axes_limit`

| UI 标签 | `.oem` 字段 | 备注 |
| --- | --- | --- |
| 软件的限位 | `NexAxisSoftwareLimitMode` | 枚举；决定下面两行 enabled |
| 正软件限位 | `NexAxisPositiveSoftwareLimit` | 本次模式为“无效”故灰置 |
| 负软件限位 | `NexAxisNegativeSoftwareLimit` | 同上 |
| 位置偏移超出值 | `NexAxisFollowingErrorLimit` | group=`位置偏移` |
| 位置偏移警告值 | `NexAxisFollowingErrorAlarmLimit` | group=`位置偏移` |

### 20.6 原点返回设置 `back_original_point`

| UI 标签 | `.oem` 字段 |
| --- | --- |
| 原点返回方法 | `NexAxisHomingMode` |
| 原点输入信号 | `NexAxisOriginInputMode` |
| 原点返回开始方向 | `NexAxisStartDirection` |
| 正限位输入时操作选项 | `NexAxisOperationPositiveLimitInput` |
| 原点输入检测方向 | `NexAxisOriginInputDetectionDirection` |
| 负限位输入时操作选项 | `NexAxisOperationNegativeLimitInput` |
| 原点返回速度 | `NexAxisHomingVelocity` |
| 原点返回接近速度 | `NexAxisHomingApproachVelocity` |
| 原点返回加速度 | `NexAxisHomingAcceleration` |
| 原点返回减速度 | `NexAxisHomingDeceleration` |
| 原点返回加加速度 | `NexAxisHomingJerk` |
| 原点输入掩码距离 | `NexAxisOriginInputMaskAmount` |
| 原点偏移量 | `NexAxisOriginPositionOffset` |
| 原点返回持续时间 | `NexAxisPushTime`（标签/键名不同） |
| 原点返回补偿值 | `NexAxisOriginCompensationValue` |
| 原点返回补偿速度 | `NexAxisCompensationVelocity` |

`NexAxisHomingMode=OriginPreset`（零位置预设）时，除“原点偏移量”外上述多数行 `IsEnabled=False`；这与 §17.4 的灰置来源一致，不要因为读不到值就判断映射缺失。

### 20.7 位置计数设置 `count_mode_set`

| UI 标签 | `.oem` 字段 |
| --- | --- |
| 线性模式 | `NexAxisCountMode=EnumElement1` |
| 循环模式 | `NexAxisCountMode=EnumElement2` |
| 模最大位置设置值 | `NexAxisModuloMAXPosition` |
| 模最小位置设置值 | `NexAxisModuloMINPosition` |
| 编码器类型 | `NexAxisEncoderTypes` |

### 20.8 伺服驱动设置 `servo`

| UI 标签 | `.oem` 字段 |
| --- | --- |
| 模最大位置设置值 | `NexAxisServoDriverModuloMAXPosition` |
| 模最小位置设置值 | `NexAxisServoDriverModuloMINPosition` |
| PDS状态控制方法 | `PowerDriveSystemStateControlMethod` |
| 检测 | `MainCircuitPowerObserveEnable=EnumElement1` |
| 不检测 | `MainCircuitPowerObserveEnable=EnumElement2` |

### 20.9 只读判定边界

- 本表是**字段映射**，不是写入验证；`enabled` 是界面当次状态，切换上游枚举（单位、齿轮箱、软件限位、原点返回方法、计数模式）会改变下游行的可编辑性。
- 归档里有而 UI 没有独立行的典型家族：`*Value2`、`NexAxisPdoAiosmapVersion`、`CorrectedFunctionIsIndispensable`、`PDO0..PDO27{PathName,FunctionNumber,ODBitLocation,MappedDevice,MappedChannel,Indispensable}`。
- `ss_axis.py read` 的轴号防护用 `tree.path` 末段与页面“轴号”文本比对；**树序号不等于轴号**的工程会在 `0.4.0.N` 打开轴 N 时被防护中止，应选末段与轴号一致的行，或先由 `treelabels` 读出真实轴号，不要删掉防护硬读。

## 21. 从站「参数」页导航图：按节点类型配什么、在哪配（2026-11-18 只读）

> 用户口径：**节点参数随所配节点而变，不需要逐项穷举**；目标是“哪类节点大致配什么参数、大致在哪配”。所以本节只记导航形状与参数**大类**，不列具体 Pnxxx 项（项集合另见 §17.6 的 ESI 字典）。

### 21.1 在哪打开

- 入口：工程树 `配置和设置(EtherCAT) > 节点N : <型号> (<轴名>)` 下的子节点 **`参数`**，树路径形如 `0.0.25.0`（实测 `ss_uimap.py open <pid> <out> <节点树路径>` 可打开）。
- 打开后的文档是一个停靠 Pane（`AutomationId='ParameterEditorControl'`），顶部 4 个按钮：`导入` / `导出` / `复制设置` / **`Config操作`（disabled）**；下面是 `ComboBoxTreeView > Button '所有参数'` 过滤器 + `DataGrid id='ParameterGrid'`。
- `ParameterGrid` 列：`序号 / OD / 描述 / 值 / 驱动值 / 默认 / 范围 / 单元 / 数据属性`（+ 值状态图标列）。**值单元格是 `ParameterEditorValueEditor > ComboBox`**（枚举型参数），`数据属性` 列带 tooltip 说明何时生效（如"C: 控制电源重置后或 EtherCAT 配置命令后更新"）。网格下方有参数说明文本框 + `参数一览 / 说明 / 程序 / 位置` 之类页签。
- **只读边界**：`导入`/`导出`/`复制设置`/`Config操作` 都不要点（会改从站参数或触发写入）；值单元格是 ComboBox，读它的当前文本即可，不要展开选中。

### 21.2 哪类节点配什么（按 ESI 对象字典大类，本工程 5 类从站）

`.smc2` 内 EtherCAT 配置 `.dat` 的每个 `<Dictionary>` 就是该型号的**可配参数全集**（离线可按各 `<Dictionary>` 的 OD 区间统计）。按 OD 区间看参数大类：

| 节点类型（本工程实例） | 字典规模 | 参数大类（按 OD 区间） | 配置位置 |
| --- | --- | --- | --- |
| 伺服 Panasonic MEDLT83BM / MBDLT25BM / MCDLT35BM | 637 对象 | `1000h-1FFF` 通信 profile（设备类型/身份/诊断历史/参数存储）；`3000h-3FFF` **厂商参数区 411 项**（控制模式、实时自动增益、机械刚性惯量比等 Pn 参数）；`4000h-5FFF` 厂商扩展 122 项；`6000h-6FFF` PDO/设备对象 83 项（错误码/控制字/状态字/quick-stop 等） | 该从站 `参数` 页 `ParameterGrid`，过滤器“所有参数” |
| 伺服 InoSV660N | 36 对象 | `1000h-1FFF` 通信 22 项；`6000h-6FFF` 设备/PDO 14 项（跟随误差窗口、位置窗口、原点偏移、极性、profile 加减速等）；**无 3000h 厂商大参数区** | 同上；参数远比 Panasonic 少 |
| 伺服 R88D-KN04H-ECT（A/B_YT_Y） | 无独立字典（本机已安装 ESI） | UI 实测 `Pn000…` 系列（旋转方向切换、控制模式、实时自调整等），OD 显示为 `3000.00` 一类 | 同上；`0.0.25.0` / `0.0.40.0` 已实测可开 |
| 远程 I/O / 耦合器（GX-JC06、NX-ECC203 等） | 无轴参数字典 | 这类节点主要是 **I/O 映射与模块设置**，不是 Pn 参数；本工程未在 `参数` 页逐项展开 | 通常在节点自身的设置页 / I/O 映射页，不是 Pn 参数网格 |
| Festo CTEU-EtherCAT 阀岛 | 27 对象 | `1000h-1FFF` 通信 14 项；`7000h+` 厂商/诊断 13 项 | 阀岛专用配置，非轴参数 |

- **厂商 / 型号决定参数粒度（用户 2026-11-18 21:05 补充）**：不同厂商的节点配置进去后，能改的参数本就不一样；**同为伺服驱动器，若配置的是 OMRON 自家节点，通常能配置更多详细参数**（本工程 R88D-KN04H-ECT 的 `参数` 页 UI 已实测到 `Pn000…` 系列）。第三方伺服按各自 ESI 字典决定粒度：Panasonic 三型号有 411 项 `3000h` 厂商参数，InoSV660N 仅 36 项通信 + 设备/PDO、无厂商大参数区。**不要跨厂商套用某一家的 Pn 列表。** 这条是用户实战经验补充；本轮未为验证"OMRON 一定比所有第三方更详细"再穷举跨型号 UI，详细程度按经验规则使用。
- **可推广结论**：只有**伺服驱动器**从站的 `参数` 页是 Pnxxx 大参数网格；I/O / 耦合器 / 阀岛配的是各自模块设置，不要套用 Pn 参数模型。同为伺服时，**参数大类与粒度由「厂商 + 型号 + ESI 字典」共同决定**（Panasonic 三型号同集 411 项厂商参数；Ino 只有 36 项通信+设备对象；OMRON 自家伺服按用户经验更细），所以"配什么"先看厂商与型号，再看 ESI 字典，不能只看"是不是伺服"。
- **未覆盖 / INCONCLUSIVE**：本工程只实测打开 R88D 的 `参数` 页（本轮），其它从站型号的 `参数` 页只从归档字典推大类，未在 UI 逐页打开；工程树里除 R88D 两节点外其余节点的 `参数` 子节点未展开（tree 只实化展开态），不虚构全覆盖。逐项参数值因节点配置而异，不在本导航图范围。
- 复现：`ss_uimap.py open <pid> <out> <节点树路径>.0` 打开 `参数` 页；离线按 OD 区间统计各型号参数大类。

