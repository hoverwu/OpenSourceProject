# 工程树（多视图浏览器）操作

Sysmac 的工程树是 **WinForms 托管 TreeView**（类 `WindowsForms10.SysTreeView32.app.0.*`），被塞在 WPF 的 `WindowsFormsHost` 里。它同时具备两套"半残"的接口：

| 接口 | 能做什么 | 不能做什么 |
| --- | --- | --- |
| UIA | 拿到**顶层节点**（每个根一个 `Tree` 元素，带精确矩形）与整个 Tree 的矩形 | 展开后的子行**完全不暴露**；读文字（Name 全空）；操作行（无 Invoke/Selection Pattern） |
| Win32 `TVM_*` 消息 | 结构（根/兄弟/子/父）、**任意深度**定位光标、根节点展开、节点总数、**读全部节点文字**（`TVM_GETITEMW` + 远端缓冲，见 §2） | 用错读文字的写法（A 变体 `0x110C` 或本地缓冲）**会让软件崩溃**；非根节点的展开（软件自己接管） |

所以工程树操作的现实做法是：**结构、名字、定位都用消息，动作走菜单**。定位不依赖 UIA 行矩形，也不依赖前台窗口——见 §3。节点身份（名字）与每个节点的右键菜单已经全量测绘，见 [tree-node-menus.md](tree-node-menus.md)。

## 1. 路径记法

`ss_tree.py` 的所有命令都接受**点分子索引路径**，从根开始：

```
0            配置和设置
1            编程
1.0          ↑ 的第 1 个子节点（实测：POUs）
1.1          ↑ 的第 2 个子节点（实测：数据）
1.2          ↑ 的第 3 个子节点（实测：任务）
1.0.0        POUs 下的程序
1.0.1        POUs 下的功能
1.0.2        POUs 下的功能块
```

> ⚠ **下标随工程内容变化**：`1.0` 一定是"第一个子节点"，不一定是 POUs。任何自动化开始前先 `ss_tree.py struct <pid> 3` 看根与一级子节点的数量，和预期结构对照后再深入——不要凭经验硬编码 `1.0.2`。
>
> 结构对不上时，先打开一个已知工程（或新建空工程）跑一遍 `struct` 建立基线，再回到目标工程比较。**节点文字现在能安全读出来了**（`ss_uimap.py treelabels`，见 §2），所以认节点优先用**名字**，`子节点数 + 顺序` 作为交叉校验——两者一起才是可靠指纹。

样例（一个含 POUs 的工程，`ss_tree.py struct <pid> 2`，省略句柄）：

```
[0] 配置和设置        kids=11   ← EtherCAT / CPU·扩展机架 / 控制器设置 / 运动控制设置 / CAM / 事件 / 任务 / 数据跟踪 / OPC UA / 主机连接
[0] 编程              kids=3
  [1] POUs            kids=3    ← 程序(9) / 功能(16) / 功能块(80)
  [1] 数据            kids=2
  [1] 任务            kids=1
```

（真实输出每行还有 `h=<句柄>`，行首 `[n]` 是**深度**不是序号；子节点数随工程内容变，这里只是形状参考。）

## 2. 原生消息与句柄截断

安全的只有这几条（`scripts/ss_tree.py` 已封装）：

| 消息 | 值 | 用途 |
| --- | --- | --- |
| `TVM_GETCOUNT` | 0x1105 | 节点总数（**含折叠的**，不是可见行数） |
| `TVM_GETNEXTITEM` | 0x110A | `TVGN_ROOT`(0) / `TVGN_NEXT`(1) / `TVGN_PARENT`(3) / `TVGN_CHILD`(4) / `TVGN_CARET`(9) |
| `TVM_SELECTITEM` | 0x110B | `TVGN_CARET`(9) 移动光标到**任意深度**节点（不需要前台） |
| `TVM_EXPAND` | 0x1102 | 展开/折叠（**只对根节点有效**，见 §3） |

**`TVM_GETITEM`（0x110C，ANSI 变体）绝对不要发**：它要求跨进程写 `TVITEMEXW` 结构 + 文本缓冲，实测会让 Sysmac **直接崩溃**。

