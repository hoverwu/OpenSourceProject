# 操作配方（端到端）

每条都标了 **[实测]** 或 **[未验证]**。未验证的只当思路，用前先补测。

---

## A. 新建工程

**[实测]**

```
1. ss.py clicks NewProjectToggle            # 启动页（若已打开工程：文件>新建）
2. 等 400~800ms，dump 出 NewSolutionControl 的树，确认向导已出现
3. 填工程名：找到 ProjectNameLabel 右侧同高的第一个 Edit，SetValue / 点进去 SendKeys
4. 填作者、注释（同理，分别对着 AuthorLabel / CommentLabel）
5. 选类型：ProjectTypeLabel 右侧的 ComboBox → 下拉是新窗口 → 点 ListItem
6. 设备三件套：CategoryLabel 右侧 ComboBox（类型）→ 两级型号 ComboBox → VersionLabel 右侧 ComboBox
7. 点 CreateButton（Name=创建(_C)）
8. 轮询 StatusBar 的 ProgressBar 到 0×0，再轮询主窗口标题
```

成功判据：`ss.py state <pid>` → `project=<名字>`、`controller=<型号>`、`mode=Offline`、`editor=0`。

坑：向导输入框**大多没有 AutomationId**，只能靠 label 相对位置；`SetValue` 失败时改 `Click` + `SendKeys`（`SendKeys` 里 `^a` 是全选，不是 `Ctrl+A` 文本）。

---

## B. 读状态与分辨实例

**[实测]** 全是只读，安全：

```bash
ss.py wins                # pid / hwnd / 标题 / 矩形 / 可见 / 最小化
ss.py state <pid|auto>    # 工程名 / 控制器名 / 模式 / 编辑器数 / 是否忙
```

- 标题 `工程 - 控制器 - Sysmac Studio (64bit)` → 用 `" - "` 切分前两段。
- 在线/离线：`MainDockSite` 的 **Name**（`Online` / `Offline`）。
- 有没有编辑器打开：`TabbedMdiContainer-*` 的子节点数。
- 是否忙：`StatusBar` 里 `ProgressBar` 的矩形非 0×0。
- **多实例**：标题可能完全相同（同一工程开两次），此时按 pid + 窗口矩形区分；`auto` 会挑面积最大的那个，多实例时不要用。

---

## C. 打开已有工程

**[实测]** 两条路：

