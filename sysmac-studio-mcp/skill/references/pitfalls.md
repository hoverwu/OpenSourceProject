# 坑清单（每一条都是静默失败）

按"你会不会发现"排序：越靠前越隐蔽。遇到"自动化好像没反应"，逐条对。

## 1. DPI 没声明 → 坐标整体偏

非 DPI 感知进程看到的是虚拟化坐标，125% 缩放下比物理像素小 1.25 倍。表现：点哪都差一截，点的位置永远在控件上方/左侧。

```python
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)   # 必须在 import uiautomation 之前
```

判据：`GetWindowRect` 的尺寸比 UIA 的 `BoundingRectangle` 小 ⇒ 就是这个问题。

## 2. 没提权 → UIA 树是空的

**最隐蔽的一条**：普通权限下 `EnumWindows` 一切正常（HWND/标题/矩形都能拿到），但 UIA 只有 1 个 `TitleBarControl`、0 个子节点。看着像"这个控件不存在"，实际是 UIPI 挡住了。

判据：`ctypes.windll.shell32.IsUserAnAdmin()` 为 False；或 `OpenProcess(pid, PROCESS_QUERY_LIMITED_INFORMATION)` 返回 `err=5`。

## 3. 弹窗是独立顶层 HWND → 只在主窗口里找永远找不到

主菜单下拉、上下文菜单、ComboBox 下拉、对话框、文件对话框，**全都不是主窗口的子节点**。只在主窗口子树里 `FindAll` 会 100% 落空。

做法：枚举该 pid 的**所有可见顶层窗口**，逐棵搜索。`ss.py find/click/menu/popups` 已内置。

## 4. 前台锁定 / 锁屏 → 坐标与键盘全部失效

- `SetForegroundWindow` 对高权限窗口常被拒绝（**返回成功但没生效**）。可靠做法：Alt 键欺骗 + `AttachThreadInput` + 再 `SetForegroundWindow`。
- **工作站锁定时 `GetForegroundWindow()` 返回 0**：真实鼠标点击会落到未知窗口，键盘无目标，截图是黑图/桌面。
  此时只能用：UIA `Invoke()`、`TVM_*` 消息、`menu`（UIA 点菜单项）。
- 工程树的**定位**属于 `TVM_*`：`TVM_SELECTITEM(TVGN_CARET)` 任意深度都有效，锁屏照样能跑（实测）。只有点主菜单（`编辑>复制`）必须前台。
- 判据：`ss.py flow` 打印 `fg=False` ⇒ 别发 `at:`/`dbl:`/`rclick:`。

## 5. 动作序列跨进程失效 → 菜单/对话框在两次调用之间消失

弹出菜单的存在依赖当前进程的消息循环。分两条命令做"打开菜单"和"点菜单项"，第二条执行时菜单已经关了。

规则：**一次调用跑完一个完整序列**（`ss.py flow` 或自定义脚本内联）。

## 6. 截图不是"窗口"，是"屏幕的那一块"

- `PrintWindow` 对这个 WPF 主窗口拿到的是**全黑空白图**（实测）。
- 只能用 `ImageGrab.grab(bbox=窗口矩形, all_screens=True)`，它抓的是**屏幕上那个矩形里正在显示的内容**：窗口被遮挡 → 抓到遮挡物；两个实例窗口叠在一起 → 抓到上面那个。
- 锁屏时抓不到任何软件画面。

## 7. 工程树双击：选中行 = 重命名，未选中行 = 打开

双击的语义取决于**双击前是否已选中**（2026-10-31 实测）：

- 双击**已选中**的行 → 进入**行内重命名编辑框**。之后所有按键都进了那个框，看起来像"自动化突然失灵"。
- 双击**未选中**的行 → 第一次点击选中、第二次点击**打开编辑器**（用户手册里的"双击进入组态界面"）。

所以自动化顺序必须是：**先取消选中**（点最后一行下方空白，或点父节点）→ 再双击目标行。
恢复误入的重命名：给树焦点按 `{ESC}`。

- 其它可靠入口：右键菜单（项名可读，含"打开"）、`插入` 菜单。
- **单击只选中不打开**；`TVM_SELECTITEM`/方向键/`WM_KEYDOWN VK_RETURN` 都到不了这棵树（见 [control-tree.md §6](control-tree.md)）。

## 8. GoWPF 画布只有一块

梯形图/功能块图画布由 Northwoods.GoWPF 自绘（Direct2D），UIA 下只能定位到一大块 `Pane`/`Custom`：

- 触点、线圈、连线**量不到**；
- 不要试图在画布内"找元件再点"；
- 可行替代：截图 + 相对坐标；或改用 ST 文本编辑器（`Actipro SyntaxEditor`，是否支持 TextPattern/ValuePattern **未验证**）。

## 9. `uiautomation` 的 API 缺口与原型截断