> ✅ **但节点文字是可以安全读到的**（2026-10-31 实测，2026-11-06 起已进 Skill 脚本）：用
> `TVM_GETITEMW = 0x113E`，并且把 `TVITEMW` 与文本缓冲区都 **`VirtualAllocEx` 到目标进程里**、
> 用完 `ReadProcessMemory` 读回，软件一次没崩。现成命令：
> `ss_uimap.py treelabels <pid|auto> <out>`（`node_text()`，全树 `path  名字  kids=N`）。
> 已在 219 节点工程与 84 节点库工程（一次读满 84/84）上各跑通一遍。
> 结论修正：**文字可读，只是必须远端缓冲**；本地结构 + 跨进程写指针才是崩的原因。
>
> 两个实测细节：① Sysmac 存的标题**尾部带空格补齐**（`'EtherCAT        '`），显示前要 `rstrip`；
> ② `cChildren` 是 comctl32 **写回远端结构**的，必须把 `TVITEMW` 也 `ReadProcessMemory` 读回来才拿得到。

> ⚠ **HTREEITEM 会被截断**：`import uiautomation` 重声明了 `SendMessageW` 的原型（`LPARAM` 变 32 位），64 位句柄被砍成 0 或负数，表现为"子节点数恒为 1"。发消息前必须恢复原型：
>
> ```python
> import ctypes, ctypes.wintypes as _wt
> _u = ctypes.windll.user32
> _u.SendMessageW.restype = ctypes.c_ssize_t
> _u.SendMessageW.argtypes = [_wt.HWND, _wt.UINT, _wt.WPARAM, ctypes.c_void_p]
> ```
>
> `scripts/ss_tree.py` 在 `import uiautomation` 之后立即执行这段。

## 3. 定位与展开：实测边界

### 3.1 定位：消息移动光标（主路径）

```python
send(TVM_SELECTITEM, TVGN_CARET, 目标句柄)   # 移动光标
assert send(TVM_GETNEXTITEM, TVGN_CARET, 0) == 目标句柄   # 回读校验
```

实测结论：

- **不需要前台窗口、不需要真实鼠标/键盘**，锁屏、无输入桌面、甚至**主窗口最小化**时同样有效（2026-10-30 起；2026-11-06 `probe_select.py` 只用消息复测 4/4 通过，此前 0.4.2 的"消息到不了这棵树"是误判，见 [pitfalls.md §56](pitfalls.md)）。
- 它给的是**完整选中**：`TVGN_CARET` 回读一致 **且** 目标行真的带上 `TVIS_SELECTED`、上一行被取消选中——所以 `编辑>复制/粘贴/删除` 这类"选中 + 走菜单"的动作可以全程无鼠标。
- 深度无限制：`1.0.2.0`（功能块下的第 1 个 FB）定位成功，回读句柄一致。
- 目标节点**不需要可见**（折叠、甚至在视口外都行）——树的数据是全量物化的，`TVGN_CHILD`/`TVGN_NEXT` 能遍历折叠节点。
- 选中后软件会**滚动到该行并高亮**，所以定位同时也可以当作"截图前的可见化"手段。
- 消息**做不到**的只有"打开页面"：那一步要真实单击 + 真实 `{ENTER}` 或双击未选中的行（§3.4）。

`ss_tree.py goto <pid> <path>` = 逐级 `TVM_EXPAND` 祖先（尽力）→ `TVM_SELECTITEM` → 回读校验 → 打印子节点数。退出码非 0 表示路径不存在或光标没到位。

### 3.2 展开：`TVM_EXPAND` 只对根有效，深层要"光标 + 真实 `VK_RIGHT`"

| 层级 | `TVM_EXPAND` | 光标 + 真实 `VK_RIGHT` | 双击 |
| --- | --- | --- | --- |
| 根（`配置和设置`、`编程`） | ✅ 返回 1，树真的展开 | ✅ | — |
| 一级（`POUs`、`数据`、`任务`） | ❌ 返回 0，截图**完全不变** | ✅（2026-11-06 实测，`ss_uimap.py treectx` 的整批记录都靠它） | ⚠ 容器节点会进入就地重命名 |
| 二级及以下（`功能块`、`EtherCAT`…） | ❌ 同上 | ✅ | ⚠ `EtherCAT` 双击会**打开它的编辑器**而不是展开 |

`expand_node()`（`ss_uimap.py`）= 真实**单击**该行拿焦点 → `TVM_SELECTITEM(TVGN_CARET, h)` → 真键盘 `VK_RIGHT` → 回读 `TVM_GETITEMSTATE & TVIS_EXPANDED`（已经展开就直接返回，**绝不会折回去**）。实测 probe_expand5：深度 1~2 的 10 个折叠节点 9 个这样打开，且不需要知道三角在哪。返回值 `key` / `key(try N)` / `expanded` / `no row`，`treectx` 的 `ancestors: 0=key 1=expanded` 打的就是它。**前提是主窗口在前台、树能收到键盘输入**——锁屏就用不了，这是它相对 §3.1 的唯一劣势。

