# 架构与运行前提

本文件回答三件事：这个软件是什么形态、为什么必须提权、控制进程应该怎么摆。

## 1. 软件形态（决定能用哪些手段）

| 事实 | 依据 |
| --- | --- |
| .NET Framework **WPF** 桌面程序 | 主窗口类名 `HwndWrapper[SysmacStudio.exe;;<guid>]`；伴随隐藏窗口 `SystemResourceNotifyWindow`、`MediaContextNotificationWindow`、`.NET-BroadcastEventWindow.*` |
| 主窗口 **没有子 HWND** | `EnumChildWindows` 返回空 ⇒ 控件全在 UIA 树里，Win32 层点不到 |
| UI 控件栈 | Actipro（Docking / Ribbon / SyntaxEditor / PropertyGrid）+ Xceed.Wpf + **Northwoods.GoWPF**（梯形图/功能块画布）+ SharpDX Direct2D/D3D11 + WebView2 |
| 工程树是 **WinForms 宿主** | `WindowsFormsHost` → `GDISolutionView` → `WindowsForms10.SysTreeView32.app.0.*`（托管 TreeView 子类；这是"读不到节点文字"的根因） |
| WPF 自带 UIA Provider | 菜单/工具栏/停靠面板/对话框默认就能读、能操作，不需要任何开关 |
| 可选 WebView2 | 部分内容（如更新信息、联机帮助）走浏览器内核，UIA 下可能是一整块 |

