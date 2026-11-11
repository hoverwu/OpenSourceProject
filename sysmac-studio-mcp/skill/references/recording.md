# 录制手工操作 → JSON（`scripts/ss_record.py`）

用途：当界面路径"知道该做什么、但脚本做不出来"时（EtherCAT 拖拽/插入、某些右键菜单、
向导里的特殊交互），让人**手工做一遍**，录制器把每一步落到可回放的 JSON，再据此写固定流程。

比截图识别可靠：每个点击都在**鼠标按下前**解析出 UIA 元素（控件类型 / 名称 / AutomationId /
祖先链 / 行内文本），键盘和剪贴板单独记录，弹窗出现时还会抓一份控件树。

## 1. 运行

必须**提权**：Sysmac Studio 以 High 完整性运行，中权限进程既看不到它的控件，也收不到焦点事件。

```bash
python ss_record.py --out recordings      # 提权终端里运行
```

停止：`Ctrl+Alt+F12`，或直接关掉控制台。`.jsonl` 是逐行落盘的，硬关也不丢；`.json`（含
meta / actions 汇总）在正常停止时写。

参数：

| 参数 | 说明 |
| --- | --- |
| `--out DIR` | 输出目录（默认 `./recordings`） |
| `--pid N` | 只录指定实例；同机多开时必须给 |
| `--all` | 录所有应用（默认只录发往 Sysmac Studio 的事件） |
| `--note TEXT` | 写进 meta，例如“EtherCAT 第2个从站插入” |
| `--seconds N` | 自测用：N 秒后自动停止 |

推荐用法：先启动录制器，再切到 Sysmac 操作；录完先在 JSON 里核对步数，再生成脚本。

## 1.1 架构铁律：钩子里只准入队（v0.2.0 起）

> 低级钩子回调（WH_MOUSE_LL / WH_KEYBOARD_LL）**绝对不能**调用 UI Automation、读剪贴板、
> 写盘或 `print`。

v0.1 在钩子里直接做 `ControlFromPoint` + 写盘 + 打印，结果：按下 Win 键（弹出开始菜单）
后整个控制台永久卡死。机制是：低级钩子由系统在**安装钩子的线程**里回调，而那次 UIA 跨进程
调用会等目标 UI 线程；目标线程此时正等着钩子返回 → 两边互等，输入队列整条停摆。
Sysmac 的 UIA 调用本来就慢（几百毫秒到秒级），钩子回调里做任何一件这样的事都会拖死输入。

v0.2.0 的分工：

| 线程 | 职责 |
| --- | --- |
| 主线程 | `SetWindowsHookEx` 安装钩子 + `GetMessageW` 消息泵。钩子回调只做 `queue.put(原始数据)` 和 `CallNextHookEx` |
| worker 线程 | 消费队列：`ControlFromPoint` 解析元素、读剪贴板、回读 ValuePattern、写 `.jsonl`、打印；每 0.1 s 顺带刷新前台 pid 缓存、每 0.4 s 轮询窗口/焦点 |

由此带来两个硬约束：

- 键盘过滤（"只录 Sysmac"）在钩子里只读 `self.fg_pid` 这个**整数缓存**（worker 每 0.1 s 更新，
  只调 `GetForegroundWindow` + `GetWindowThreadProcessId`），钩子里不查窗口标题、不做跨进程读。
- 停止靠 `PostThreadMessageW(WM_QUIT)` 打断消息泵，再 `_unhook()` → `worker.join(4)` → `finish()`；
  关控制台走 `SetConsoleCtrlHandler`，留 4 s 给 worker 写完 `.json`。

自测方式（不改动别人窗口）：`ss_record.py --all --seconds 8` 起一个，再从另一个进程
`keybd_event` 打几个字母，看 `.jsonl` 里有没有 `text`；鼠标钩子用 `SendInput` 的
`MOUSEEVENTF_MOVE` 验证（`SetCursorPos` 不会触发低级鼠标钩子，别拿它验）。


## 2. 记录什么