判定展开是否真的发生，优先看**子行能否被点到**（`row_hit` 让树自己回读句柄），其次才是截图像素；`TVM_EXPAND` 的返回值在根上可信，在深层恒为 0；`visible_rows()` 只暴露根节点，行数不会告诉你子节点展开了。

> 但**能不需要展开就别展开**：`count`/`copy`/`paste`/`treelabels` 全部只需要光标，不需要展开，也不需要前台。

### 3.3 已废弃方案：键盘下降
早期用"点行给焦点 → `{HOME}` → `{DOWN}` 逐级下移"，实测：

- 点行给焦点**不可靠**（`SetFocus` 被 WPF 抢回；`AttachThreadInput` 无效；要靠重试点击 + `{HOME}` 回读光标才知道成功）；
- `{DOWN}` 会钻进已展开节点的子节点，需要用 `TVGN_PARENT` 识别并 `{LEFT}` 折回，但 `{LEFT}` 在"已折叠节点"上会跳到父节点，语义不一致；
- 锁屏 / 无输入桌面时整条链路不可用。

结论：**不要用键盘在树里导航**，用 §3.1 的消息定位。注意这条废弃只针对"用 `{DOWN}`/`{LEFT}` 逐级**移动选中项**"；把光标用消息放好、再敲一次 `VK_RIGHT` **展开当前光标**是有效的（§3.2）。

### 3.4 按名字打开配置/数据页（实测形状）

工程树里的节点名可以直接读到（见 §2 的远端缓冲写法）。实测节点名与位置：

```
配置和设置 > EtherCAT
配置和设置 > 运动控制设置 > 轴设置 / 轴组设置
编程 > 数据 > 数据类型 / 全局变量
编程 > 任务 > PrimaryTask
```

打开一个页面的稳妥顺序（三条路按成本排）：

1. **已打开的文档选项卡**：文档选项卡是 `PaneControl`，`Name` 就是文档名（`数据类型` / `全局变量` / `EtherCAT` / `轴设置`），位置在窗口顶部（`top < 200`）。有就直接点它；
2. **树节点真实单击 + `{ENTER}`**（2026-10-31 起首选）：单击把键盘焦点交给树（跨进程 `SetFocus` 必须先 `AttachThreadInput`），再发真实回车。给树窗口直接 `SendMessage(WM_KEYDOWN, VK_RETURN)` 在焦点不在树上时**不会**触发打开；
3. **树节点双击**：`EtherCAT` 与配置页会打开编辑器。注意双击前要先单击一次，否则第一下只用来"从别的编辑器抢焦点"，第二下才可能落入就地重命名。

⚠ 双击在**容器节点**（`数据`、`POUs`、`任务`）上会把名字变成可编辑；只想展开就别双击。

⚠ **树行坐标必须走远端 `TVITEMRECT`**：`TVM_GETITEMRECT` 的 lParam 不是裸 `RECT`，而是 `struct { TVITEM item; RECT rc; }`，`item.mask=TVIF_HANDLE` 且 `item.hItem` 要**先写进远端缓冲区**。以前传一个空 RECT，结果恒为失败或返回上一行的坐标，导致双击/拖拽全落在别处（2026-10-31 修复）。

⚠ 如果之前有单元格在就地编辑（数据类型/全局变量表常见），第一次点树只会提交那个编辑框。打开页面前先按两次 `{ESC}`，并确认树获得了焦点。

## 4. 复制 / 粘贴 / 删除

**必须走 `编辑(E)` 菜单**，不能用 `Ctrl+C`：

- 实测 `Ctrl+C` 是**空操作**（什么都不发生）。
- `复制(C)` / `粘贴(P)` / `删除(D)` 三项可用，但**"点菜单项"和"目标节点已选中"必须在同一个进程里完成**——弹出菜单是独立 HWND，跨进程调用时它已经关了。

标准序列（`ss_tree.py copy/paste/del` 已实现）：

1. `TVM_SELECTITEM(TVGN_CARET, 节点)` 选中（不需要前台）；
2. **先取前台**（点菜单必须有真实输入），UIA 点 `编辑(E)`；
3. 在新出现的弹窗 HWND 里按 Name 找 `复制(C)` 并 Invoke/Click；
4. 粘贴/删除后可能出现确认框，按 Name 找 `是(Y)` 并 Invoke。

**判定动作是否真的生效**只能用外部状态：