- 没有 `GetDescendants()`、`WindowControl.SetForeground()`、`GetSupportedPatterns()`。
- `GetLegacyIAccessiblePattern()` **不接受** `createNew` 参数。
- `ControlFromHandle(hwnd)` 比 `WindowControl(ProcessName=...)` 可靠。
- 显式设置 `auto.SetGlobalSearchTimeout(10)`，否则找不到元素时每次都要等默认超时。
- **`import uiautomation` 会把 `SendMessageW` 原型改成 32 位**，导致 64 位 HTREEITEM 被截断（子节点数恒为 1 / 句柄为负）。发消息前恢复原型（见 [project-tree.md](project-tree.md#2-原生消息与句柄截断)）。

## 10. 提权进程的工作目录是 `C:\Windows\System32`

相对路径的输出文件会写进系统目录（而且往往没权限，静默失败或写到意外位置）。**所有文件参数一律用绝对路径。**

## 11. 引号、空格、斜杠

- 通过"文件投递"或 shell 传参时，**含空格的路径要再套一层引号**，否则被空格截断，后半段被当成别的参数（实测凭空造出过一个文件）。
- Git Bash / MSYS 会**重写** `/box:`、`/terminate` 这类以斜杠开头的参数；需要时用 `//` 前缀或改用 `.bat`/`.ps1`。
- `$_.xxx` 在 `powershell -Command "..."` 里会被 bash 展开；复杂逻辑写进 `.ps1` 文件。

## 12. 菜单名要按 UIA Name 取

主菜单第二排第 4 个是 `工程(P)`，**不是** `工程(E)`——写错直接 "menu not found"。

```
文件(F) 编辑(E) 视图(V) 插入(I) 工程(P) 控制器(C) 模拟(S) 工具(T) 窗口(W) 帮助(H)
```

## 13. ENABLED ≠ 生效

`编辑>复制(C)` 对 `配置和设置` 分支显示 **ENABLED**，点下去剪贴板一个字都不变。删除/粘贴的确认框也可能"点不动"。

判据只能是**外部状态**：剪贴板格式与字节数、树节点数、磁盘文件时间戳。不要用"菜单项能点"或"控件返回成功"当成功。

## 14. 显示名 ≠ 内部名

删除确认框显示内部名。实测选中行 `复制1_Buzzer_Config`，确认框写 `Buzzer_Config`。**名字不一致就取消**。

## 15. `文件>导入` 会先关闭当前工程

没另外保存的内存工程会在这里**永久丢失**（实测踩过）。导入前必须 `保存` 或 `另存为`。

## 16. 多实例窗口几乎完全重合

截图、坐标点击、`auto` 选 pid 都会命中"最上面那个"。多实例时必须按 pid 显式操作，并在 `ss.py wins` 里核对标题。

## 17. 等待：轮询状态，不要 sleep 死等

- 建工程/打开工程/编译/导入可能几十秒到几分钟；
- 唯一的"忙"信号是 `StatusBar` 里 `ProgressBar` 矩形非 0×0；
- 轮询上限设时间预算（如 5 分钟），超时按失败处理并记录，不要无限等。

## 18. 中文输出在控制台会乱码

Windows 控制台是 GBK，脚本 `print` 中文会变成 `????`。做法：把结果写 UTF-8 文件再读（脚本里加 `encoding='utf-8'`），或把 stdout 强制为 UTF-8：

```python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
```

## 19. 工程树：别用键盘下降，别用 UIA 行数判断展开

- **UIA 只暴露根节点**：`SolutionTreeView.GetChildren()` 恒等于根节点数（典型 2），展开后的一级/二级行不会出现。用行数变化判断"是否展开"永远为假——只能截图看。
- **`TVM_EXPAND` 只对根节点有效**：根节点返回 1 并真的展开；`POUs`/`功能块` 等返回 0 且像素级不变（虚拟树，展开由软件自己接管）。
- **键盘下降不可靠**：点行给焦点会被 WPF 抢回；`{DOWN}` 会钻进已展开节点的子节点；`{LEFT}` 在"已折叠节点"上会跳到父节点。实测废弃。
- 正解：`TVM_SELECTITEM(TVGN_CARET)` 直接定位（任意深度、不需要前台）+ `TVM_GETNEXTITEM(TVGN_CARET)` 回读校验；节点身份用**子节点数 + 顺序**核对。

## 20. 弹出菜单会整体"罢工"（进程级），鼠标/打字却仍然正常

实测现象（同一个实例，连续出现）：

- 点 `文件(F)`、`编辑(E)` 只让菜单栏**获得焦点高亮**，下拉不展开；再点一次也不展开。
- `Alt+P` / `Alt+F` 加速键完全无反应。
- 表格里右键只出 **IME 文本服务菜单**，表格自己的上下文菜单不出来。
- 但：**单元格单击、选项卡切换、往文本框打字全都正常**，`SendInput` 也返回成功。

排查结论（`GetGUIThreadInfo`）：焦点、`hwndActive`、`hwndMenuOwner`、`hwndCapture` 都正常指向主窗口，**不是前台锁、不是 UIPI**。
触发时机：一次原生 `#32770` 文件对话框（导出）关闭之后开始出现，怀疑是 TSF/IME 文档状态的残留。

处置顺序：

1. 先 `Esc` 两下、点一次单元格再点文本框（把 TSF 组合结束掉）→ 再试菜单；
2. 仍不行：**重启该实例**（先确保工程已导出/另存到磁盘）。不要以为是坐标错了或权限问题，一直重试点坐标。
3. 需要判断"是菜单坏了还是输入全坏了"，用一个**纯文本输入框**做探针（如工具箱检索框）打一个字母看有没有出现。

## 21. 工具栏按钮：`Name` 是空的，文字在 `HelpText`

主工具栏 30 个按钮的 `Name` 全为 `''`，靠 `HelpText` 区分：

```
剪切(T) 复制(C) 粘贴(P) 删除(D) 撤销(U) 重做(R) 帮助
3D可视化器 输出窗口(O) 编译窗口(B) 交叉索引窗口(C) 监视窗口(W) 监视标签页(表)(G)
微分监视器(D)... 查找和替换 故障分析 编译控制器(B)
在线 离线 监测 停止监测 运行模式 编程模式 同步 到控制器 从控制器
缩放到合适大小(F) 放大(I) 缩小(O) 重置缩放(R) 开始回放(S) 退出回放(E)
```

按 `HelpText` 找按钮比记坐标稳。注意它们大多是"上下文相关"的：`删除(D)` 在变量表里点下去**不一定**删得掉当前行（见 §22）。

## 22. 变量表里"名为空"的行删不掉，而且会被导出

全局变量表里出现一条 `名称` 为空、类型/地址有值的行时：

- `删除(D)`（右键/工具栏）、`Delete`、`Esc`、清空类型、`Ctrl+A`+`Delete` **全部无效**；
- 导出的 `.smc2` 里它真实存在：变量行写成 `++D=<类型> AT=<地址> Const=1 G=VAR_GLOBAL`，**缺 `N=` 字段**；
- 编译固定报 `变量名是空。 全局变量 - 名称`。

处理：认定为"删不掉的数据"，写进重建问题记录；别为了消掉它反复试各种按键（实测 6 种写法全失败）。

2026-11-06 补一条**识别**层面的进展（不是删除通道）：变量表单元格里"`Name` 形如 `项: …VariableViewModel，列显示索引: N`、`HelpText` 空、子 `Text` 空串"**就是"这一格为空"的机器可读形态**，有值的格子则 `Name`=`HelpText`=值。所以"空名行"可以在不动数据的前提下被程序化定位到具体行/列——完整格子契约见 [control-tree.md §16.7](control-tree.md)。删除仍然只能离线改 `.smc2`（缺 `N=` 的那一行）。

## 23. 菜单点不开时：先查残留模态窗与"罢工"，再用坐标+助记符兜底

先纠正一个常见误判：**主菜单栏是 UIA 可枚举、也可点的**。实测：

```
MenuItemControl name='文件(F)' id='文件(_F)' cls='MenuItem' enabled=True rect=(0,34,68x24)
```

`ss.py menu <pid> 视图(V) <任意项>` 能真的展开并列出弹窗项（本次实测列出了 28 项）。所以"菜单点不到"通常不是"它不是 UIA 控件"，而是下面三种情况之一：

1. **有残留模态窗**（最常见）：一个没关的 `#32770`（错误框、导出框、确认框）会让所有菜单点击失效。先把 `wins_of(pid)` 里 `cls == '#32770'` 的窗口逐个 `Esc`/点 `取消` 关掉；也可以让用户从任务栏把它翻出来关掉。
2. **菜单进程级罢工**（见 §20）：点菜单只在菜单栏留下高亮、不展开，`Alt+E` 无反应，但单元格点击/打字正常 → 重启实例。
3. **弹窗枚举方式不对**：下拉是**独立顶层 HWND**。不要遍历主窗口去找（几千个节点，实测 2~3 分钟还可能漏），只遍历 `hwnd != main_hwnd` 且可见的顶层窗口。
4. **残留的库索引类模态窗**（2026-10-31 实测）：`库索引` / `引用库` / `引用库文件` 没关掉时，工程树双击看起来**完全没反应**（选中正常、页面不出现），日志里表现为 `当前选项卡：（无）`。每次打开页面前先按标题关一遍这些窗口，失败步骤之后也要兜底关一遍。

**兜底写法（实测可靠，本次导出就是这么开的）**：按坐标点菜单栏那一格（窗口左上 `(left, top)` 时 `文件` ≈ `(left+48, top+55)`，125% DPI），再发助记符键 `E`；不要发 `Alt+E`（`Alt` 会把菜单栏切进键盘模式吞掉后面的键）。

## 24. `grab` 截图里没有弹出菜单和对话框

`ss.py grab` 用 `PrintWindow` 抓**主窗口**的内容，所以：

- 下拉菜单、`#32770` 对话框、右键菜单**都不在截图里**；
- 别用"截图里有没有菜单"来判断菜单开没开/点位置对不对；
- 要验证菜单，用 §23 的弹窗枚举；要截对话框，得抓那个对话框自己的 hwnd。

## 25. 导出对话框三件套：前台、剪贴板、别用 ValuePattern

实测 `文件>导出(E)...` 的 `#32770 '导出文件'`：

1. **必须 `SetForegroundWindow(dialog_hwnd)`**。只把主窗口抢到前台，`Ctrl+A` / `Ctrl+V` 会发给主窗口，文件名框的值一个字节都不变（看起来"打字没反应"）。
2. **中文文件名只能用剪贴板**：`auto.SendKeys` 打不出 CJK；`uiautomation` 的 `SendKeys` 传中文会静默丢字。塞 `CF_UNICODETEXT`（`SetClipboardData(13, ...)`，注意 `GlobalAlloc/GlobalLock` 要声明 `restype/argtypes`，否则 64 位下 `OverflowError: int too long to convert`），再 `Ctrl+V`。
3. **`EditControl.GetValuePattern().SetValue()` 会抛 `COMError -2147220992`**（该控件不实现 ValuePattern）。不要用它写路径。
4. 文件名 Edit 的 `AutomationId` 是 `1001`，`保存(S)` 是 `'1'`；覆盖确认是**另一个 `#32770`**，按钮 `是(Y)` / `否(N)`。
5. 路径尽量只给**文件名**，让对话框停在上次目录——从命令行传 Windows 完整路径时反斜杠可能被 shell 吃掉（实测盘符后的分隔符全丢、变成盘符相对路径，软件报 `文件名无效。`）。

现成脚本：`scripts/ss_export.py <pid> <文件名>`。

## 26. 编译错误列表：几何定位 + 滚动 + UTF-8

- 网格是 `DataGridControl`，**没有可用的 Name/AutomationId**；用 `BoundingRectangle.top > 630` 才能把它从界面里挑出来（125% DPI 实测）。
- 行内容 = 每行子 `TextControl` 顺序拼接：`编号 | 说明 | 程序 | 位置`。`说明` 里可能含换行，落盘时一行一条会"行数 ≠ 条数"，用 `编号` 去重/排序。
- 全量读取靠 `ScrollPattern.SetScrollPercent(-1, 0..100 step 5)`，每屏 `sleep 0.35`；**滚动太快会漏行**（实测 385 条漏 4 条）。
- 面板顶部 `TextControl` 直接给 `N 错误` 与 `M 警告`，用它做"编译结束"的判据比读进度条稳（连续两次轮询相同即结束）。
- 结果**必须写 UTF-8 文件**再看（控制台 GBK，见 §18）。

现成脚本：`scripts/ss_build.py totals|list|run <pid> [out.txt]`。

## 27. 目标是提权进程时，中权限的注入**静默无效**

实测：Sysmac Studio 常以管理员启动（`TokenElevation=1`）。中权限脚本对它做 `SendInput` / `mouse_event` / 键盘注入，**不报错、不抛异常，界面毫无反应**——表现和"点在空白处"一模一样，非常容易误判成"坐标错了"或"控件不可点"。

判据（先查再动手）：

```python
import ctypes, ctypes.wintypes as wt
k, a = ctypes.WinDLL('kernel32'), ctypes.WinDLL('advapi32')
k.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]
a.GetTokenInformation.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
def elevated(pid):
    h = k.OpenProcess(0x1000, False, pid); tok = wt.HANDLE()
    k.OpenProcessToken(h, 0x0008, ctypes.byref(tok))
    e = ctypes.c_int(); sz = wt.DWORD()
    a.GetTokenInformation(tok, 20, ctypes.byref(e), ctypes.sizeof(e), ctypes.byref(sz))
    return e.value            # 1 = 提权
```

对照实验：同一个坐标，中权限点一次没反应、提权点一次就生效——**先做这个二分，再怀疑坐标**。

顺带：`UIA` **读**树对提权窗口通常仍可用（能 dump、能读 Name），所以"能读到"不代表"能点动"。

## 28. 125% DPI 下有**两套坐标**，混用会系统性偏 150 px

同一个 960×629 物理像素的对话框：

| 调用方 | `GetWindowRect` 得到 |
| --- | --- |
| 声明了 DPI 感知（`SetProcessDpiAwareness(2)`） | `(0, 29, 960, 629)` |
| 没声明 | `(0, 23, 768, 503)` ← 被虚拟化成逻辑像素 |

所以：**坐标必须来自 DPI 感知进程**，截图（也是 DPI 感知的）与点击用同一套数值才不会错。混用时表现为"点在按钮上/按钮旁边都试过，全没反应"。

推论：在提权守护进程里跑点击脚本时，**脚本自己也要先声明 DPI 感知**，不能只靠父进程声明。

## 29. 文件对话框：对列表单元格 `SetValue` 会触发**就地重命名**

实测 `导出文件` 的 shell 视图里，文件列表每行的"名称"列在 UIA 里是 `EditControl`（值就是文件名）。对第一行做 `GetValuePattern().SetValue('新名字')`：

- 抛 `COMError (-2146233083)`，**但副作用已经发生**：弹出
  `重命名文件 → 要将"<原工程名>.smc2"重命名为"…_Copy (2).smc2"吗？此位置已经包含同名文件。`
- 一旦误按"是"，**源工程文件名就被改了**。

安全做法（实测可靠）：

1. 想选一个**已存在**的文件名 → **单击列表里那一行**，文件名框会自动填好，然后点 `保存(S)`；
2. 想输一个**新**名字 → 单击文件名框（把焦点放进去）后输入；不要碰列表单元格；
3. 任何 `SetValue` 都只用在"确定是文件名输入框"的控件上，且失败后**立刻截图核查有没有冒出新对话框**。

配套的两个已知限制（同一对话框上实测）：

- `KEYEVENTF_UNICODE` 逐字注入**进不去** DirectUI 编辑框（`VK_DELETE` 这类单键能进去，说明焦点是对的）；
- `Ctrl+A` / `Ctrl+V` 在该 DirectUI 编辑框里也可能静默无效。

所以"选已有行 + 保存"是最稳的一条。

## 30. 常驻提权守护进程是**单任务**，卡住的调用会把队列堵满 900 s

典型实现：读 `job.in` → `subprocess.run(..., timeout=900)` → 写 `job.done`。后果：

- 一个**等待界面响应**的调用（例如对弹了模态框的控件做 UIA `SetValue`/`Invoke`）会让守护进程阻塞到 900 s 超时才放行；
- 期间投递的后续命令全部排队，表现为"所有自动化突然无响应"。

规避：

1. 调用前先自问"这个控件会不会等界面响应"——会等的（弹窗、模态确认）改用**先处理弹窗再调用**；
2. 长等待用"投递 → 轮询 `job.done`/日志"的方式，别在同一调用里 sleep 死等；
3. 卡住时的恢复顺序：先用另一个已提权的通道点掉弹窗（弹窗不处理，超时也没用）→ 再等 `job.done` / 看日志最后一行是谁。

## 31. 输入法会吞掉 `SendKeys` 的 ASCII —— 文本统一走剪贴板

中文输入法（微软拼音）处于中文态时，`SendKeys`/`keybd_event` 打出来的字母会进入**组合态**，界面上看是"什么都没输入"或只进去前几个字符。2026-10-31 在 EtherCAT 关键字框、全局变量表、结构体成员表上均复现。

可靠做法：

1. 先把前台窗口的输入法切成英文半角：`ImmGetContext` → `ImmSetConversionStatus(himc, IME_CMODE_ALPHANUMERIC(0), 0)` → `ImmSetOpenStatus(himc, False)`；
2. 文本本身**不用按键**，写剪贴板后 `Ctrl+V` 粘贴（中文/ASCII 都适用）；
3. 粘贴后**读回校验**（`ValuePattern.Value` 或表格行文本）。WPF 的 `SetValue` 常不提交绑定，读回才发现"名称被重置"。

`Ctrl+A` 在某些 DirectUI 编辑框里无效（见 §29），所以粘贴前先点一下目标控件、必要时用 `ValuePattern.SetValue('')` 清空。

## 32. 表格里没关的下拉/就地编辑会"吃掉"第一次菜单点击

全局变量表的"数据类型"列是**可编辑下拉框**。录完一行如果下拉还开着：

- 点菜单栏 `文件(F)` 只会把下拉关掉，菜单不展开；随后发 `E` 也没有对象接收，表现为"导出菜单唤不出来"；
- 工程树/选项卡的第一次点击同样会被用来**提交**那个编辑框。

对策：每步开始和导出前，先收掉弹出层（见下方判定），再点菜单；打开树节点前确认树真的拿到了焦点（见 project-tree.md §3.4）。

**怎么可靠地判定"下拉还开着"**（2026-10-31 从失败 dump 里定位到）：WPF 的下拉/子菜单在 UIA 树里是 **`ControlType=Window` 且 `ClassName='Popup'`** 的子节点（压在窗口中部，里面是一串 `ListItem`）。按 Win32 `EnumWindows` 的窗口类过滤**抓不到**它（它的窗口类名也是 `HwndWrapper[...]`），所以 `wins_of(pid)` 加 `cls=='Popup'` 永远为空。

可靠收法（`ssk.dismiss_popups`）：

1. 在 UIA 树里找 `Window/cls=Popup`；没有就直接返回；
2. 有则先发 `{ESC}`，重查；ESC 常因焦点不在宿主控件上而**无效**；
3. 仍然存在就**鼠标点一下主菜单条右侧空白处**（`main_left+width-140, main_top+50`），弹出层随之关闭；
4. 每轮重查，最多 3 轮。仍然关不掉时把弹出层名字记进日志，不要继续点菜单。

导出失败时的 dump 里那个 `ListBox`（`_eAREA`、`_eBCD_FORMAT`…）就是全局变量"数据类型"列的下拉，它不在菜单栏下面，所以"点文件菜单"只会把它关掉。

## 33. `TVM_GETITEMRECT` 的真实契约（写错会把软件打崩）

以 Windows SDK `CommCtrl.h`（10.0.26100.0）为准，宏是：

```c
#define TreeView_GetItemRect(hwnd, hitem, prc, code) \
    (*(HTREEITEM *)(prc) = (hitem), \
     (BOOL)SNDMSG((hwnd), TVM_GETITEMRECT, (WPARAM)(code), (LPARAM)(RECT *)(prc)))
```

也就是：

- **wParam = fItemRect**（1 = 整行矩形，0 = 只要文字）；
- **lParam = 指向 RECT 的远端地址**；
- **RECT 的第一个字段（left）先塞 `HTREEITEM`**，消息返回后这个字段被矩形覆盖。

实测坑：

- 旧写法 `wParam=hItem, lParam=RECT*`（把文档里"wParam 是项句柄"当真）→ 永远返回 0。
- 把两者对调成 `wParam=RECT*, lParam=1` → 目标进程把 1 当指针写，**直接崩溃**（`SysmacStudio.exe` 消失）。跨进程消息 ≥ `WM_USER` 不做封送，指针必须是目标进程地址，这一点对每个原生消息都要单独核对。
- 只有**可见行**才拿得到矩形，先 `TVM_ENSUREVISIBLE`。

跨进程 `SetFocus(别进程的 HWND)` 返回 `NULL`，除非双方线程先 `AttachThreadInput`。当时据此写过"这棵树不响应键盘"——**这句是错的**（2026-11-06 修正）：树在**真的持有键盘焦点**时响应真实按键（`VK_RIGHT` 能展开、`VK_APPS` 能弹节点菜单），只是 `SetFocus` 拿焦点不稳，要给焦点得**真实单击**那一行。判焦点别看 `GetFocus()`（跨线程恒 0），用 `GetGUIThreadInfo(树所在线程).hwndFocus == 树句柄`，见 §49。

判定办法：节点被选中但页面没出来 ⇒ 先看"双击前是否已选中"（§7），再查行号/坐标，不要怀疑节点名。

## 34. 批处理外壳：CRLF、`-ArgumentList ''`、单实例

- `.bat` 必须是 **CRLF**。用编辑器改成 LF 后，cmd 会把行拆碎，报 `'administrator' 不是内部或外部命令` 之类的鬼话。
- 自提权的 PowerShell 一行：无参数时**不要**写 `-ArgumentList ''`，会抛 `ParameterArgumentValidationError`；要按 `%~1` 是否为空分支。
- 同一个软件实例被两个脚本同时驱动 → 日志交错、菜单全空。用命名互斥体（如 `Local\SysmacAuto_<工程名>`）挡住第二次启动。

## 35. 提权与否：Sysmac 本体可以中权限跑，UIPI 只卡"低→高"输入

- 实测 `SysmacStudio.exe` 没有 `requireAdministrator` 清单、也没有 `RUNASADMIN` 兼容标记，**中权限能正常启动并新建工程**。
- UIPI 规则：**中权限进程的鼠标/键盘注入到提权窗口会被静默丢弃**；反过来（提权进程 → 中权限窗口）没问题。
- 所以两条路都行：① 整体提权跑（老路，需点一次 UAC，自动化对提权 Sysmac 有效）；② 全程中权限（无 UAC，Sysmac 也中权限）。
- 跨完整性仍然可用的是 **UIA 的 Pattern**：中权限能 `GetWindowPattern().Close()` 掉提权窗口（实测）。
- 桌面**锁屏/无人值守**时：UAC 弹窗会被自动取消，`ImageGrab` 报 `OSError: screen grab failed`，`SetCursorPos` 类输入也不会产生真实交互 —— 此时不要判断"脚本逻辑坏了"，先看会话是否解锁。

## 36. `auto.SendKeys('^a')` 会把 `^a` 当普通字符敲进去

`uiautomation` 的 `SendKeys` **不认 `^` 前缀**：`SendKeys('^a')` 是"输入字符 ^ 和 a"，不是"Ctrl+A"。导出对话框里就踩过：

- 现象：目标文件名变成 `<原文件名>.smc2^a^v.smc2`，真正要保存的文件根本没生成；
- 判据：目录里出现带 `^a^v` 字样的怪文件；
- 正确写法只有两种：`SendKeys('{Ctrl}a')` / `SendKeys('{Ctrl}v')`，或者自己发 `keybd_event`：

```python
def ctrl_key(vk):
    u.keybd_event(0x11, 0, 0, 0); time.sleep(0.05)   # Ctrl down
    u.keybd_event(vk,   0, 0, 0); time.sleep(0.05)   # A=0x41 / V=0x56
    u.keybd_event(vk,   0, 2, 0); time.sleep(0.05)
    u.keybd_event(0x11, 0, 2, 0); time.sleep(0.15)   # Ctrl up
```

这个坑和 §31（输入法吞 ASCII）是两回事，但常常同时出现：表现为"框里进了几个怪字符"或"什么都没进"。

## 37. EtherCAT 拓扑：从站行、端口行与"插入"的真实语义

**控件层级（2026-10-31 实测，V1.68 64bit）**

- `TopologyView`（`TreeView`）→ `TreeItemControl` 主设备行（名字以 `…MasterDeviceTreeNode` 开头）；
- 主设备行下面才是从站行：`…SlaveDeviceTreeNode`，行里带
  `EditControl aid=editBox`（节点号，可直接改）、`ButtonControl`（"+"，点了没反应）、
  `ImageControl`（设备图标）、`TextControl E001`（设备名）、`TextControl 型号 Rev:x.x`、`TextControl '---'`。
- **不展开时 UIA 只给第一个从站行**。选中该行按 `→`（VK_RIGHT）后，下面才冒出端口行：
  `TextControl 'X2'` / `'X3'` / `'Internal Port'`，每行还带一个 `Redundancy` 文本。这一步只是展开，不改变组态。

**插入语义**

| 网络状态 | 右键工具箱结果行 →「插入(I)」 | 说明 |
| --- | --- | --- |
| 空网络 | **有效**，挂到主设备后面 | 这是第一次插入能成功的原因 |
| 已有从站 | **无效**：菜单能点、不报错、拓扑和工程树都不变 | 插入位置是"当前选中的节点/端口"，链尾并不会自动接管 |
| 已有从站 + 选中某端口行 | 未完全验证 | 选中 `X2`/`X3` 行后再插入是本 Skill 目前唯一可尝试的入口 |

其它实测无效的入口（不要再试）：

- 从站行里的「+」按钮（`ButtonControl`）：点了无任何反应；
- 主菜单 `插入(I)`：子项只有 `回路(R)`、`导出设备`、控制器/驱动器/HMI… 以及 `从设备终端(S)`，而 `从设备终端(S)` 的二级菜单只有 `EtherNet/IP耦合器`、`PROFINET耦合器`——**没有 EtherCAT 从站**；
- 慢速分段拖拽（≥40 段 + 目标处停顿 0.4 s）：在这个 WPF 拓扑上始终不生效；
- 双击工具箱结果行：无反应。

**一次插入 ≠ 一个从站**

插入 `GX-JC06(IN,X2,X3) Main device` 后，工程树与导出文件里都会出现**两个**从站：
`节点N : GX-JC06(IN,X2,X3) Main device (E001)` 和 `节点N+1 : GX-JC06(X4,X5,X6) Sub-device (E002)`。
即这类"主/子两半"的模块是成套出现的，`从设备数量` 也按 2 计。判断"到底插进去几个"不要数界面行，按下面 §38 解析导出文件。

**删除**：右键从站行 → `删除(D)`（无确认框），会连同成套的 Sub 一起删掉。工程树里的从站行**没有**右键菜单。

**设备名**：右侧参数表里有 `设备名称` 行（初值 `E001`），可编辑；导出后它出现在 DN 末尾的括号里：`… Main device (E001)`。样本里写的是 `(总站123)` 这种业务名，需要在插入后单独改。

## 38. 组件组态的正确性要用导出文件当真值

工程树（`多视图浏览器` 里的 `节点N` 行）**会滞后**，`从设备数量` 的语义也和行数对不上（曾出现"数量=1、树里两行"）。唯一可靠的判据是导出后解析 `.smc2`：

```python
import zipfile, re
z = zipfile.ZipFile(r'...\xxx.smc2')
txt = z.read([n for n in z.namelist() if n.lower().endswith('.oem')][0]).decode('utf-8', 'ignore')
names = re.findall(r'subtype="(?:SlaveProxy|NXBusCoupler)"[^>]*?DN="([^"]*)"', txt)
```

得到的 DN 形如 `节点1 : GX-JC06(IN,X2,X3) Main device (总站123)`——节点号、型号、变体、设备名全在里面。做"照抄组态"的校验时，拿这个列表和样本逐条比节点号，比读界面可靠得多。

## 39. 权限：本机 Sysmac 实际以 High 运行（修正 §35）

§35 说"Sysmac 没有 `requireAdministrator` 清单、中权限能跑"。2026-10-31 再测：**本机这个实例是 High**（`integrity_of(pid)` 返回 `High`，启动途径不同结果不同，可能是快捷方式/兼容标记带的）。

- 中权限脚本对 High 窗口：UIA 树只剩 `WindowControl` + 标题栏，`ControlFromPoint` 直接 `0x80070005 拒绝访问`，鼠标键盘注入被 UIPI 静默丢弃；
- 排查顺序：先读两边完整性（`OpenProcess(0x1000)` → `OpenProcessToken(TOKEN_QUERY)` → `GetTokenInformation(TokenIntegrityLevel=25)` → `GetSidSubAuthority` 最后一个子项），**脚本等级低于目标就直接报错退出**，别浪费时间猜"控件找不到"；
- 结论不变：要么两边都提权，要么两边都中权限。提权 .bat 自启动（`Start-Process -Verb RunAs`）在本机实测**仍会弹一次 UAC**；无人值守/UAC 被拒时提权会立刻失败（`The operation was canceled by the user`），不要把它当成脚本逻辑错误。
## 40. 新建工程点「创建」后会弹一个 WPF 提示框，不点「确定」工程永远建不出来

现象（2026-10-31 实测，Sysmac 1.68 64bit / 提权批处理）：选完型号点「创建」，主窗口标题长时间不变，
后续所有步骤都报“工程树不存在”，日志里主窗口还停在 `StartPageView`。

原因：紧接着会弹出一个**说明性提示框**，正文以「启用此功能可以将工程编辑直接保存到工程文件中。
保存工程可能需要一些时间，因为在…」开头，只有一个「确定」按钮。它不是 `#32770`，而是
`HwndWrapper[SysmacStudio…]` 顶层窗（标题也是 `Sysmac Studio`，尺寸约 508×170），
在 `EnumWindows` 里和主窗口并列；模态阻塞主窗口，标题因此不会变成「工程名 - xxx」。

做法：等待“工程建立”的循环里顺手点掉它——只认 `ButtonControl` 名为 `确定`/`OK` 的小窗。
**不要顺手点 `是(Y)`**：保存提示也是顶层窗，那是需要用户决定的分支。

```python
def auto_ok_popup():
    main = ssk.main_hwnd(PID)
    for w in ssk.wins_of(PID):
        if w['hwnd'] == main or 'HwndWrapper' not in w['cls']:
            continue
        if w['rect'][2] * w['rect'][3] > 900 * 700:   # 弹窗都很小，大窗是主界面
            continue
        d = auto.ControlFromHandle(wt.HWND(w['hwnd']))
        for c in ssk.walk(d, 10):
            if c.ControlTypeName == 'ButtonControl' and (c.Name or '').strip() in ('确定', 'OK'):
                ssk.click(c)          # WPF 按钮 Invoke 不需要前台
                break
```

同一个遮挡也会让「挂库 / 导出」的菜单点击看起来“菜单打不开”或“对话框没出现”，排查时先看有没有这类小顶层窗。

## 41. 低级钩子回调里做 UIA / 写盘 / 打印 → 按 Win 键整个控制台卡死

现象（2026-10-31，`ss_record.py` v0.1）：录制器跑起来后按下 Win 键，cmd 窗口立刻永久卡死，
连 Ctrl+C 都不响应，只能到任务管理器里结束进程树。

机制：`WH_MOUSE_LL` / `WH_KEYBOARD_LL` 的回调由系统在**安装钩子的那个线程**上同步调用，
钩子不返回，输入队列就不再往下走。v0.1 在回调里直接 `auto.ControlFromPoint` 解析元素、
写 `.jsonl`、`print`；Sysmac 是 High 权限，那次跨进程 UIA 调用要等 Sysmac 的 UI 线程，
而 Sysmac 的 UI 线程此刻正卡在“等这个钩子返回”上——双向死等。开始菜单一弹出就必然触发。

做法（v0.2.0 架构，见 [recording.md §1.1](recording.md)）：

- 钩子回调只做三件事：读 `MSLLHOOKSTRUCT`/`KBDLLHOOKSTRUCT`、`queue.put(原始数据)`、`CallNextHookEx`。
- 另起一个 worker 线程消费队列，所有 UIA / 剪贴板 / 磁盘 / 打印都在那里做。
- 钩子里的“只录 Sysmac”判断只能读 worker 每 0.1 s 刷新的 `fg_pid` 整数缓存，
  不能在钩子里查窗口标题（那同样是跨进程调用）。
- 停止用 `PostThreadMessageW(WM_QUIT)` 打断消息泵，然后 `_unhook()` → `join(worker)` → 写汇总。

自测时别用 `SetCursorPos` 验证鼠标钩子（它不触发低级鼠标钩子），要用 `SendInput` 的
`MOUSEEVENTF_MOVE`；键盘用 `keybd_event` 敲几个字母，看 `.jsonl` 里有没有 `text`。

## 42. 轴：创建入口在工程树右键，「插入(I) > 轴设置(A)」的老对话框不稳

- 2026-10-31 录制确认的创建入口：工程树 `轴设置` **右键 → 添加 → 子菜单第一项**。
  新行 `MC_AxisNNN` 直接出现在树下，轴号按创建顺序自动分配；
  之后 **F2 / 双击行** 进入行内重命名（临时 `EditControl`，`AutomationId` 是随机数字，
  别按 id 找，按“矩形落在树里”找）。
- 老脚本用的主菜单 `插入(I) > 轴设置(A)` 走的是参数对话框，弹不弹、字段顺序都不稳定，
  已弃用。
- 轴页的**下拉列表不属于组合框**：`combo.GetExpandCollapsePattern().Expand()` 之后，
  `walk(combo, 6)` 拿不到任何 `ListItem`——项挂在主窗口的 `Window(cls=Popup) > Pane` 下
  （也可能是独立顶层弹窗；用 `ssk._popup_roots` 两种都扫）。
  判据用「ListItem 的 x 与组合框对齐、top 在组合框上下 400px 内」。
  这条坑同样适用于 `pick_combo`：它只在组合框内部找项，对轴页无效。
- 顶部组合框是 **2~3 个**（实测 y=247/270/377），类型和关联节点不能按序号取：
  展开后看内容认（含 `伺服器轴` = 类型，以 `节点` 开头 = 关联节点）。
- 关联节点只有在可选节点里出现伺服驱动器（`R88D…`/`R88M…`/`1SN…`）时才选；
  工程里只有 `GX-JC06` 耦合器时没有可关联项，按约定跳过并记录，不要拿耦合器硬填。

## 43. 锁屏后所有 UI 自动化都会"假死"——先看 `GetForegroundWindow` 属于谁

2026-11-05 实测：用户锁屏（Win+L）后，前台窗口是 `LockApp.exe` 的
`Windows.UI.Core.CoreWindow`，`SetForegroundWindow` / `ShowWindow` 全无效，
脚本只能拿到"前台不是目标进程"。

- 判据：`GetForegroundWindow` → `GetWindowThreadProcessId` → `tasklist /FI "PID eq N"`
  返回 `LockApp.exe` 就别再重试点击，直接停手等解锁。
- 典型表现：`ssk.force_foreground` 后 1.5 s 内前台又被抢回 `LockApp`，依赖前台的编译脚本
  会以 rc=3 退出并写 `前台不是 Sysmac`。
- 别用"多试几次"绕过：锁屏下 SendInput/UIA 全部无效，重试只会空烧时间。
- 另外，提权执行通道用 `shell=True` 拉起的控制台窗口偶尔会抢前台；脚本里的前台断言
  要重试 3 次（每次 `force_foreground`），仍失败才放弃。

**锁屏不等于不能干活**（2026-11-06 实测）：需要前台的**坐标点击**确实全废，但
`InvokePattern.Invoke()` 调用按钮不需要前台（后台编译脚本就是这么编译的），
`taskkill` + `Popen` 打开/关闭工程也不需要前台。所以锁屏下的可行组合是：
**常驻提权执行通道 + 重开工程 + 后台编译**（外部一次性脚本），全程不点坐标。
只有必须操作弹出菜单/对话框/编辑器的步骤才需要等解锁。

## 44. 注入了 ST 实体但编译说"必须存在至少1行有效代码(注释除外)"

PouBody 实体的 `version` 属性必须是 `"0.2"`（工程内所有 StructuredText 本体都是 0.2；
Ladder/FBDExtended 是 `"0"`）。写 `"0"` 时软件能打开、能看到源码，但编译按空程序处理。
同一症状还常见于 `END_IF` 缺分号——先查这两条，再去怀疑实体引用关系。
详见 [offline-surgery.md §8.1/§8.2](offline-surgery.md#8-从零新建-poust-功能块--程序--任务--实测可行2026-11-06-修订)。

## 45. 程序的 subtype 不是 `StructuredText`：整张程序变量表会"隐形"

2026-11-06 实测，同一个程序两种写法对比：

| 写法 | 打开 | 编译 | 结果 |
| --- | --- | --- | --- |
| `Program / StructuredText` + `Variables / StructuredTextProgram` | ✅ | ✅ | 程序里**每个变量**都报 `未定义的标识符`（37 条），FB 内部变量正常 |
| `Program / MultipartLadder` + `Variables / Ladder` + 段内 `IST` 内联 ST 块 | ✅ | ✅ | 0 错误 |

错误跟踪日志 `%APPDATA%\OMRON\CXAP\Log\SysmacStudioErrorTrace.log` 会给出铁证：
`Extended data is not an instance of VariableGroups`、`PouIFsRule.UpdateEntityTargetResult`
的 `KeyNotFoundException`、`NexSTBuilderService` 的 `Invalid source`。

- 真实工程里 `Program` 的 subtype 只见过 `MultipartLadder` / `FBDExtended`(安全)。
- 程序变量表的 `Variables` 子实体**只有** `SourceHolder`，加了 `PouIFLibraryHolder` 不是解决办法。
- 程序体是"多段梯图容器"，ST 代码在 `<PouBody subtype="Ladder" name="PrgMain">` 下的
  `Inline / StructuredText` 子实体里，配套文件是带 BOM 的梯图 JSON（`IST` 块）。
- 详见 [offline-surgery.md §8.1](offline-surgery.md#81-实体骨架)。

## 46. 编译没跑起来时，错误网格仍然可以是 0 行（假 0 错）

外部一次性后台编译脚本用"CPU 静默 3 次采样"判编译结束。如果 `InvokePattern` 没生效、按钮点错、
或模态窗挡住，它会在 20~40 s 后照样打印"编译结束"，然后读到 **0 行**错误、面板显示
`0 错误 / 0 警告`——看起来完美，其实什么都没编。

实测对照：故意写成 `xP := ;` 的工程同样返回 0 行；同一脚本换个结构重跑却报 37 条。

判据必须三条同时成立：

1. 编译期间 CPU 时间明显增长（本次全量编译 8~50 s，视工程与机器负载）；
2. 面板读到 `N 错误` 与 `M 警告` 两个数字（不是只读网格行数）；
3. `%APPDATA%\OMRON\CXAP\Log\SysmacStudioErrorTrace.log` 编译前后**字节差为 0**
   （编译前 `os.path.getsize` 记 mark，编译后比对；有新增就说明内部抛过异常）。

## 47. `LREAL` 不会隐式转换成 `REAL`

把 FB 的 `yP : LREAL` 赋给程序的 `REAL` 变量，报
`无法将LREAL转换为REAL。 PRG_Example PrgMain 梯形图:行0, ST:line 102, column 18`。
注意行号是**内联 ST 块内的行号**，不是源文件行号。

- 修复：`rPowerCmd := LREAL_TO_REAL(fbCtrl.yP);`
- 反方向 `REAL` → `LREAL`（实参传给 `LREAL` 形参）是隐式的，不用改。
- 报错里的 `梯形图:行0` 指的是段内梯图坐标（ST 块放在第 0 行），与 ST 行号不是一回事。

## 48. `force_foreground` 里的 Alt 轻点会**吞掉紧随其后的点击**

2026-11-06 实测（probe_sweep）：为了绕过"SetForegroundWindow 返回成功但没生效"，抢前台的写法是先 `keybd_event(ALT)` 两下再 `SetForegroundWindow`。但**窗口已经在前台时**再点这一下 Alt，会把 Sysmac 的菜单栏切进助记符模式，后面第一个真实点击被当成"退出助记模式"吃掉 —— 表现是"一轮里只有第一次点击生效，其余全静默"。

修法：函数开头先判 `GetForegroundWindow() == hwnd`，是就直接 `return True`，**不要碰 Alt**。

```python
if u.GetForegroundWindow() == hwnd:
    return True
```

同类症状（"只有第一下有用"）也见 §20 的菜单罢工，区别是罢工**重启实例**才好，而这个改代码就好。

## 49. `VK_APPS` 弹出来的常常是**窗口系统菜单**，不是节点菜单

节点没菜单、或树没拿到键盘焦点时按 `VK_APPS`，Sysmac 会给一个 `#32768` 弹层，内容是 `还原 / 移动(M) / 大小(S) / 最小化 / 最大化(X) / 关闭`。它是**窗框的系统菜单**，与树无关。tctxA 一度把它当成根节点的菜单记录在案。

- 判据（已实现，`is_window_system_menu`）：弹层里 ≥3 个 `MenuItemControl` 命中上面那串名字 → 丢弃。
- 焦点判据：`GetFocus()` 跨线程**恒返回 0**，别用它。要 `GetWindowThreadProcessId(树句柄)` → `GetGUIThreadInfo(tid, &gti)` → `gti.hwndFocus == 树句柄`（`tree_has_focus()`）。为假时 `VK_APPS` 必然只给系统菜单，直接跳过。
- 反向教训：**这棵树是响应键盘的**，只要焦点真在它上面（§33 的旧结论已修正）。

## 50. 点段落头（根行）会**折叠整个段落**，把后面所有序号打乱

树根 `配置和设置` / `编程` 的**整行都是展开开关**，不只是那个 `+/-` 三角。实测（外部一次性探针）：在根行上点任何位置，`TVM_GETCOUNT` 当场变化 → 所有可见行序号平移 → `row_hit` 用"点完让树回读句柄"来证明坐标时**永远证不中**（`# PATH 1 !! never hit`）。更糟的是它把整批扫描的坐标系挪走了，后面的记录全部错位。

- 根节点走**键盘通道**（`caret + VK_RIGHT`），不点行；`treectx` 对 `len(path)==1` 的路径完全不用鼠标。
- 同理，任何"探测坐标"的循环里都不要点根行；要给树焦点就点**一个非根行**。

## 51. `PostMessage(WM_CONTEXTMENU)` 在 Sysmac 树上**永远无效**

2026-11-06 用 5 通道探针（外部一次性脚本：80 ms 轮询 `EnumWindows` / `FindWindowExW('#32768')` / `hwndMenuOwner`）实测：给树窗口 post `WM_CONTEXTMENU (0x007B)` + 屏幕点 lParam，返回值是成功，**但对菜单正常的节点也不弹任何东西**。Sysmac 的上下文菜单是在它自己的鼠标/键盘处理里现场构造的，不走窗口过程。

→ 别再往这条路投时间。可用的只有：真实右键、真实 `VK_APPS`（都要前台 + 树有焦点）。

注意"没弹菜单"有两种截然不同的原因（真没有 vs 采集缺陷），所以 `treectx` 的判定阶梯是 `RCLICK(行中心) → RCLICK2(同行 +80px，避开展开三角) → VK_APPS`，三条全空 + 焦点已证 + 截图留证，才敢写"该节点类型没有上下文菜单"。

## 52. 展开：`TVM_EXPAND` 只对根有效，深层要 **caret + 真实 `VK_RIGHT`**

- `TVM_EXPAND`：根返回 1 且真展开；一级及以下返回 0、截图像素不变。**别拿它的返回值当"展开成功"的判据。**
- 有效写法：真实**单击该行**（给树键盘焦点）→ `TVM_SELECTITEM(TVGN_CARET, h)` → 真实 `VK_RIGHT`（`SendInput`，不是消息）→ 回读 `TVM_GETITEMSTATE(h, TVIS_EXPANDED)`。实测 probe_expand5：深度 1~2 的 10 个折叠节点 9 个这样打开，不需要知道 `+/-` 三角在哪。整棵 84 节点树能逐级展开到 `1.0.2.43`（`treectx` 的 `ancestors: 1=expanded 1.0=expanded 1.0.2=expanded` 就是这么来的）。
- 代价：需要前台 + 键盘能到达树，**锁屏时失效**。所以能用光标消息解决的（`count`/`copy`/`paste`/`treelabels`）就不要展开。

## 53. 行坐标的三个必踩前提：行高 26、客户区≠窗口、窗口可能整块在屏外

1. **`ROW_H=26`、一滚轮 = 3 行**（probe_geom2 实测，单调 +26）。整段可见区只需 1 次 `TVM_GETITEMRECT` + `TVGN_NEXTVISIBLE` 步进就能算完；逐行发消息（每行一次 `OpenProcess`/`VirtualAllocEx`）会把一次 `treerows` 拖成 3 s/次调用，实测把整轮扫描卡死。
2. **`TVM_GETITEMRECT` 的返回是客户区坐标**，树还能横向滚动 → `left` 会小于 0（`--fit` 之后尤甚），它**不是视觉缩进**，别拿它当层级用。
3. **"可见行"要按 `pane_bounds = 客户区 ∩ 监视器` 判定**，不是按客户区：
   - 树下面有 21 px 横向滚动条（probe_geom2），点在最后一行上会把焦点丢给滚动条、什么都不选中；
   - 实测主窗口是 `(0,253)-(1938,1351)`（1080 高的屏），客户区底 1253 **在屏外 173 px**，`SetCursorPos` 会被钳到屏幕边缘 → 文档最后约 7 行**永远点不到**（hitcheck：`1.1.0`/`1.2.1` 打不中，它们以上全中）。
   - 唯一不依赖改尺寸的办法：`--fit` 先把窗口滑回屏内（`fit_on_screen`，结束时 `restore_rect` 还原）。`treectx` 和 `panels` 都支持 `--fit`。
   - 本机实测平移量：未拟合 `(0,253)` → 拟合 `(-26,-26)`，即**全部元素矩形 -26/-279**（`panels01` vs `panels02`，同一工程）。拟合后底边仍低 18px，但状态栏、输出/编译页签、错误网格、`筛选器` 都进了屏幕，够真点。**这个数只在本机这分辨率成立**，要坐标就同一轮里现读，别抄常数。
4. 顺带：`WindowFromPoint` 在这些坐标上常返回 **`XamlExplorerHostIslandWindow`**（WPF 岛窗）而不是树，别用它验证"这里是不是树"。验证只用"点完让树回读句柄"。

## 54. 树节点文字**能安全读**：`TVM_GETITEMW(0x113E)` + 远端 TVITEMW + 远端文本缓冲

长期结论"工程树读不到文字（`TVM_GETITEM` 会崩）"把两件事混成了一件。真正的边界是**结构体与缓冲区在哪个进程**，不是"能不能读文字"。

| 写法 | 结果 |
| --- | --- |
| `TVM_GETITEM`(0x110C, ANSI) + 本地 `TVITEMEXW` | **Sysmac 直接崩溃**（早期踩过，因此误判"文字不可读"） |
| `TVM_GETITEMW` (0x113E) + 本地结构（`pszText` 指着自己的进程） | 同样是跨进程写指针，**不要用** |
| `TVM_GETITEMW` (0x113E) + `TVITEMW` 与文本缓冲**都 `VirtualAllocEx` 到 Sysmac 里**，`WriteProcessMemory` 填参数 → 发消息 → `ReadProcessMemory` 读回 | **安全**。219 节点工程与 84 节点库工程各跑通一遍，一次没崩（2026-11-06 起在 `ss_uimap.py treelabels` 里） |

三个细节：

1. x64 的 `TVITEMW` 是 **56 字节**（`hItem`/`pszText` 8 对齐，ctypes 会自动插同一个填充）；分配远端缓冲要按这个尺寸。
2. `cChildren` 是 comctl32 **写回远端结构**的，所以必须把 `TVITEMW` 本身也读回来，本地那个 `t` 里永远是 0。
3. Sysmac 存的标题**尾部带空格补齐**（`'EtherCAT        '`），显示/比对前必须 `rstrip`，否则"看起来一样"的字符串相等判断全错。

> ⚠ 顺带一条：`0x110D` 是 **`TVM_SETITEMTEXTW`**（写文字），不是某个矩形消息的变体。别把 `0x1104`/`0x110C`/`0x110D` 互相"试一下"——前两个已实测会崩，第三个会改坏工程数据。

## 55. 弹层菜单**打不开子菜单**，且 `menuitems=` 计数会大于打印行数

Sysmac 的工程树右键菜单是 WinForms 弹层（稳定句柄，类 `WindowsForms10.Window.20808.app.0.*`），里面的 `MenuItemControl`：

- `GetExpandCollapsePattern()` 拿不到模式 → 程序化 `Expand()` 无效，`添加` / `在上方插入` 的**子菜单项列不出来**（要它们只能手工展开或 `ss_record.py` 录）。
- `menu_popups()` 报的 `menuitems=` 是在弹层根 8 层内数到的 `MenuItemControl` 总数，**包含尚未实化的子菜单项**；`map_popup()` 打印的是按"名称+状态"去重后的可见项。所以 `1.0.0.0` 会出现"计数 23 / 打印 16 行"。两个数都对，别拿计数当"漏采"。
- 弹层是**独立顶层 HWND**：必须在同一个进程里"右键 → 读 → Esc"，分两次调用它已经关了（与 §「一个动作序列要在同一个进程里跑完」同源）。

## 56. `TVM_SELECTITEM` 到底改变了什么（一条被写反了两次的结论）

同一件事在本 Skill 里出现过**三个互相矛盾的版本**：0.2.0 说消息定位万能 → 0.4.2 说"`TVM_SELECTITEM`/方向键都到不了这棵树，选中只能真实鼠标" → project-tree.md §3.1 又说消息可行。2026-11-06 用 `probe_select.py`（**只发消息，不点鼠标、不抢前台**）一次测清：

对 `0.0 EtherCAT`、`0.4.0 轴设置`、`1.0.2.3 FB_AxisAllow`、`1.0.0.0.0 PrgMain` 四个不同深度的节点，`TVM_SELECTITEM(TVGN_CARET, h)` 之后：

| 观测 | 结果 |
| --- | --- |
| `TVGN_CARET` 回读 == h | **4/4 是** |
| 目标行拿到 `TVIS_SELECTED(0x2)` | **4/4 是**（不是"只动光标不给选中态"） |
| 上一行被取消选中 | **4/4 是**（caret 就是选区，不是第二套状态） |
| 软件把该行滚进可见区 | **4/4 是** |
| 主窗口**最小化**时同样有效 | **是** |

所以正确答案是：**选中 = 消息就够**（`编辑>复制/粘贴/删除` 全可以在锁屏/最小化下做完）；**"打开页面" ≠ 选中**，那一步才必须真实单击 + 真实 `{ENTER}` 或双击未选中的行。0.4.2 的"到不了这棵树"是把这两件事合并了，属于**误判**，已修正 [control-tree.md §6](control-tree.md) 与 [project-tree.md §3.1](project-tree.md)。

`row_hit` 里"caret 单独不够，因为树没有键盘焦点时读回 0"的那句，说的是**另一种情形**：先用 `TVM_SELECTITEM(TVGN_CARET, 0)` **清空**光标、再用**真实点击**去选中——点击在没有焦点时只写 `TVIS_SELECTED`、不写 caret。自己用消息选中的话不存在这个问题。别把这两条混成"消息不可信"。

> 教训：这类"消息到不到得了"的结论**必须用只发消息的探针测**（不点鼠标、不抢前台），一旦掺进点击，就永远分不清是消息生效还是那一下点击生效。本条三次反转的根因就是这个。

## 57. 默认遍历会**裁掉 `off` 子树**——"这页是空的"是错觉

`ss_uimap.py` 的 `walk()` 默认（不带 `--all`）会剪掉 `IsOffscreen` 的元素**及其整棵子树**（为了不让几万行隐藏节点淹没落盘文件）。对**页签式**的编辑器这是陷阱：内容常挂在 `off` 的 `TabItem` 里面，剪完只剩一个空壳容器，看起来像"这页没控件"。

实测对照（同一页、同一秒级条件，只差一个 `--all`）：

| 页面 | 默认遍历 | `--all` |
| --- | --- | --- |
| `1.1.1 全局变量` | 5 行：`GlobalVariablesView` → `VariablesView` → `Tab id='VariableGroupTabControl'`（**到此为止**） | 52 行：`TabItem '全局'`（`off`）里面的 `组筛选器`、`ToggleGroupButton`、`GroupingSelectionComboBox`、`GlobalNamespaceGroupDataGrid`（8 列 + 每列左右 `PART_*HeaderGripper`）、空表占位 `Button '数据为空。点击此处添加项。'` 全在 |

所以规矩是：**看到"根容器在、子元素空或只有一层"，先加 `--all` 重采一遍再下结论**；写文档时把"要不要 `--all`"当成每页的属性记下来（§16 里已逐页标注）。反过来，读**在线/离线态、按钮灰不灰**这类判据时不能全放开——`StartPageView` 那套许可元素就是靠 `disabled+off` 才不会被误当成主页控件（[control-tree.md §3.2](control-tree.md)）。

## 58. 开页失败有两种，取证字段能分清；关页只能真点

**开页**（`ss_uimap.py open <路径>`）实测的通道顺序：`TVM_SELECTITEM` 选中 → **真实单击行**（把键盘焦点交给树）→ 真实 `VK_RETURN`；不开就 `TVM_SELECTITEM(TVGN_CARET, 0)` 取消选中 + **真双击**（双击已选中的行会掉进就地改名，见 §7）；再不开就打一行取证。取证怎么读：

```
## 0.4.0  轴设置  enter then dblclick did not open a document
   (tree focus=True, row hit by click=True/True, caret kept=True, rows 85->85,
    kids=0, new windows=[], ancestors: 0=expanded, 0.4=expanded)
```

- `tree focus=True` + `row hit by click=True/True` ⇒ **点确实落在那一行**（`WindowFromPoint` 回读句柄 == 树句柄，两次都成立）。
- `rows 85->85`（`TVM_GETCOUNT`）+ `kids=0` ⇒ 不是"点开页时顺手把树改了"。
- `new windows=[]`（弹层句柄差集，且只算宽度 > 0 的）⇒ **没弹对话框**，不是被模态框吃掉。
- 三条同时成立 ⇒ 结论是"**这类节点在没有对应实体时没有可打开的文档**"，不是定位 bug。本工程实测这 6 个：`0.4.0 轴设置`、`0.4.1 轴组设置`、`0.5 Cam数据设置`、`0.8 数据跟踪设置`、`1.2.0 PrimaryTask`、`1.2.1 TempCtrlTask`（明细见 control-tree.md §16.6）。**别再对着它们重试第二遍**，也不要据此说"这个软件打不开轴设置"——2026-10-31 那次是从**有轴实体**的工程打开的。

**关页**：`DocumentWindow` 里的 `Button id='closeButton'`（15×15）**拒绝 `InvokePattern.Invoke()`**，实测一律走"窗口置前台 + 按矩形真点"（日志里 `closed(click)` 就是这个含义）。关掉**没编辑过**的页：不弹保存框、不冒新顶层窗口；改过的页会弹保存确认，本轮没测那条路径。`open … --close` 或 `close auto <out> --all` 是收尾动作——留着的脏页会混进下一轮的 `panels`/`--fit` 采样（本轮实测把残留 3 页清成 `# after: []`）。

## 59. 轴页顶部那个 `输出设备1` 组合框**只显不写**（五种机制全试过）

2026-11-07，轴1 想把它从 `节点:39 设备B` 改绑到 `节点:20 设备A`。轴页顶部/`伺服驱动设置` 里那个 `输出设备1` `ComboBoxControl`：

| 试过的写法 | 结果 | 证据 |
| --- | --- | --- |
| UIA `Expand` + `Select` / 点行 | 界面文字变了 | — |
| 真鼠标点弹层里的行 | 界面文字变了 | 实测日志（不随 Skill 发布） |
| `HOME` + `N×VK_DOWN` + `Enter` | 界面文字变了 | 同上 |
| 关闭态 `40×{UP}` + `N×{DOWN}` + `Enter` | 界面文字变了 | 同上 |
| 切文档页签强制刷新后再读 | 文字回落到旧值 | 实测日志（不随 Skill 发布） |

**保存 + 读归档**（`NexAxisOutputDevice1` 仍是 `<旧 sha 前缀>` = 旧设备）证明上面五种**一个都没进模型**。判据只有两条：① 读文件；② 看该轴 PDO 表里 `设备` 下拉给了什么（§60 的过滤特性）。**永远不要把轴页上那个框的 `combo_selection()` 当绑定真值**，它会让你把后面的 PDO 步骤全白做一遍。

## 60. `轴设置表` 是 WinForms：UIA 看不见单元格，但格子里藏着真的 Win32 组合框

`轴设置` 右键 → `轴设置表(S)` 的页面根是 `CustomControl ClassName='AxisSettingTableView'`（`WindowsFormsHost` 宿主）。`ss_uimap.py scan/open --all` 在这里只能看到一个空 Custom——**单元格、行、列在 UIA 里不存在**，别再按 WPF 网格去找 `DataItem`。

可行的写法（本轮唯一成功的绑定通道）：按量出来的 cell 坐标**真点**一下 → `EnumChildWindows(主窗口)` 枚举类名含 `COMBOBOX` 且可见的子窗口（`WindowsForms10.COMBOBOX.app.0.*_r6_ad1`，矩形就是那个格子）→ `CB_GETCOUNT/CB_GETCURSEL/CB_GETLBTEXT` 读全 34 个从站与**模型真值** → 对该组合框逐次 `{UP}`/`{DOWN}`（关闭态方向键改选中会发 `CBN_SELCHANGE`，网格就是听这个）→ `{ENTER}` → 离开格子再点回来复读。

- **`CB_SETCURSEL` 不能用**：只动选中文字、**不发通知**，看起来改了、模型没改。
- `SendMessageW` 的原型会被 `import uiautomation` 改成 32 位 `LPARAM`（同 §33 的 `HTREEITEM` 坑），64 位下 `CB_GETLBTEXT` 传缓冲要 `ctypes.cast(buf, c_void_p)`，`restype` 自己设成 `c_ssize_t`。
- 这一手有概率把软件打出 §63 那个异常框。
- 坐标是"现读量出来"的：列宽 150 px、行距 25 px、首行 top=236（1920×1080 最大化实测基线，control-tree §17.1）。**照抄数字到别的分辨率必然点错格**，换环境先重测；要重测就用截图找线（`ss_axtable.py geom`），不要用肉眼对 Read 工具给的缩放图。

## 61. 换 `输出设备` 会把这个轴的 PDO 映射**全部清空**，所以顺序只能"先设备后过程数据"

实测：绑定改对之后，`轴基本设置` 详细设置里所有行的 `设备`/`过程数据` 都退回 `＜未分配＞`（`devprobe_a1.txt`）。两个推论：

1. **先绑设备，再写 PDO**；反过来做，写进去的映射会被绑定动作抹掉。
2. `设备` 列的写操作要**幂等**：当前值已经等于目标就跳过（`ss_axpdo.py apply` 打 `already`）。重复设一次 = 再清一次下游映射。

另外 `设备` 下拉是**按已绑定设备过滤**的（绑定对 → 只给 `节点:20 <型号>(<设备名>)` + `＜未分配＞`），这也解释了"轴页那个框看着能选、PDO 却写不进去"：两套控件读的根本不是同一个模型状态。

## 62. `过程数据` 下拉：一项是**一个位**，匹配只能 `startswith(key + '(')`

- 文本形态 `'<obj>h-<sub>.<bit>(<Receive|Transmit> PDO mapping <n>_<名>_<obj>_<sub>)'`，实测某伺服共 257 项（32 位的 `60FDh` 展开成 32 个位）。
- `'60FDh-00.1'` 是 `'60FDh-00.10'` 的**子串**，`in` 匹配会静默映射到错的位——**必须** `caption.startswith(key + '(')`（左括号把 `.` 的歧义封死）。
- 下拉**打开时定位到当前选中项**：还是 `＜未分配＞` 的行一打开就在列表**最底部**，所以"往上滚回去"这步不能省，扫描要**先上后下**（只向下扫的结果：`60FDh-00.1/.16/.17/.18/.25` 写成功，`.0`/`.2` 永远 `NO-PREFIX`，`pdoapp1c.txt`）。
- **滚轮点必须落在弹层自己的矩形中心**。点"组合框中心 + 偏移"时，弹层往上开或行靠屏幕下沿时，滚轮落到网格上，列表一动不动却看起来在滚（同一个 `首项/末项` 文字反复出现就是唯一线索，要做"卡住检测"）。
- 兜底（本轮真正解决 `.0`/`.2` 的那一手）：真点开下拉拿到键盘焦点后**把键名敲进去** —— WPF 组合框的文本检索会直接把高亮跳到 `60FDh-00.0(…`，再点它/`Enter` 提交（`pdoapp1e.txt`：`clicked 60FDh-00.0(…) (typed)`）。

## 63. 软件会自己弹 `Microsoft .NET Framework` 未处理异常框，它会**冻住后面所有 UIA**

2026-11-07 两次实测（`ss_axtable.py set` 方向键写 `输出设备1` 时、`ss_axpdo.py apply` 扫 `过程数据` 时）。表现：屏幕左边一个"Microsoft .NET Framework / 未将对象引用设置到对象的实例"小框，带 `继续(C)`/`详细信息(D)`/`关闭`；它一出现，**后续 UIA 调用不是报错而是长时间不返回**，脚本从 1 分钟变成 8 分钟。

处理规矩（`scripts/ss_crashdlg.py`）：先**只报告**（列顶层窗口 + 该框的按钮矩形），确认目标就是 `.NET`/`Framework` 那个框、并且**只有 `继续` 被点**；`详细信息`/`关闭` 永远不点（关闭会带走整个实例，`详细信息` 是未知路由且属许可/崩溃上报面）。实测点 `继续` 后实例活着，**已经写进去的值还在**（保存后读归档可证）。

顺带一条通用判据：**跑很久不结束先怀疑模态框，而不是怀疑算法**。用 `ss.py wins` 或 `crash_dlg` 看有没有第二个顶层窗口，比加日志快。

## 64. 虚拟化网格 / 下拉的三种"看着有、点不动"，和它们的正确读法

| 现象 | 机制 | 对策 |
| --- | --- | --- |
| 早先抓的 `DataGridRow`/`ComboBox` 回来时失效，写了没反应 | 滚动时 WPF 回收行元素 | **找一行、写一行、再找一行**，绝不缓存（`find_row`） |
| 组行折叠时子行根本不在树里 | 折叠 = 不实化 | 只点三个**组行**的 `toggleUnit`（子行的那个永远显示 `'+'`，点了也没用，实测每个点 6 次全无效） |
| 下拉项枚举得到但 `IsOffscreen=True`、矩形是过期坐标 | 弹层列表也只实化约 60 项 | **绝不点 offscreen 的行**（点了会命中当前画在那儿的另一项——这条曾经把 轴1 绑成 `节点:39` 上的错误设备，实测日志为证）；要它出现就滚动，或按 §62 敲键名 |
| `ListItem.GetSelectionItemPattern()` 返回 `None`；`GetScrollItemPattern` 直接 `AttributeError` | 这些行没实现相应 Pattern | `Select()` / `ScrollIntoView()` 两条"UIA 正规军"路线都**不存在**，只剩真点 + 滚动 + 键入 |

## 65. 两条"读文件才知道"的真相：编译不补 PDO 字段，折叠态会写进工程

1. **编译不会**把 `PDO<i>PDOPathName` / `PDO<i>ODBitLocation` 填出来（实测编译后仍为空）。想要"编一遍就自动映射好"是不存在的，界面写进去才算。
2. `NexAxisGeneralSetting/NexAxisPDOMappingTable` = `'output=True,input=True,digital input=True,'`。**2026-11-07 把它的语义测反了一次，这里是在场证据**：
   - 观测到的相关性：只有"**过程数据/设备单元格被界面提交过**"的轴带这串。本轮逐行写完 PDO 的 轴1/2/3/5 全冒出这串；只读不写的 轴4 保持空；源工程里带这串的是原作者手工改过的 轴4。
   - **它不随折叠/展开变化**：`ss_axpdo.py fold` 真点了三个组（`toggleUnit` 从 `'-'` 变 `'+'`，`expand` 反向也一样）→ `ss_save.py` 落盘（sha 变了）→ `ss_axcmp.py` 那串**一字未动**；再把该轴的编辑器页签关掉（`ss_uimap.py close`，实测 `closed(click)`）后保存，仍然不动。⇒ 保存**不会**按当前视图重算它，它也不是当前折叠态的快照。
   - ⇒ 结论：**只增不减的历史标记，界面上没有清除通道**。做"逐参数一模一样"时它属于"如实报告"那一类（和 §65.3 的灰置字段并列），**不要为了对齐反复点 toggle**——白跑，每轮还要几分钟。
   - 反过来说：`ss_axpdo.py expand` 之后保存会"多出"这串的说法**作废**（那是当时把"提交过 PDO 数据"误认成"展开过组"）。只读仍然用 `collect`，理由不变（不点 toggle、不碰视图）。
   2b. **这串是"点 toggle 的顺序记录"，不是集合**（同一份源工程里两种写法都出现过）：轴4 是 `output=True,input=True,digital input=True,`，轴27 是 `digital input=True,input=True,output=True,`——同样三个键、**顺序相反**。这条**仍然成立**（它记录的是提交顺序），只是既然 §65.2 判定它改不动，实际用途只剩"读源工程时别把两种写法当两种状态"。
3. 还有一类差异**界面上根本没有开关**：`IsEnabled=False` 的字段（轴0 的 `AxisType`/单位分子分母/最大速度/最大点动速度，以及每轴的 `NexAxisHoming/NexAxisStartDirection`）在**源和 Copy 两份文件里都是灰的**，改不动也不是漏做，明细见 [control-tree.md §17.4](control-tree.md#174-界面上灰掉因此抄不过来的轴参数2026-11-07-实测)——**遇到就如实报告，不要为了对齐去手改归档文件**（那属于 [offline-surgery.md](offline-surgery.md)，且违背"照着添加照着修改"的要求）。


## 66. 保存这一刀：`Ctrl+S` 会被残留弹层吃掉，菜单项名字带访问键后缀（2026-11-07 实测）

1. **判"保存成功"只看一件事：目标 `.smc2` 的 sha256 变了没有**。标题栏不加 `*`、状态栏不提示、界面全读完也对，`ss_save.py` 的 `#### SAVED (+1s)` 才是结论。
2. 表格里**没关掉的下拉**是一个独立顶层小窗（`HwndWrapper[SysmacStudio.exe;;<guid>]`，实测 93×31，`GWLP_EXSTYLE` 可见但 `Name`/`Title` 全空）。它会在主窗口拿到前台之后继续吃键盘：`force_foreground(主窗口)` + 真 `Ctrl+S` 按下去，文件纹丝不动（`save_final.txt`/`save_final2.txt` 两轮都是这个形状，四个轮询点都能看见这个小窗）。
   - 对策一：保存前 `U.esc(2)`（`ss_save.py --esc 2`，默认就带）；实测 Esc 能把这种弹层关掉，关不掉时它会一直在轮询里出现——**弹层还在 = 别指望键盘**。
   - 对策二（更稳）：**走菜单，不碰键盘**：`ss_save.py --menu` → `文件(F)` 用 `ExpandCollapse.Expand()` 打开，在弹层里按名字找 `保存`，`Click(simulateMove=False)` 点它。这条路实测 +1s 落盘。
3. **菜单项的 UIA `Name` 带访问键后缀**：实测弹层里是 `保存(S)`、`另存为(A)...`、`关闭(C)`、`退出(X)`，而 [control-tree.md §5](control-tree.md#5-工具栏33-个命令--6-条-toolbar) 记的是剥掉后缀的中文标题。所以 `ss.py menu_item(pid,'文件(F)','保存')` 这种精确匹配**必然 not found**（`save_final2.txt` 就是这么失败的）。`ss_save.py bare()` 用正则 `\s*[（(]\w[)）](\s*\.\.\.)?\s*$` 先剥再比；任何按名字点菜单的新脚本都要走同一套，或者干脆用 `ss_uimap.py menus` 先抓一次真实 `Name`。
4. 保存弹层**只记录不动手**：`ss_save.py` 的 `pop_lines()` 会把每个弹层的 Text/Button/Document/MenuItem/List 子节点文字写进日志，带 `许可/License/序列号/激活/Registration` 字样的窗口一律标 `<< 许可类，绝不操作`。

## 67. PDO 组的 `toggleUnit`：是 Button 不是 Text，第一遍读值会说谎（2026-11-07 实测）

四条串在一起的坑，每一条都能让"展开/折叠"变成**零点击的成功**：

1. **控件形状**（`ss_axpdo.py peek <pid> out.txt <轴路径>` 打出来的原文）：
   `DataItem cls='DataGridRow'` → `Custom cls='DataGridCell'` → **`Button id='toggleUnit'`（`PAT=Toggle`）** → `Text id='toggleButton' Name='+'|'-'`。
   老代码按"`AutomationId=='toggleUnit'` 的 **TextControl**"找，永远找不到 ⇒ `expand_all`/`collapse_all` 走"找不到就当已经到位"的捷径，日志写 `groups opened=[三组]`，实际**一次都没点**。 ⇒ 判"这组什么状态"要读**子 Text 的 Name**，判"有没有真点动"要看日志里有没有 `round N: ... -> '-'`。
2. **第一遍读值会反**：刚 `expand_groups()`/`raise_tab()` 完立刻扫，三组会全读成 `'-'`，2 秒后和最终复查都是 `'+'`（截图也是 `+`）。⇒ `stable_glyphs()`：连读两次一致才拿来做决定；点击之后也要再 `stable_glyphs()` 复查，不能信"点完立刻读"。
3. **PDO 表藏在第二层 Expander 后面**：`轴基本设置` 页里 `详细设置`（`Custom cls='MultiPDOTableFieldView'`）自己也是个折叠 Expander，它折着的时候整张 `DataGrid id='list'` 都不在树里。关掉一个编辑器页签再开，它会回到折叠态 ⇒ `page()` 必须先 `ss_axis.expand_groups(root)`，否则 `NO DATAGRID`（会被误读成"这轴没绑设备"）。
4. **文档已开着 ≠ 该页在前面**：`ss_uimap.py open` 对已开文档只做 Enter/双击，`axis_open.txt` 里 `enter then dblclick did not open a document` 之后，`page_root()` 命中测试读到的是**别的轴**的页面。⇒ `ss_axpdo.page()` 现在补 `ss_axis.raise_tab()`，并在动任何写操作前用 `verify_axis()` 核对页面上的 `轴号` 与路径里的轴号一致，不一致直接 `return 4` 停手（写错轴是静默破坏）。
5. 附带一条读值坑：`expand` 之后**立刻** `collect` 会把有值的行读成空（`x_a4h.txt` 里 `1. Controlword` 的设备/过程数据都是 `""`，同一时刻截图是 `节点:29 CH1 R88D-KN04H-ECT(...)` / `6040h-00.0(Controlword)`）。展开后要么等一轮，要么再 `collect` 一次；**"读回为空"不能当"没写进去"**，最终以 `ss_axcmp.py` 的归档为准。

## 68. ESI 库：只能单实例安装，对话框是独立顶层窗口（2026-11-08 实测）

1. 入口：EtherCAT 编辑器里选中**主设备**行 → 真实右键 → 菜单项名字是 **`显示ESI库`**（无空格、**没有**访问键后缀）。`ss_esi.py open` 用 `Name.replace(' ','') == '显示ESI库'` 匹配。
2. 弹出的是**独立顶层窗口**，标题 `ESI库`，`Custom cls='ProfileLibraryView'`，树 `TreeControl id='EsiProfileTreeView'`。按钮 id：`installFileButton` / `installFolderButton` / `unInstallButton` / `cancelButton`（关闭）。
3. **硬前置：本机只能有一个 Sysmac Studio**。多开时点「安装(文件)」会弹
   「安装未执行。因为正在运行多个Sysmac Studio，无法执行安装。请关闭其它Sysmac Studio，然后重试。」
   这个框 `Name='Sysmac Studio'`、`AutomationId='MessageBoxView'`（**ClassName 只是 `Window`**，按 ClassName 找永远找不到），正文是 ScrollViewer 里的只读 Edit，按钮是 ListBoxItem 包着的真 `ButtonControl`。`ss_esi.py msgbox` 读全文并只点指定按钮。
4. 文件对话框是 Win32 `#32770`：文件名框优先 `Edit id=1148`（`ValuePattern.SetValue` 能用；ComboBoxEx32 里那个 `ComboBox id=1148` 只是壳），打开按钮 `id=1`。
5. 装完别只看"对话框关了"：`ss_esi.py find <关键字>` 在 ESI 树里应该能找到型号。实测装汇川 SV660N 后关键字 `SV660` 命中 `InoSV660N Rev:0x00010000 | SV660N_1Axis_00916`。

## 69. 右击插入的三条语义：成对插入 / 头插 / 自动重排节点号（2026-11-08 实测）

这三条决定了"照抄一份组态"的计划表必须怎么写，任何一条搞错都会得到一棵"数量对、顺序错"的树：

1. **`GX-JC06(IN,X2,X3) Main device` 是成对插入**：一次插入同时生成
   `节点N : … Main device` 和它 `Internal Port` 下的 `节点N+1 : GX-JC06(X4,X5,X6) Sub-device`
   （默认名 `E001`/`E002`），`从设备数量` +2。**Sub 是自动生成的那一个**，不需要（也不能）单独插。
   - 刚插完 Main 行是**折叠态**，`Internal Port` 和 Sub 行都还没实例化 ——
     必须 `Expand(Main)` → 等 0.7 s → **重新取一次行**（控件会重建）→ `Expand(Internal Port)` → 再读子行。
     第一版脚本没做这一步，日志写 `main_subs=0`，误以为没插进去。
2. **插入落在所选端口的"头部"**：同一端口依次插 A、B、C，拓扑里是 C、B、A。
   ⇒ 菊花链按**链尾→链头**倒序写计划（源工程 X3 上是 `设备C`(7)、`设备A`(20)、`设备B`(29)，计划里就先插 29、再 20、再 7）。
3. **每次插入都会重排全网络节点号**：插到中间会把后面的整体顺移。
   ⇒ 插入阶段**不要写节点号**，拓扑建完再用 `ss_ecat_build.py renumber` 统一写一遍。

## 70. 拓扑行矩形是**整棵子树**的高度；父行文字会混进所有子孙（2026-11-08 实测）

1. `BoundingRectangle` 拿到的不是行高（约 38 px），而是**这一行 + 全部展开子孙**的总高：
   主设备行实测 `(275, 186, 902, 1950)`。所以 `center(行)` 会点到子行上（点错位置插到别的端口/别的从站）。
   ⇒ 点标题带：`x + min(300, max(60, w//3))`、`y + 18`。
2. `find_by_type(行, ('TextControl',))` 会把**所有子孙行的文字**都扫出来 ⇒
   `find_slave(t,'IO站123')` 会先命中祖先 `总站123`（它的拼接文字里含这个名字），
   于是改名/改节点号落在了**别人身上**（本轮真出过：把 `总站123` 的 Sub 改成了 `IO站456`）。
   ⇒ 行文字必须过滤：只保留**中心点不在任何子 TreeItem 矩形内**的 Text（`row_texts()`）。
   注意这条也有边界：子行**尚未实化**时没有矩形可排除，父行 label 里仍会混进子行文字
   （实测 `5 | 驱动器123 | … | 30 | 驱动器456 | …`）——只影响 label 展示，
   用 `no=`（行自己的 editBox）+ 精确前缀匹配即可。
3. 行内还有 `EditControl aid='editBox'`（节点号）和选中态；判"选中"用 `SelectionItemPattern.IsSelected`，不要看文字。

## 71. 工具箱搜索只匹配**设备名**；「工具箱 / 查找和替换」是同一组 `PaneControl` 页签（2026-11-08 实测）

1. 关键字框（`EditControl id='SearchTextBox'`）只能匹配**型号名**：
   - `GX-JC06(IN,X2,X3) Main device` → **0 条**；`GX-JC06` → 4 条（Main/Sub × GX-JC06/GX-JC06-H，均 Rev:1.1）
   - `CTEU-EtherCAT Modular` → 0 条；`CTEU` → 1 条
   - `NX-ECC203` → 1 条（Rev:1.7）；`SV660` → `InoSV660N Rev:0x00010000 | SV660N_1Axis_00916`
   ⇒ 计划表里 `kw` 写短型号，再用 `pick` 子串在结果行里挑（结果行文字形如
   `GX-JC06(IN,X2,X3) Main device Rev:1.1`）。
2. 右下角停靠区里 **`工具箱` 和 `查找和替换` 是两个 `PaneControl` 页签，不是 `TabItemControl`**。
   切到「查找和替换」时 `SearchTextBox` / `ItemListBox` 直接**从 UIA 里消失**（脚本报
   `SearchTextBox not found`，截图才发现页签换了）。`ensure_toolbox()` 的正确写法是按
   `('PaneControl','TabItemControl')` 两种类型找 `Name=='工具箱'` 再点。
3. 关键字框**读不回值**（`Value` 永远是 `''`），成功判据只能是结果列表 `ListControl id='ItemListBox'` 出现行。
4. `显示所有版本` 复选框（`CheckBoxControl`）：**关掉**时只列推荐版本。实测本机源工程用的
   `NX-ECC203` 就是 Rev:1.7、`R88D-KN04H-ECT` Rev:2.1，**关着就对**；开着会出现 1.3/1.1 等旧版，
   选错版装配对但归档型号不同。默认关。

## 72. EtherCAT 组态只在进程内存里：不落盘，进程一退出全没（2026-11-08 血的教训）

本轮 16 步建完、21 个从站、节点号也写对了，但**全程没保存**；之后 Sysmac Studio 进程消失，
`.smc2` 的 mtime 还停在开工之前、归档 `flat children of Proxy = 0` —— 整轮白做。
⇒ 批量脚本必须每步落盘：`ss_ecat_build.py ... --save-each`（每步成功后走 `文件(F) > 保存`）。
保存判据仍然只看 sha256 变没变（§66）；多实例同时打开同一工程会被锁（见 §68.3 的兄弟现象：
第二个实例报「无法打开工程文件。该文件可能被该应用程序的另一个实例锁定。」）。

## 73. 拓扑树按视口实化：从树根 `walk()` 会整段缺行（2026-11-08 实测）

树高实测 1950 px、视口约 700 px。`ss_ectree.py dump` 从树根递归 `GetChildren()`，
只会拿到**当前视口附近已实化**的行：同一棵树在源实例拿到 51 行（完整），
在目标实例只拿到 33 行，某分支 7 个从站整段消失（内置 `ss_ecat_archive.py cmp` 因此报 7 个 MISSING）。
这些行**确实存在**（插入日志、`从设备数量=21`、renumber 读回、归档都对），纯粹是视图覆盖问题。

⇒ 要核**结构**就从目标行往下取：先找到那行 → `ScrollItemPattern.ScrollIntoView()` →
`ExpandCollapsePattern.Expand()` 逐层展开 → 再从**这一行** `walk()`
（内置 `ss_ectree.py subtree`）。要核**整份组态**就别跟视图较劲，直接读归档（recipes §O.6）。

## 74. Git Bash 改写 `tasklist` 的斜杠参数 → 误判"进程没了 / 组态丢了"（2026-11-08 实测）

1. `tasklist /FI "IMAGENAME eq SysmacStudio.exe" /FO CSV /NH` 在 Git Bash 里会被 MSYS 路径重写成
   `/FI` → `C:/Program Files/Git/FI`，命令直接报错/无输出，**看起来像没有任何 SysmacStudio 进程**。
   那一轮因此得出"进程被杀了、16 步全丢"的错误结论，还差点重做整份组态（实际进程一直活着，
   只是没保存，见 §72 —— 两件事叠在一起才像"丢了"）。
   ⇒ Git Bash 里用 `//FI //FO //NH`；或干脆走 PowerShell `Get-Process SysmacStudio`。
2. 判"进程在不在"只看 `tasklist` 一处证据不够，要和**窗口**对一下：UIA 里能拿到主窗口句柄
   + 标题里带工程名，才说明实例真的在跑。
3. 同一份 `.smc2` 不能被两个实例同时打开：第二个实例弹「无法打开工程文件。该文件可能被该应用程序的
   另一个实例锁定。」（`#32770` / 消息框）。要换实例必须先关掉前一个（先保存！），
   不要用 `taskkill /F /IM SysmacStudio.exe` 一把梭（会把未保存编辑一起杀掉，外部一次性开工程脚本就是为避开它写的）。