**推论**：能操作的就是 WPF 那一套（标准 UIA Pattern），画布类内容（梯形图/功能块图）基本是"一块画布"，不要指望逐元件读写（见 [pitfalls.md](pitfalls.md#8-gowpf-画布只有一块)）。

## 2. 为什么必须提权（UIPI）

Sysmac Studio 的 manifest 要求管理员权限，安装后**总是以 High IL 运行**。Windows 的 UIPI 规则：较低完整性级别的进程**不能**读取或操作较高完整性进程的 UI。

实测对照（同一台机器）：

| 控制进程 | 看到的 Sysmac 窗口 | UIA 树 |
| --- | --- | --- |
| 普通权限（Medium IL） | `EnumWindows` 能拿到 HWND / 标题 / 矩形 | 只有 1 个客户端自己合成的 `TitleBarControl`，**0 个真实子节点**；有的 UIA MCP 甚至直接不返回这个窗口 |
| 管理员（High IL） | 同左 | 完整 WPF 树（启动页 ~55 节点 / 新建工程向导 ~104 / 工作区 ~448） |

旁证：普通权限 `OpenProcess(<SysmacStudio pid>, PROCESS_QUERY_LIMITED_INFORMATION)` 返回 `err=5`。

**结论**：任何"读 UIA 树 / 点控件"的动作都必须在提权进程里跑。只读窗口参数（HWND/PID/标题/矩形/`IsIconic`）不需要提权。

## 3. DPI 感知（坐标偏移的唯一原因）

在 DPI 缩放下，非 DPI 感知进程拿到的是**虚拟化矩形**，UIA/DPI 感知进程拿到的是**物理像素**。125% 缩放下两者差 1.25 倍，两套坐标混用必然点错。

每个控制进程在 `import uiautomation` **之前**执行：

```python
import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)   # 2 = PER_MONITOR_DPI_AWARE
except Exception:
    pass
```

`scripts/ss.py` / `scripts/ss_tree.py` 已经内置。**同理：看到 `GetWindowRect` 比 UIA 矩形小一圈，就是这个进程没设 DPI 感知。**

## 4. 会话与前台（锁屏会改变一切）

| 场景 | UIA 读树 | UIA Invoke（按钮/菜单项） | 坐标鼠标 | 键盘 `SendKeys` | 截图 |
| --- | --- | --- | --- | --- | --- |
| 已登录、桌面已解锁 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 已登录、但工作站锁定 | ✅ | ✅ | ❌ 无前台窗口，点击落在未知位置 | ❌ | ❌ 黑图/桌面图 |
| RDP 断开会话 | ✅ | ✅ | ❌ | ❌ | ❌ |

判据：`GetForegroundWindow()` 返回 **0** 就说明没有前台输入桌面（实测），此时 **禁止发坐标点击**，改用 `TVM_*` 消息、UIA `Invoke()`、`menu`（UIA 点菜单项）这些不依赖前台的方式。

> 实测补充（2026-10-30）：工程树的**定位**完全不依赖前台——`TVM_SELECTITEM(TVGN_CARET)` 直接移动光标并用 `TVM_GETNEXTITEM(TVGN_CARET)` 回读校验，任意深度都成立。只有"点菜单"（`编辑>复制`）需要前台，因为主菜单是真实弹出窗口。

`SetForegroundWindow` 对高权限窗口常被系统拒绝（返回成功但没生效）。可靠组合：

```python
# 1) 先按一次 Alt（伪造用户输入，解除前台锁定限制）
keybd_event(VK_MENU, 0, 0, 0); keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
# 2) 与目标线程、当前前台线程 AttachThreadInput
# 3) SetForegroundWindow(目标)
```

实现见 `scripts/ss.py` 的 `force_foreground()`。

## 5. 三条接入路径

### 5.1 推荐形态：常驻高权限解释器

一次 UAC，之后所有命令从一个已经提权的解释器里发出，避免反复弹框，也避免"一次点击要开一个进程"。

文件协议（任意目录，进程间用文件通信即可）：

```
job.in    一行命令（shlex 语法），写完由守护进程取走
job.log   追加 stdout/stderr
job.done  已完成命令 + 退出码
job.stop  出现即退出
```

守护进程骨架（**只做参考，不随 Skill 分发**）：

```python
# 以管理员启动：Start-Process python.exe -Verb RunAs -ArgumentList "<path>\daemon.py"
import os, shlex, subprocess, sys, time
D = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
while not os.path.exists(os.path.join(D, 'job.stop')):
    p = os.path.join(D, 'job.in')
    if os.path.exists(p):
        cmd = open(p, encoding='utf-8').read().strip()
        os.remove(p)
        if cmd:
            argv = shlex.split(cmd)
            r = subprocess.run([PY, os.path.join(D, argv[0])] + argv[1:], cwd=D,
                               capture_output=True, text=True, encoding='utf-8', timeout=900)
            open(os.path.join(D, 'job.log'), 'a', encoding='utf-8').write(r.stdout + r.stderr)
            open(os.path.join(D, 'job.done'), 'w', encoding='utf-8').write(cmd)
    time.sleep(0.4)
```

两个实测坑：

- **投递命令的第一个 token 是脚本名**，解释器由守护进程补上；写成 `python ss.py wins` 会报"找不到名为 python 的文件"。
- **带空格的路径参数要在命令串里再套一层引号**：`ss.py dump <pid> "out/my tree.txt"`。漏引号时后半段会被当成别的参数，甚至凭空造出一个文件。

### 5.2 单次 UAC

一条命令一次提权（`Start-Process -Verb RunAs`），简单但慢，且**每条命令是独立进程**——弹出菜单/对话框会在两条命令之间消失。只适合"一次跑完的 `flow` 序列"。

### 5.3 UIA MCP over HTTP

若已有 `uiautomation-mcp` 之类的服务，把它的 stdio 模式套一个**本地 HTTP 壳**并以管理员启动（如 `127.0.0.1:8765/mcp`）。UIPI 只管进程完整性，不管 socket，普通权限客户端能正常连高权限服务。

注意这类 MCP 的通用毛病：每次 `list_windows` 会清空内部 element 缓存 ⇒ **之前拿到的 elementId 失效**，必须重新 `inspect`；返回的 `processName` 字段可能填的是 ClassName，且不返回 PID（多实例时无法分辨）。

## 6. 多实例（务必区分）

同一台机器可以同时开若干 Sysmac 实例（实测两个），它们的**主窗口位置几乎完全重合**，截图和坐标点击都会命中"最上面那个"，而不是你以为的那个。

- 用 `scripts/ss.py wins` 按标题区分（标题形如 `<工程名> - <控制器名> - Sysmac Studio (64bit)`）。
- 所有脚本都显式收 pid，`auto` 只挑面积最大的可见主窗口——**多实例时不要用 auto**。
- 需要把窗口分开时，调整窗口位置（`SetWindowPos`）或用虚拟桌面；不要靠"我以为前台是它"。

## 7. 输入方式的可靠度排序

1. **UIA Pattern**（`InvokePattern.Invoke()` / `SelectionItemPattern.Select()` / `ValuePattern.SetValue()`）：最稳，不需要前台，不会被遮挡。
2. **原生控件消息**（`TVM_SELECTITEM` 定位 / `TVM_GETNEXTITEM` 读结构 / `TVM_GETITEMW` 读节点文字 / `TVM_EXPAND` 展开根节点）：稳定，不需要前台，锁屏可用；但只能用在 WinForms 树这类原生控件上，且**只发安全消息**——读文字必须是 `TVM_GETITEMW(0x113E)` 且 `TVITEMW` 与文本缓冲**都在目标进程里**，ANSI 变体 `0x110C` 或本地指针跨进程会**把软件打崩**（[pitfalls.md §54](pitfalls.md)）。
3. **键盘**（真实按键注入）：需要前台与焦点；**实测不适合在工程树里"导航"**（`SetFocus` 抢不到、`{DOWN}` 会钻进子节点、折叠行上 `{LEFT}` 语义不同）。但两类动作实测只有它行：**展开非根节点**（caret + `VK_RIGHT`）与**弹出节点菜单**（`VK_APPS`）——见 [project-tree.md §3.2](project-tree.md)。对话框/文本输入也走它（但 ASCII 会被输入法吞，见 §31）。
4. **坐标鼠标**：最后手段。依赖前台、依赖 DPI 感知、依赖窗口位置，且会被遮挡/锁屏破坏。

## 8. `uiautomation`（Python 包）的 API 缺口

`uiautomation 2.0.x` 实测缺这些，别硬找：

- 没有 `GetDescendants()` —— 自己递归 `GetChildren()`。
- `WindowControl` 没有 `SetForeground()`。
- 没有 `GetSupportedPatterns()` —— 用 `GetPatternAs(auto.LegacyIAccessiblePattern)` 探测；`GetLegacyIAccessiblePattern()` **不接受** `createNew` 参数。
- `ControlFromHandle(hwnd)` 比 `WindowControl(ProcessName=...)` 可靠（后者会误匹配到别的进程窗口）。
- 默认全局搜索超时很松，显式设：`auto.SetGlobalSearchTimeout(10)`。
- **`import uiautomation` 会重声明部分 Win32 原型**，把 `SendMessageW` 的返回值/参数变成 32 位，导致 64 位句柄被截断（表现为"子节点数恒为 1"或句柄变负数）。发原生消息前必须恢复（见 [project-tree.md](project-tree.md#2-原生消息与句柄截断)）。