- 复制 → 剪贴板格式变化（`ss_clip.py list`）。实测单个 FB 深节点（`1.0.2.0`）= `Omron.SolutionEntityClipboardFormatter` / 10,376 B；
- 粘贴 → 树里子节点数 +1（`ss_tree.py count`）；
- 删除 → 子节点数 -1。

**不要**用"菜单项是 ENABLED"当成功判据（见 §6）。

## 5. 剪贴板格式

| 场景 | 格式名 | 格式 id（实测，可能随版本变） |
| --- | --- | --- |
| 单个实体 | `Omron.SolutionEntityClipboardFormatter` | 49713 |
| 多个实体 | `Omron.SolutionMultipleRootEntites` | 49726（105 个 POU ≈ 1.3 MB） |

这些是软件自定义的二进制格式，**只能原样落盘/回放，不要尝试解析**。`ss_clip.py dump/set` 可以复制整块数据到另一个实例再回放——实测软件接受回放的数据。

## 6. 多选复制（批量搬 POU 的主路径）

1. 右键 `POUs` → `选择并复制多个项目`（右键要真实 `WM_RBUTTONDOWN/UP`，UIA 的 `RightClick` 也可）；
2. 弹出 `MultiplePousCopyDialog`：WPF TreeView，每行一个 CheckBox，`AutomationId='TreeSelection_TreeItemCheckBox'`；
3. **勾 `POUs` 行等于全选**（子项随之全勾）；勾选后 `复制` 按钮才可用；
4. 目标工程右键 `POUs` → `粘贴多个项目`；
5. 命名冲突弹窗：`是`=覆盖 / `否`=保留两者（自动加 `复制1_` 前缀）/ `取消`。

> 该对话框里的树是 **WPF TreeView**（有 Name、有 CheckBox Pattern），和工程树完全不是一回事——可以放心用 UIA。

## 7. 搬不动的东西（实测结论，不要再重复试）

| 对象 | 现象 |
| --- | --- |
| `数据`、`任务`（容器本身） | `编辑>复制` 是 no-op，剪贴板不变。（"子节点展不开"是旧结论：`TVM_SELECTITEM` + 真实 `VK_RIGHT` 能把它们展开，见 §3.2；但**右键确实没有菜单**，见 [tree-node-menus.md §1](tree-node-menus.md)） |
| `配置和设置` 及其全部子节点（`EtherCAT` / `CPU·扩展机架` / `控制器设置` / `运动控制设置` / `任务设置` …） | `编辑>复制` 显示 **ENABLED**，点完**剪贴板内容完全不变** |
| 配置行的右键 | **有**上下文菜单，但里面**没有** `复制(C)`：叶子只有 `编辑(E)`（`EtherCAT` 另有 `驱动器设置表`、`OPC UA设置`/`DB连接` 只有 `显示操作日志`），能导入导出的只有 `轴设置`/`轴组设置`/`Cam数据设置` 三项（`添加`/`导入(I)`/`导出(E)`）。容器行（`控制器设置`、`运动控制设置`、`主机连接设置`）和两个根**完全没有菜单**。全表见 [tree-node-menus.md §2.1](tree-node-menus.md) |

**结论**：配置部分**无法通过界面**逐项跨工程搬运——现在有了机制级证据：**配置节点的右键菜单里根本没有"复制"这一项**，`编辑>复制` 那条路径又是假可用（剪贴板不变）。要把配置带到另一个工程，有两条路：

> 路线 A（整体）：`文件(F) > 导入(I)...` 读一个 `.smc2`，软件会**按该文件建一整个新工程**（配置、程序、功能块、HMI 全在里面），然后再 `另存为` 改工程名/作者。
>
> 路线 B（选择性，2026-10-30 起实测可行）：**在文件层面移植实体子树**——`.smc2` 是 zip，实体树在 `<GUID>.oem`，把目标子树整段搬过去并按实体 id 拷配套文件即可（EtherCAT、安全 CPU、数据类型页都验证过）。步骤、边界与复验清单见 [offline-surgery.md](offline-surgery.md)。界面搬不动 ≠ 不能重建。

实测补充（2026-10-30 整工程重建）：