| kind | 内容 |
| --- | --- |
| `click` / `doubleclick` / `rightclick` | 按钮、坐标、按下时刻的元素快照（`el`）、持续毫秒 |
| `drag` | `from` / `to` 两个元素快照、`dx`/`dy`、时长。**记录的是输入，不代表应用真的接受了拖放** |
| `wheel` | 坐标、delta、元素 |
| `text` | 连续键入的字符（在 Enter/Tab/Esc/点击/失焦时冲刷成一条） |
| `paste` | `Ctrl+V` 时的剪贴板文本（脚本回放时用这种方式写中文/长文本） |
| `shortcut` | `Ctrl+A/C/X/Z/Y/S/F/...` |
| `key` | `Enter` / `Tab` / `Escape` / `Backspace` / `Left` / `Right` / `Up` / `Down` / `Delete` 等 |
| `ime_key` | 输入法吃掉的按键（拿不到组成的字符） |
| `value` | Enter/Tab/点击后**回读焦点编辑框的值**——中文输入法的最终文本靠这条恢复 |
| `focus` | 焦点控件切换（编辑框/树行的身份） |
| `window_open` / `window_close` | 每个顶层窗口出现/消失，`tree` 是深度 5、最多 400 个控件的树快照 |
| `activate` | 前台切进/切出 Sysmac |

元素快照：

```json
"el": {
  "path": [
    {"ctl": "WindowControl", "name": "Sysmac Studio (64bit)", "aid": "MainWindow", "cls": "Window", "rect": [0,100,1938,1098]},
    {"ctl": "CustomControl", "name": "", "aid": "", "cls": "", "rect": [9,138,1920,1051]},
    {"ctl": "TreeItemControl", "name": "", "aid": "", "cls": "", "rect": [400,300,500,326]}
  ],
  "texts": ["节点1 : GX-JC06(IN,X2,X3) Main device (E001)", "1"],
  "value": ""
}
```

`path` 是根→叶；`texts` 是该行直接子节点的 Text（表格行/树行靠它认值）；`value` 只对支持
ValuePattern 的控件有值。

## 3. `actions`：给脚本用的汇总

`events` 是原始流水，`actions` 已按"一次点击 + 其后的输入"合并：

```json
{"i": 8400, "kind": "click", "target": "TreeItemControl '节点1 …'",
 "point": [612, 388], "inputs": [{"kind": "key", "name": "Right"}],
 "windows": [], "el": {…}}
```

生成脚本时的映射：

| JSON | 脚本动作 |
| --- | --- |
| `click` + `el.path[-1].aid` | 优先按 AutomationId 找，其次 Name，最后坐标 |
| `click` + `texts` | 树行/表格行按"行内文本包含"定位，比坐标稳 |
| `inputs` 里的 `text` | `set_edit`（ValuePattern → 点击 + Ctrl+A + 剪贴板粘贴 + 读回） |
| `inputs` 里的 `key: Right` | 树节点展开：选中行后发 `VK_RIGHT` |
| `inputs` 里的 `paste` | 直接粘贴该文本 |
| `windows` 里的标题 | 下一步要在哪个对话框里操作；到 `window_open.tree` 里找字段 id |
| `drag` | `drag(from_x, from_y, to_x, to_y)`，注意源工程的拖放可能被忽略，优先找右键「插入」 |
| `value` | 用来核对输入是否真的提交（回放时也读回比对） |

## 4. 限制

- **只记录输入，不记录结果**。拖拽事件成功送达 ≠ 应用接受了拖放；判断结果仍要读控件树或导出文件。
- 中文输入法的组合过程不可见，靠 `value` 回读恢复；若编辑框不支持 ValuePattern，只能看到 `ime_key`。
- `RuntimeId` 每次启动都变，不要存；用 aid/name/rect。
- 坐标是**物理像素**（脚本已设 per-monitor DPI aware）。换缩放比例要重新录或换算。
- 录制器自身占用 `Ctrl+Alt+F12`；与其它全局热键冲突时改常量 `STOP_HOTKEY_VK`。
- 菜单、下拉、右键菜单都是**独立顶层窗口**：点菜单项的 `el.path` 里能看到完整祖先，
  但菜单消失后这些句柄不能再用，回放必须重新点开。
- 中权限运行录不到 High 的 Sysmac：日志里只有 `activate`，没有 `click`——先提权。
  同理，中权限进程 `SendInput`/`keybd_event` 打向 High 窗口的输入会被 UIPI 丢掉，
  这段输入在钩子里也可能根本不出现；**自动注入测试只用中权限目标窗口做**。
- 长时间录制会积累大量 `focus`/`activate`；生成脚本时以 `actions` 为主，`events` 用于核对。