1. 启动页 `OpenProjectToggle` → 原生打开对话框 → 输入 `.smc2` 路径 → `打开(O)`；
2. `文件(F) > 导入(I)...` （会把文件当"整工程"建出来，见 [project-files.md](project-files.md#2-导入整工程导入会先关闭当前工程)）。

差别：打开 = 直接绑到该文件；导入 = 复制成新工程并加序号。**要改文件就用"打开"，要复制就用"导入"。**

等待：大工程（几千实体）打开要十几秒到几分钟，轮询 ProgressBar + 标题，不要 `sleep` 死等。

---

## D. 批量搬运 POU

**[实测]** 三个层级，按规模选：

### D1 单个实体（跨实例也行）

```bash
ss_tree.py goto   <src_pid> 1.0.2.0        # 源：功能块下的第 1 个 FB（光标定位，回读校验）
ss_tree.py copy   <src_pid> 1.0.2.0        # 内部 = 定位 + 抢前台 + 编辑>复制
ss_clip.py list                            # 确认剪贴板出现 Omron.SolutionEntityClipboardFormatter
                                           #   实测单个 FB ≈ 10,376 B
ss_tree.py goto   <dst_pid> 1.0.2.0
ss_tree.py paste  <dst_pid> 1.0.2 --yes    # 粘贴到容器；自动应答覆盖/冲突
ss_tree.py count  <dst_pid> 1.0.2          # 校验子节点数 +1
```

剪贴板是**系统级**的，所以跨实例天然可行。

### D2 批量（推荐）

```
右键 POUs → 选择并复制多个项目 → MultiplePousCopyDialog 勾 POUs 行（=全选）→ 复制
目标端 右键 POUs → 粘贴多个项目 → 冲突选"否"保留两者 / "是"覆盖
```

细节见 [project-tree.md](project-tree.md#6-多选复制批量搬-pou的主路径)。

### D3 整工程

`文件>导入` + `另存为`（见 [project-files.md](project-files.md#7-完整搬运流程把一个工程复制成另一个工程)）。

**搬运前检查清单**

1. 源工程和目标工程的数据结构版本兼容（同版本软件最稳）；
2. 目标工程里没有同名 POU，或者你清楚冲突语义（是=覆盖 / 否=保留两者）；
3. 搬完用 `ss_tree.py count <pid> 1.0` 对比子节点数；
4. 大工程搬完 `文件>保存` **立刻落盘**（否则后续任何"导入"都可能把它清空）。

---

## E. 组态入口

**[部分实测]**：`插入` 菜单项已全部枚举；具体对话框内容**未逐项验证**。

组态对象都从 `插入(I)` 菜单进（选中工程树里的目标位置后再点）：

| 菜单项 | 对应组态 |
| --- | --- |
| `控制器(C)` | 添加控制器（CPU 机架） |
| `安全网络控制器(O)` | 安全控制器 |
| `驱动器(D)` | 伺服驱动器（NX 系列等） |
| `HMI(H)` | 触摸屏 |
| `测量传感器(E)` / `视觉传感器(V)` | 传感器设备 |
| `从设备终端(S)` | EtherCAT 从站 |
| `回路(R)` | 回路（Loop） |
| `应用管理器` | 应用（Application）容器 |
| `轴设置(A)` / `轴组设置(G)` | 单轴 / 轴组（运动控制） |
| `CNC设置(E)` | CNC |
| `机械手控制设置(L)` | 机器人 |
| `CAM数据设置(M)` | 凸轮数据 |
| `数据跟踪(T)` | 数据跟踪 |
| `DB连接设置(N)` | 数据库连接 |
| `程序(P)` / `功能(F)` / `功能块(B)` | POU |
| `导出设备` | 导出设备定义 |

**通用套路**（在任意 `插入` 项上类推）：

```
1. ss_tree.py select <pid> <目标父节点路径>
2. ss.py menu <pid> 插入(I) <菜单项名>        # 弹窗自动处理
3. 等 600~1500ms，ss.py popups <pid> 5        # 看新出现的对话框结构
4. 按 AutomationId / Name 填字段，最后点"确定"
5. 回树 count 校验新增了节点；若失败，dump 对话框树记录到 extending.md
```

⚠ `EtherCAT` 节点**双击不是展开而是打开其编辑器**——需要进网络设置就用双击/回车，需要展开子节点则做不到（见 [project-tree.md](project-tree.md#3-定位与展开实测边界)）。

---

## F. 写程序

**[实测·离线路线]**（2026-11-06）见 [offline-surgery.md §8](offline-surgery.md#8-从零新建-poust-功能块--程序--任务--实测可行2026-11-06-修订)：
向库工程注入 2 个 ST 功能块 + 1 个程序 + 1 个 200 ms 任务后，`编译控制器` 0 错误 0 警告。
生成器与坑位都以那一节为准，下面只列"写 ST 时最容易踩的四条"：

- `END_IF`/`END_FOR`/`END_CASE`/`END_WHILE`/`END_REPEAT` 后面**必须带 `;`**；
- 不支持嵌套 `MIN(MAX(a,b),c)`（报 `无效的输入参数组合`），限幅写显式 `IF`；
- `VAR_INPUT` 在 FB 内只读，要限幅就先拷到局部变量；
- `LREAL` → `REAL` 不隐式转换（报 `无法将LREAL转换为REAL`），写 `LREAL_TO_REAL(…)`。

**[实测·关键结构]** 程序的 subtype 是 `MultipartLadder`，程序变量表是 `Variables / Ladder`，
ST 代码放进段里的 `IST` 内联块（梯图 JSON）。写成 `Program / StructuredText` 会让整张程序
变量表不被识别——**能打开、能编译，但程序里所有变量报未定义**。详见 [offline-surgery.md §8.1/§8.4](offline-surgery.md#81-实体骨架)。

**[实测·界面路线]** 工程树里 `编辑>粘贴` 能带进已有 POU（含程序体）；打开编辑器用
选中节点后 `插入` 菜单 / 右键上下文菜单 / `单击` + `{ENTER}`，**不要双击**（双击会进就地重命名）。
`TabbedMdiContainer` 里每个 `TabItem` 的 Name 就是打开的对象名，可确认编辑器是否真的打开。

---

## G. 编译 / 构建

**[实测]**

```bash
ss_build.py run <pid> build_all.txt     # 点 编译控制器(B) → 轮询到头 → 全量导出错误
ss_build.py totals <pid>                # 只读面板："errors=385 warnings=0"
ss_build.py list <pid> build_all.txt    # 只读列表
```

- 按钮：工具栏 `ButtonControl`，`Name` 为空，靠 `HelpText` 含 `编译控制器` 匹配；
- 结束判据：面板顶部 `N 错误` 数字**连续两次 5s 轮询不变**（比状态栏进度条稳）；
- 列表：`DataGridControl`（`top > 630`）→ `ScrollPattern` 逐屏收 → **写 UTF-8 文件**；细节与坑见 [pitfalls.md §26](pitfalls.md#26-编译错误列表几何定位--滚动--utf-8)；
- 常见错误类别的判读：`地址不合法。` ⇒ 设备/轴组态缺失（重建工程的必然结果）；`该名称已用于数据类型 X。` ⇒ 结构体重名或被引用库里有同名类型；`未定义的标识符 'FC_xxx'` ⇒ 被编辑保护的 POU 没搬过来；`无法将LREAL转换为REAL` ⇒ 显式 `LREAL_TO_REAL(…)`。

**"0 错误"不能只看错误网格**（2026-11-06 实测被坑）：编译没真跑起来时，网格可以是 0 行、
旧行也可能是上一次的残留。判定通过的三个条件必须同时满足：① 编译后 CPU 时间明显增长；
② 面板能读到 `N 错误 / M 警告`；③ `%APPDATA%\OMRON\CXAP\Log\SysmacStudioErrorTrace.log`
在编译前后**字节差为 0**。详见 [pitfalls.md §46](pitfalls.md#46-编译没跑起来时错误网格仍然可以是-0-行假-0-错)。

---

## H. 导出与校验

**[实测]** 见 [project-files.md](project-files.md#4-导出) 与 [§6 校验配方](project-files.md#6-导出校验配方强烈建议每次批量搬运后跑)。

一句话流程（`ss_export.py` 已封装）：点 `文件` 菜单栏坐标 → 键 `E` → `SetForegroundWindow(导出对话框)` → 文件名 Edit（aid `1001`）`Ctrl+A`/`Ctrl+V`（中文走剪贴板）→ `保存(S)`（aid `1`）→ 覆盖确认 `是(Y)`。

两条判据：**mtime 变了**、`testzip()` 为 `None`。**别拿字节数相等当失败**（同一工程重复导出大小会变）。

---

## I. 把动作串成一次调用

因为弹出菜单/对话框只在**当前进程**内有效，一串相关动作必须写在**同一次脚本执行**里：

```bash
ss.py flow <pid> "click:NewProjectToggle;wait:800;keys:^a;type:MyProject;wait:200;click:CreateButton;wait:5000"
```

- 步骤间用 `;` 分隔；
- 每步之后脚本自己 `sleep` 0.3~0.5s，关键节点手动加 `wait:`；
- 长等待（建工程/打开工程/编译）不要靠 `wait`，用轮询 `state` 的 `busy`。

失败重试原则：**同一动作最多重试 2 次**，仍失败就记录到 [extending.md](extending.md)，跳过并继续后面的步骤，不要卡死在一个弹窗上。

---

## J. 挂库 / 分配任务 / 改变量表

**[实测]** 三件事都在 [library-and-tasks.md](library-and-tasks.md) 里，这里只给最短路径：

```
挂库：  工程(P) > 库(L) > 显示索引(S) → 库索引里点 + → 引用库文件 里写 .slr 全路径 → 打开(O)
        → 关掉"引用库"提示窗（确定）→ 库索引 确定
        （普通工程里 库设置(L)/创建库(C) 是灰的，只有库工程能用）
分配任务：中上区 任务设置 选项卡 → 左侧图标条第 3 个 → 程序分配设置
        → 逐行点 +（每加一行按钮下移 22px，坐标要重新找）→ 点开程序名组合框选 ListItem
改变量表：单击单元格选中 → 直接打字 → Enter 提交 / Esc 放弃
        （右键只会弹 IME 菜单；名为空的行删不掉，见 pitfalls §22）
读编译：  工程(P) > 检查所有程序(C)（Alt+P 然后按 C），面板顶部直接显示 "N 错误 / M 警告"
```

**拖拽不成立**：把程序拖到任务节点上、把变量拖进表格，合成鼠标拖拽都不产生拖动影像，实际不生效。

---

## K. 重建工程的验收顺序

**[实测]** 本轮把一个真实工程重建到另一工程时用的是这个顺序，每一步都有客观判据：

| 步骤 | 判据 |
| --- | --- |
| 1. 树结构 | `ss_tree.py count` 对比各级子节点数（程序/功能/功能块/数据/任务） |
| 2. 任务分配 | `任务 > PrimaryTask` 子节点数 = 期望程序数，叶子名逐个核对 |
| 3. 编译 | 编译面板 `N 错误 / M 警告`，并把前 N 行错误按"说明"归类 |
| 4. 导出 | `文件>导出(E)...` → `保存(S)` → `是(Y)`，核对文件大小/时间戳变化 |
| 5. 落盘校验 | [project-files.md §6](project-files.md#6-导出校验配方强烈建议每次批量搬运后跑) 的 digest：`testzip()` 为 None、实体计数逐类比对 |

**预期会留下的错误**（不是你的操作失误）：设备/EtherCAT/安全组态搬不过来 → 所有设备地址类错误（`地址不合法。`）都会保留；编辑保护的 POU 缺失也会连带。


---

## L. 导出成 .smc2（含覆盖确认）

**[实测]** 一条命令：

```bash
ss_export.py <pid> "我的工程.smc2"        # 导出到对话框上次停的目录，覆盖同名
```

内部步骤（自己写脚本时照这个顺序）：

1. `force_foreground(main_hwnd)`；点菜单栏 `文件` 的坐标（窗口左上 + (48, 55)，125% DPI）；
2. `keybd_event('E')`（不要用 `Alt+E`，有的实例菜单栏一进键盘模式就吞键）；
3. 轮询 `wins_of(pid)` 里 `cls == '#32770'` 且标题含 `导出` 的窗口（最多 10s）；
4. **`SetForegroundWindow(dialog)`** ——不抢对话框的前台，键盘事件会发给主窗口，文件名不变；
5. 点 `EditControl AutomationId='1001'` → `Ctrl+A` → 剪贴板塞文件名 → `Ctrl+V`；
6. 点 `ButtonControl AutomationId='1'`（保存）；
7. 再枚举 `#32770`，对 `ButtonControl` 名字以 `是` 开头的点下去（覆盖确认）；
8. 收尾：再枚举一次确认没有残留对话框，`os.stat` 比对 mtime。

**不要做**：用 `ValuePattern.SetValue` 写文件名（抛 COMError）、用 `SendKeys` 打中文、把 Windows 完整路径从命令行传进来（反斜杠会被 shell 吃掉）。

## M. 全量读编译错误并分类

**[实测]** 重建工程收尾必做：

```bash
ss_build.py run <pid> build_all.txt        # 编译 + 落盘
```

然后按"说明"做归一化（把具体名字替换成占位符）再计数，才知道 385 条到底是几类：

```python
import re, collections
rows = [l.rstrip('\n').split('\t') for l in open('build_all.txt', encoding='utf-8')]
rows = [r for r in rows if len(r) >= 3]
def norm(m):
    m = m.split('\n')[0]
    m = re.sub(r'st_[A-Za-z0-9_]+', 'st_X', m)
    m = re.sub(r"'[^']*'", "'X'", m)
    return m
for k, v in collections.Counter(norm(r[1]) for r in rows).most_common():
    print('%5d  %s' % (v, k))
```

判读原则：**同一类错误计数 × 起因 × 能否修**，比"还剩 N 条"有用得多。重建工程的典型构成：设备地址类（不可修）> 库重名类（可修）> 缺 POU 类（需权限）。

## N. 建数据类型命名空间（子空间）

**[实测]** 用来消掉 `数据名称中含有无效值。`：

1. `数据 > 数据类型` 打开页 → 点选项卡激活；
2. `NamespaceToggleButton`（约 (281,163)）展开命名空间面板 ——**点完重新读一遍控件矩形**，它在展开/折叠两种状态下位置会变；
3. 单击结构体的**名称格**（选中当前命名空间）；
4. 在结构体区域**右键** → 选建命名空间/子空间的项；输入名字回车；
5. 面包屑（y≈163）会变成 `root > 你的空间`，用来确认当前在哪一层。

**别做的事**：靠反复点命名空间树的行来切换空间（实测一直停在同一个节点，点偏就折叠面板）；只改结构体名而不建空间（错误不消失）。

## O. 在 EtherCAT 编辑器里组态从设备（右击插入路线，2026-11-08 端到端实测）

**这条路线已整条验证**：某 EtherCAT 组态工程的 21 个从站全部用
「选中位置 → 关键字搜硬件 → 点结果行 → 右键 `插入(I)`」建出来，**没有一个 drag 动作**；
保存后归档与源工程逐条比对 `RESULT EXACT`。脚本 `scripts/ss_ecat_build.py` 0.3.0。

### O.1 先装 ESI（非欧姆龙从站必需）

1. EtherCAT 编辑器 → 选中**主设备**行 → 真实右键 → **`显示ESI库`**。
2. 独立顶层窗口 `ESI库`（`ProfileLibraryView` / 树 `EsiProfileTreeView`）：
   `installFileButton` 安装(文件)、`cancelButton` 关闭。
3. **硬前置：只能有一个 Sysmac Studio 实例**，多开时安装会弹「因为正在运行多个Sysmac Studio，无法执行安装」。
4. 文件对话框是 Win32 `#32770`：`Edit id=1148` 填路径（`ValuePattern` 可用）、`id=1` 打开。
5. 装完 `ss_esi.py find <关键字>` 在 ESI 树里确认型号出现。
   实测：装汇川 SV660N 后 `SV660` → `InoSV660N Rev:0x00010000 | SV660N_1Axis_00916`。

明细与控件形状见 [pitfalls §68](pitfalls.md#68-esi-库只能单实例安装对话框是独立顶层窗口2026-11-08-实测)。

### O.2 选插入位置（两步缺一不可）

1. 位置 = **从站行下面的端口行**：`X2`/`X3`/`X4`/`X5`/`X6`/`Internal Port`（标签形如 `X2 | Redundancy`）。
   端口行只在父从站行**展开后**才实化 ⇒ `ExpandCollapsePattern.Expand()`。
2. 选中 = `SelectionItemPattern.Select()` **+ 真实左键点标题带**（`x+min(300,max(60,w//3))`, `y+18`）。
   行矩形是**整棵子树高度**，点中心会落到子行上（[pitfalls §70](pitfalls.md#70-拓扑行矩形是整棵子树的高度父行文字会混进所有子孙2026-11-08-实测)）。
3. 主设备下的第一条挂在 `master` 本身（`parent="master"`，`port=""`），其余都写在某个端口下。

### O.3 三条插入语义（决定计划表怎么写）

| 语义 | 实测 | 计划表对策 |
| --- | --- | --- |
| Main device **成对插入** | 插一次生成 Main + 它 `Internal Port` 下的 Sub，`从设备数量` +2 | 用 `sub_name` / `sub_node` 描述那对里的第二个 |
| 插入落在端口**头部** | 同端口的菊花链在拓扑里是**倒序** | 按**链尾→链头**倒序写步骤 |
| 插入会**自动重排节点号** | 插到中间会顺移后面所有节点号 | 节点号在 `renumber` 阶段最后统一写 |

### O.4 设备名与节点号

- **设备名**：右侧参数表 `设备名称` 行，值在 `Text AutomationId='text'`（**无 ValuePattern**）⇒
  点单元格 → 真 `Ctrl+A` → 剪贴板粘贴 → `Enter`（不全选会把新名插进旧值中间，得到 `E0新名…` 这类脏值）。`scripts/ss_ecat_name.py`。
- **节点号**：从站行自己的 `EditControl aid='editBox'`，点 → `Ctrl+A` → 粘贴 → `Enter` 后 `ValuePattern` 读回。
  读回可能是 `''`（控件重建），此时**不代表没写进去**：重新定位该行再读，或 `--only "名1||名2"` 单独重跑。
- 改完名/号控件会重建 ⇒ **每次操作前重新定位行**，不要缓存控件。

### O.5 批量执行

```bash
cd /d "<skill目录>\scripts"
python ss_ecat_build.py <pid> <plan.json> <logdir> --save-each
python ss_ecat_build.py <pid> renumber <plan.json> <logdir>
python ss_ecat_build.py <pid> renumber <plan.json> <logdir> --only "名1||名2"
```

计划表（UTF-8 JSON 数组，按顺序执行）：

```json
{"step": 2, "parent": "总站123", "port": "X2",
 "kw": "GX-JC06", "pick": "GX-JC06(IN,X2,X3) Main device",
 "name": "IO站123", "node": "2",
 "sub_name": "IO站456", "sub_node": "4"}
```

- `kw` **只写设备名**（`GX-JC06`、`NX-ECC203`、`SV660`、`CTEU`）：带括号/`Main device` 的整串会 0 结果
  （[pitfalls §71](pitfalls.md#71-工具箱搜索只匹配设备名工具箱--查找和替换是同一组-panecontrol-页签2026-11-08-实测)）。
- `pick` 在结果行里挑子串；`显示所有版本` 保持**关**（源工程就是推荐版本）。
- `--save-each` **必开**：组态只在内存里，进程退出即丢
  （[pitfalls §72](pitfalls.md#72-ethercat-组态只在进程内存里不落盘进程一退出全没2026-11-08-血的教训)）。

### O.6 验收：只认归档

```bash
cd /d "<skill目录>\scripts"
python ss_ecat_archive.py "<目标.smc2>" flat
python ss_ecat_archive.py "<目标.smc2>" cmp "<源.smc2>"
```

- `节点标签` = `节点N : 设备型号 (设备名)`；`RESULT EXACT` 同时证明**节点号 / 型号 / 设备名 / 物理顺序**四项。
- **不要**用 `ss_ecat_archive.py diff` 当验收：它把实体 `name`（`N/A0`、`EcatCoupler1`）也算进签名，天然全红。
  要比就比 `(subtype, 节点标签)`。
- 结构（谁挂在谁的哪个端口）对 UIA 树：`ss_ectree.py dump`，或按行名取子树
  （`ss_ectree.py subtree <out> <行名子串>`）。从树根 walk 会因视口高度缺行（[pitfalls §73](pitfalls.md#73-拓扑树按视口实化从树根-walk-会整段缺行2026-11-08-实测)）。
- `从设备数量` 与工程树都会滞后，只能当参考。

**其它实测无效的入口**（不要再试）：从站行的「+」按钮、主菜单 `插入(I)`（只有
`从设备终端(S)` → `EtherNet/IP耦合器`/`PROFINET耦合器`）、双击工具箱结果行。

**删从站**：右键从站行 → `删除(D)`，无确认框；工程树里的从站行没有右键菜单。

## P. 收敛到 0 错之后：导出并**重新打开复验**

顺序不能省（踩过：导出的是旧快照、以及"内存 0 错但文件有问题"）：

1. **编译**：`编译控制器(B)` → 面板头部必须是 `0 错误 / 0 警告`；`dumpbuild` 读出 0 行。
2. **导出**：先按两次 `Esc` 收掉可能还开着的下拉/单元格编辑（**变量表里一个没关的下拉会让第一次点"文件"只起到关下拉的作用**），再 `文件(F)` → 键 `E`（或 UIA 点 `导出(E)...`）→ 在 `导出文件` 对话框里**单击列表里的目标行**（文件名框自动填好）→ `保存(S)` → `确认另存为` 点 `是(Y)`。详见 pitfalls §25 / §29。
   - 菜单点不开时先看有没有 `#32770` 残留模态窗（如失败的「导出文件」），见 pitfalls §23。
3. **等文件写完**：对话框关掉后文件可能还在写（实测出现过 2.6 MB 的中间态），**隔 2~5 s 再看 `os.path.getsize` 是否稳定**。
4. **校验容器**：`testzip()` 为 `None`；条目数/实体数按类型计数与预期一致。
5. **独立复验**（关键）：用 `ShellExecute` 把导出的 `.smc2` 交给默认程序 → 会起**新实例**（标题自动带 `_2` 之类后缀）→ 在新实例上再点一次 `编译控制器` → 必须仍是 `0 错误`。这一步才证明"磁盘上的文件是对的"。
6. 复验完把临时实例关掉（提权 `taskkill`），避免多实例抢焦点。

导出产物与手工 zip 的差异属正常：`Solution` 实体 id 会换新，并会补一个 `SafetyProject` 实体。

## Q. 新建运动控制轴并填参数（工程树 + 轴页）

2026-10-31 录制实测路线（录制文件是本机运行时产物，不随 Skill 发布；复现方法见 [recording.md](recording.md)）。
**不要**再用主菜单 `插入(I) > 轴设置(A)` 的老路线（对话框不稳定）；走工程树右键。

1. **建轴**：工程树 `配置和设置 > 运动控制设置 > 轴设置` 上**右键** → 菜单项 `添加`
   → 右侧弹出的子菜单第一项（`添加DropDown`）→ 点击。树下立刻多一行 `MC_AxisNNN`，
   轴号按创建顺序自动分配（0,1,2…），不能也不需要在树里改。
2. **重命名**：选中新行 → `F2`（或对行做双击）→ 树内出现临时 `EditControl`
   （`AutomationId` 是一串数字，如 `2032460`，不要按 id 找，按“落在树矩形内”找）
   → 全选 + 剪贴板粘贴 → `Enter` 提交。提交后树里文字应变成目标名。
3. **打开轴页**：单击行 + `Enter`（先 `ss_tree.py goto <pid> <路径>` 选中，再真点行 + `Enter`；或直接 `ss_uimap.py open`）。选项卡名是 `轴名 (轴号)`。
4. **轴页结构**（64bit V1.68 实测）：

   | 位置 | 控件 | 取值 |
   | --- | --- | --- |
   | 顶部 | `ComboBoxControl` ×2~3（y=247/270/377） | 轴类型（`伺服器轴`）与关联节点（`节点:N 型号(E00x)`）；**按选项内容认，别按序号**：展开后选项含 `伺服器轴` 的是类型，以 `节点` 开头的是关联节点 |
   | 左侧导航 | `CustomControl aid=axes_scale` | 缩放设置（单元 / 行程距离） |
   | 左侧导航 | `CustomControl aid=axes_dynamics` | 动作设置（最大速度/加速度/减速度） |
   | 左侧导航 | `axes_io` / `axes_limit` / `count_mode_set` / `servo` | IO / 限制 / 计数模式 / 伺服驱动器 |
   | 右侧 | `GroupControl '单元'`（`subsectionExpander`） | `RadioButton '毫米'` |
   | 右侧 | `GroupControl '行程距离'` | 行程距离等数值 `EditControl` |
   | 右侧 | `GroupControl '速度/加速度/减速度'` | 3 个数值 `EditControl`（自上而下 = 最大速度/加速度/减速度，y=252/293/313） |

5. **下拉项的位置**：轴页的组合框下拉列表**不是组合框的子节点**，而是挂在主窗口
   `Window(cls=Popup) > Pane > ListItem` 下；`combo_items(combo)` 在这里永远返回空。
   正确做法：展开后在所有弹层（`ssk._popup_roots`：顶层弹窗 + 主树里的 `Window(cls=Popup)`）
   里找「`ListItemControl` 且 `x` 与组合框对齐、`top` 在组合框上下 400px 内」的那批项，
   再读它直接子 `TextControl` 的 `Name`。实测偏移：组合框 `[466,270]` → 弹层
   `[466,288]` → 首项 `[467,289]`（项可比组合框宽，如 `[467,396,220,21]`）。
6. **关联节点**：只有下拉里出现**伺服驱动器**（`R88D…` / `R88M…` / `1SN…`）才能关联；
   工程里只有 `GX-JC06` 这类耦合器时，轴页的关联节点没有可用项 → 跳过并记录，
   不要硬选耦合器。
7. **参数真值**（从源工程轴 XML 读，导出后同样可校验）：
   `NexAxisUnitsNumerator/Denominator`（pulse/rev 与 mm/rev）、
   `NexAxisTravelDistancePerWorkRotation`、`NexAxisMaxVelocity`、
   `NexAxisMaxAcceleration`、`NexAxisMaxDeceleration`、`NexAxisMaxJogVelocity`、
   `NexAxisInPositionBand`、`NexAxisHomingVelocity`、`NexAxisHomingApproachVelocity`。
   每个轴实体在 `.oem` 里是 `type="AxisSettingEntity" id=… name=… DN="名 (号,MC1)"`。
8. **单位**：`NexAxisUnitsConversion=EnumElement2` + `…NumeratorValue2=pulse/rev`、
   `…DenominatorValue2=mm/rev` 对应界面上的「毫米」；换算值本身不在界面的行程距离格里，
   界面上填的是 `NexAxisTravelDistancePerWorkRotation`。
9. **八个子页 = 左侧导航条的 8 个按钮，aid 与实测标题一一对应**（`ss_axis.py nav <pid> <out> <树路径>`
   会把这张表原样打出来，实测落盘 `axnav.txt`，源工程 轴4）：

   | aid | 页面标题 | 实测行数 |
   | --- | --- | --- |
   | `basic_setting` | 轴基本设置 | 17 |
   | `axes_scale` | 单位换算设置 | 1 |
   | `axes_dynamics` | 操作设置 | 16 |
   | `axes_io` | 其它操作设置 | 9 |
   | `axes_limit` | 限位设置 | 5 |
   | `back_original_point` | 原点返回设置（用户常说"远点返回"） | 16 |
   | `count_mode_set` | 位置计数设置 | 4 |
   | `servo` | 伺服驱动设置 | 4 |

   逐参数写用 `ss_axis.py apply <pid> <out> <plan.json>`，plan 每元素
   `{"path":"0.4.0.N","sets":[{"section":"<aid>","label":…,"value":…}]}` ——
   **一根轴一个进程**（同一 UIA 会话里开页一次、写完全部字段），别逐字段重开页。
   两个必踩前提（[control-tree.md §16.7](control-tree.md)、pitfalls §57）：节里的 `GroupControl`
   是 `subsectionExpander`，**折叠时那些行根本不在 UIA 树里**（`单位换算设置` 实测就是这样），
   读/写前要先展开；`轴基本设置` 的 PDO 表还藏在第二个名为 `详细设置` 的 Expander 后面。
   写完一律走 §R 第 7~8 步（保存 + `ss_axcmp.py`）验收，**界面读回只说明控件这么显示**。

## R. 轴↔从站绑定与 PDO 过程数据映射（2026-11-07 实测，唯一可行界面路线）

**[实测]** 场景：把 A 工程的 6 根轴的「输出设备 / 每个功能的 PDO 位映射」在 B 工程里逐轴逐项重做。
工具：`scripts/ss_axtable.py`（轴设置表）、`scripts/ss_axpdo.py`（轴页 PDO 表）、
`scripts/ss_axisplan.py`（从源 `.smc2` 生成写计划）、`scripts/ss_axcmp.py`（两份文件逐参数对比）、
`scripts/ss_crashdlg.py`（软件自己弹的 .NET 异常框）。控件形状与坐标见
[control-tree.md §17](control-tree.md#17-轴设置表winforms与轴-pdo-过程数据2026-11-07-实测)。

1. **先把三条组合框通道的差别搞清楚**（本轮最贵的坑，机制解释在
   [pitfalls.md §59/§60](pitfalls.md)）：
   - 轴页顶部的 `输出设备1` 组合框**只显不写**：UIA Select、鼠标点行、`HOME`+`↓`+`Enter`、
     关闭态 `40×↑ + N×↓`、切文档页签，五种机制全部试过，保存后文件里
     `NexAxisOutputDevice1` 一个字节都不动。**不要拿它的显示文字当真值。**
   - 轴页 PDO 表里的 `设备` 列**能写**，但它是**按已绑定设备过滤**的下拉：
     绑定没改对时它只给 `＜未分配＞`，于是它同时是最好的**免保存探针**——
     下拉里出现 `节点:20 <型号>(<设备名>)` 就说明模型里真的绑上了。
   - `轴设置` 节点右键 → `轴设置表(S)` 打开的 WinForms 表**才是改绑定的入口**：
     UIA 看不见它的单元格，但点一格会浮出一个真正的 Win32 编辑框
     （`WindowsForms10.COMBOBOX.app.0.*`），`CB_GETCOUNT/CB_GETCURSEL/CB_GETLBTEXT`
     全可用，34 个从站全列出，且 `cursel` 就是模型真值。
2. **改绑定**（`ss_axtable.py set`）：`raise_tab '轴设置表'` → 按 cell 坐标真点一格 →
   `EnumChildWindows` 抓那个 COMBOBOX → 读 items/cursel → 对**已聚焦的关闭态组合框**
   逐次发 `{UP}`/`{DOWN}`（Win32 组合框在关闭态用方向键改选中就会发
   `CBN_SELCHANGE`，这才是表格监听的信号；`CB_SETCURSEL` 只动文字不通知，**故意不用**）
   → `{ENTER}` → 点上一格离开 → 再点回来复读 `cursel` 确认。
   本轮实测：`cursel 21 → 10`，保存后 `NexAxisOutputDevice1` 从 `<旧 sha 前缀>`(旧设备)
   变成 `<新 sha 前缀>`(目标设备)，与源工程一致。**这一步有概率触发软件自己的
   .NET ThreadException 对话框**（pitfalls §63），写盘成功但流程会卡住，处理见第 6 步。
3. **换绑会清空 PDO 映射**（pitfalls §61）：改完输出设备后，该轴 PDO 表里所有
   `设备`/`过程数据` 都退回 `＜未分配＞`。所以顺序必须是**先绑设备，再写 PDO**，
   反过来做等于白做。
4. **写 PDO 表**（`ss_axpdo.py`）：
   - `expand <pid> <out> <轴树路径>` 先打开 `MultiPDOTableFieldView 详细设置` 里那三个
     组行（`输出(控制器到设备)` / `输入(设备到控制器)` / `数字输入`）；组没展开时子行
     **不在 UIA 树里**，展开要边滚边找（虚拟化网格）。
   - `ss_axisplan.py <源.smc2> <轴号>` 生成写计划：每行 `{label, device, pdkey}`，
     `label` 用 FunctionNumber 对齐网格里的功能名（`1. Controlword`），
     `pdkey` 由源 XML 的 `PDO<i>PDOPathName/ODBitLocation` 拼成
     `6040h-00.0` 这种**按位**的键（`'%sh-%s.%s' % (obj.upper(), sub, bit)`）。
   - `apply <pid> <out> <轴树路径> <plan.json>` 逐行写：`设备` 用 `ss_axis.set_combo`
     （幂等：已经对就读 `already` 并**绝不重设**，重设会清掉该行 PDO）；`过程数据` 用
     `pick_prefix()`——真点开下拉（`SelectionItemPattern` 在这些行上是 `None`，
     UIA Select 走不通）、**在弹层自己的矩形里滚滚轮**、先向上后向下扫、按
     `caption.startswith(key + '(')` 匹配后点它；滚不动就退回**键入键名 + `Enter`**
     （WPF 的文本检索会直接把高亮跳到那一项，本轮 60FDh-00.0/.2 就是靠这条路写进去的）。
   - 每行写完都用 `combo_selection()` 复读，`startswith(key+'(')` 才算过。
5. **`NexAxisPDOMappingTable` 改不动，别追**（2026-11-07 用一整轮实测换来的结论，细节见
   [pitfalls.md §65.2](pitfalls.md#65-两条读文件才知道的真相编译不补-pdo-字段折叠态会写进工程)）：
   它**不是**"保存那一刻的展开态"。真点了三个组（`toggleUnit` 的 `toggleButton` 文字确实从
   `'-'` 变 `'+'`，反向也一样）、保存（sha 变了）、甚至关掉该轴页签再保存，三种做法之后
   归档里那串**都一字未动**。它只在"该轴的 PDO 单元格被界面提交过"时出现，且只增不减。
   ⇒ 逐行写完 PDO 的轴必然带这串，源工程里没写的轴就是空 —— **验收时单列一类如实报告**，
   不要为对齐去反复点 toggle（每轮好几分钟且无效），更不要手改归档。
   5b. 读源工程时注意：这串**是"提交顺序"而不是集合**（同一份源里 轴4
   `output,input,digital input` 与 轴27 `digital input,input,output` 两种顺序都出现过），
   别把两种写法当成两种状态。
   5c. 逐轴的实际值现读，别抄文档（下面是某源工程的实测基线示例，`''` = 空串）：
   `轴0 ''(en=false，未使用) 轴1 '' 轴2 '' 轴3 '' 轴4 'output=True,input=True,digital input=True,'
   轴5 ''`，读法就是
   `python scripts/ss_axisparams.py <源.smc2> --all` 里 grep `PDOMappingTable`。
   5d. 只想**看**折叠态用 `ss_axpdo.py toggles <pid> <out> <轴路径>`（只读，报三组
   `toggleButton` 的 `+`/`-`、`IsOffscreen` 原文和 `ToggleState`）；要看这行的控件到底长什么样，
   用 `ss_axpdo.py peek`（把组行整棵子树打出来）。
6. **中途弹 .NET 异常框**：`python scripts/ss_crashdlg.py <pid> <out>` 先看，
   确认是 `Microsoft .NET Framework` 那个 ThreadException 框再 `… click` 只点 `继续(C)`；
   **永不点 `详细信息(D)`/`关闭`**（点关闭会带走整个实例）。软件活着、已写的值还在。
7. **落盘才有真值**：上面每一步写的都只是**内存里的模型**。收尾必须
   `python scripts/ss_save.py <pid> saveN --menu [--file <目标.smc2>]`——它记 sha256、
   每 2 s 复算一次，**文件 sha 变了才认**（`#### SAVED (+Ns)`；`UNCHANGED` 退出码 1）。
   `--menu` 是本轮实测出来的**默认该走的路**：`文件(F)`→`保存` 用 UIA 展开+点击，
   不碰键盘，实测 +1s 落盘；裸 `Ctrl+S` 在有残留下拉弹层时**会被弹层吃掉**（弹层是独立顶层
   `HwndWrapper[...]` 小窗），脚本先 `--esc 2` 再按，仍然不变就走菜单兜底。
   菜单项真实 `Name` 带访问键后缀（`保存(S)`），脚本内已剥后缀匹配，见
   [pitfalls.md §66](pitfalls.md#66-保存这一刀ctrls-会被残留弹层吃掉菜单项名字带访问键后缀2026-11-07-实测)。
   保存可能弹确认框，脚本**只记录文字**，要人判断；许可/序列号类窗口一律标出来不碰。
8. **校验只看文件，不看界面**：`ss_axcmp.py A.smc2 B.smc2 0 1 2 3 4 5` 出逐参数差；
   `编译` **不会**把 `PDOPathName`/`ODBitLocation` 补出来（实测过），所以别指望
   编译后再读就有了；没写进去的就是没写进去。