- **设备 / EtherCAT / NX 总线 / 安全应用**都不在 POU 剪贴板语义里，靠逐个复制永远搬不到；重建后的工程编译会留下大量 `地址不合法。`（`X100`、`MC://_MC_AX[1]` 之类）。若只走界面，这是**必然结果**；用路线 B 补上组态后可归零（实测 385→0）。
- 具体到 EtherCAT，下面 5 条路**全部实测失败**，不要再试：

  | 路径 | 结果 |
  | --- | --- |
  | 源树 `EtherCAT` 节点 → 复制 → 目标树粘贴 | 剪贴板确实变成 `Omron.SolutionEntityClipboardFormatter`，粘贴**静默 no-op**，目标子节点数不变 |
  | 源树 `节点N`（单个从设备）→ 复制 → 粘贴 | 同上 |
  | 源 EtherCAT 画布 `Ctrl+A` + `Ctrl+C` → 目标画布 `Ctrl+V` | 无反应 |
  | 目标画布右键 `粘贴(P)` | **该项 disabled** |
  | EtherCAT 编辑器工具栏 / 主设备右键找导入导出 | 工具栏**没有任何 UIA 控件**；主设备右键只有 `获取从设备信息` / `显示 ESI 文件` / 5 个无名 `EcatExtendCommandInfo` |

- 空网络的 `TopologyView`（拓扑视图）**只在没有从设备的网络里出现**，所以已组态的网络拿不到它，无法"复制拓扑"。
- 判断差异有多大的快捷方法：源/新两边分别读主设备属性里的**从设备数量**（实测 48 vs 0），比逐个数节点快。
- **编辑保护的 POU**（某些程序/功能在源工程里被锁）：右键 `剪切` / `复制` / `带有副本复制` 全灰，剪贴板哈希不变 → 只能跳过并记录在案。
- 库工程里的 FB / 数据类型：用 `工程>库>显示索引` 挂 `.slr` 引用获得，不要逐个粘贴（见 [library-and-tasks.md](library-and-tasks.md)）。
- 逐项搬运后仍可能差几个实体：`任务`/`程序` 的空壳、`Group` 分组层级、以及被保护 POU 内部的 `DataType`/`Variables`。用 digest 的实体计数差异来交代，不要当成"没搬完"。
- **被引用库里的类型会和工程本地同名类型撞名**：若你重建出的 `.slr` 把 100 个 `st_*` 结构体平铺在一页，而工程自己也定义了同名的 100 个，编译会得到 `100 × 2` 条 `该名称已用于数据类型 st_X。` + `数据类型名称 st_X 已用作库…名称`。两个未验证的修法：给被引用库设命名空间（`ReferredLibrary/NameSpace`），或移除库引用后重编译对比。

详见 [project-files.md](project-files.md#2-导入整工程导入会先关闭当前工程)。

## 8. 显示名 ≠ 内部名

删除确认框显示的是**内部名**，可能与树上显示名不一致。实测：选中行显示 `复制1_Buzzer_Config`，确认框写 `Buzzer_Config`。

规则：**确认框里的名字和你要删的名字不完全一致时，一律按"否"**，改用路径/结构核对后再操作。

## 9. 常用命令

```bash
python <SKILL_DIR>/scripts/ss_tree.py struct <pid> 3     # 结构 + 子节点数
python <SKILL_DIR>/scripts/ss_tree.py goto   <pid> 1.0.2 # 光标定位（锁屏也可用，回读校验）
python <SKILL_DIR>/scripts/ss_tree.py select <pid> 1.0   # 只选中，不打印（goto 的简版）
python <SKILL_DIR>/scripts/ss_tree.py count  <pid> 1.0   # POUs 子节点数
python <SKILL_DIR>/scripts/ss_tree.py expand <pid> 1.0   # 只有根节点会真的展开（§3.2）
python <SKILL_DIR>/scripts/ss_tree.py copy   <pid> 1.0.2 # 复制功能块容器节点（实测无效，见 §7）
python <SKILL_DIR>/scripts/ss_tree.py copy   <pid> 1.0.2.0
python <SKILL_DIR>/scripts/ss_tree.py paste  <pid> 1.0 --yes

# 带节点名 / 菜单测绘（要提权 + 真实桌面，treectx 还要 --fit）
python <SKILL_DIR>/scripts/ss_uimap.py treelabels <pid|auto> out.txt   # 全树 path + 名字 + kids（§2，只读，安全）
python <SKILL_DIR>/scripts/ss_uimap.py tree       <pid|auto> out.txt   # 只有结构 + 展开态 + caret
python <SKILL_DIR>/scripts/ss_uimap.py treectx  <pid|auto> out.txt --fit 0.0 1.0.2.0  # 右键菜单逐节点记录（结果见 tree-node-menus.md）
python <SKILL_DIR>/scripts/ss_uimap.py treerows <pid|auto> out.txt --max 200         # 真实点击展开整棵树，记录可见行
```

> 任何时候**先 `treelabels` 再动手**：它一次读全树的名字，几十毫秒，能把"我以为 `1.0.2` 是功能块"变成事实。
