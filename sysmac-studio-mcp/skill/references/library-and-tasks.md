# 库引用、任务分配与变量表编辑

本章是"把一个工程重建到另一个工程"时最缺的三块拼图：**库怎么挂**、**程序怎么挂到任务**、**变量表怎么改**。
全部 **[实测]** 于 Sysmac Studio V1.68 64bit / 125% DPI / 1920×1080，坐标为**屏幕像素**（换 DPI 必偏，换版本要重新量）。

---

## 1. 工程 > 库(L) 子菜单：两个世界的分界

菜单路径：`工程(P)` → `库(L)`。子菜单只有三项：

| 项 | 普通工程 | 库工程（标题带 `[库]`） |
| --- | --- | --- |
| `显示索引(S)` | **可用** | 可用 |
| `库设置(L)` | 灰 | **可用** |
| `创建库(C)` | 灰 | **可用** |

**结论**：普通工程里给工程挂库，只能走 `显示索引(S)` → `库索引` 对话框里的 `+`。
`库设置/创建库` 是"把当前工程导出成 .slr 库文件"用的，只在自己是库工程时点亮。
（想从普通工程做库：新建工程时把工程类型选成**库**，标题会带 `[库]`，这时才有 `创建库(C)`。）

### 打开子菜单的正确手法

[实测 2026-10-31] 结论要修正：

- **可用（首选）**：UIA 点 `工程(P)` 打开一级菜单 → 鼠标**悬停** `库(L)`（不要先点，WPF 悬停才展开二级）→ 在新弹窗里找 `显示索引(S)` 并 Invoke。整条路径要在同一个提权进程里连续完成，中途别 sleep 太久让菜单自动收起。
- **可用（兜底）**：先点开 `工程(P)`，菜单拿到焦点后按 `L` 再按 `S`。`Alt+P` 直接发组合键**不一定**能展开（焦点在表格单元格时会被吞）。
- **错误写法**：`menu_click(PID, '工程(P)', '库(L)')` 之后再 `menu_click(PID, '库(L)', '显示索引(S)')` —— 第二次会在**主菜单**里找 `库(L)`，永远找不到；子菜单项只在独立弹窗 HWND 里。
- 打开前若表格里有未提交的下拉/编辑，第一次点击只会关掉它，见 pitfalls §32。

参考资料实现：`ssk.menu_path(pid, '工程(P)', ['库(L)', '显示索引(S)'])`。

### 窗口类不要写死

`库索引` 本身可能是 **WPF 窗口**（`HwndWrapper[...]`），只有 `引用库文件` 文件选择框是原生 `#32770`。按标题在所有可见顶层窗口里找，别加 `cls == '#32770'` 过滤，否则会出现"菜单明明打开了却报没打开"。

---

## 2. 给工程挂一个 .slr 库（库索引）

```
工程(P) > 库(L) > 显示索引(S)
  → 窗口 库索引
     表格列：库名称 / 命名空间 / 版本 / 作者 / 公司 / 创建时间 / 修改时间 / 注释 / 附件 / ID
     工具条：+   🗑(空表时灰)   ↻
     复选框：将引用库包含在工程中（默认勾）
     复选框：如果工程中的库ID与引用库文件ID不匹配，则通知
     按钮：确定
  → 点 +  → 原生对话框 引用库文件 (#32770，默认目录是软件的库目录)
     文件名(N): Edit   →  用 ValuePattern.SetValue 写**完整 .slr 路径**（中文路径安全）
     打开(O)
  → 弹出独立提示窗 引用库：
     "库中可能使用了当前控制器不支持的指令。…"  → 确定
  → 回到 库索引，表格多出一行（库名称/版本/作者）  → 确定
```

实测几何（125% DPI，仅供定位参考，优先用 UIA Name 找控件）：

| 控件 | 矩形 |
| --- | --- |
| `+` | (576,603,613,634) |
| 删除（垃圾桶） | (613,×,651,×) |
| 刷新 | (651,×,688,×) |
| `确定` | (920,669,1013,698) |
| `引用库文件` 的 `打开(O)` | (1256,938,1366,971) |

校验成功：

- 立即判据（2026-10-31 实测）：回到 `库索引` 后，表格里出现**库文件名**（如 `MyLibV1.0.0_20250101`）或 `DataItem/ListItem` 行。表格行不一定暴露成 DataItem，但文件名文字一定在对话框的某个 `Text` 里 → **按"文件名子串出现"判成功**，别只数行。
  - **2026-11-21 更正（V1.68）**：这条**在本版本不成立**。实测该表格根是 `CustomControl class='LibraryDataGrid'`，**既没有 `DataItem/ListItem` 子节点，也没有承载行文字的 `Text` 子节点**——UIA 下这个表就是个空壳（dump 出来只有 `itemScrollViewer` + `LibraryDataGrid` 两行）。所以**不要**用"文件名出现"当判据，改用下面两条之一：
    1. **离线判据（最可靠）**：`ss_libref.py <pid> <out> list <工程.smc2>` —— 直接读归档里 `ReferredLibrary/LibraryModel` 的 `Name`/`Version`/`LibraryId`/`LibraryFilePath`/`IsSource`/`IsDisableSourceDisplay`。需要先把工程保存一次（或本来就有磁盘文件），不需要 Sysmac 在跑。
    2. **界面旁证**：打开一个程序编辑器后，工具箱出现分组按钮 ` <库名> ( <版本> )`（`AutomationId='groupToggle'`）——这是"库真的挂上了"的可见证据，且能进一步列出 POU（见 §8）。
- 导出后：digest 脚本看 `.oem` 里 `ReferredLibraries` 实体 = 1，且库工程的 `Library` 实体还在。
- 右侧工具箱出现库命名空间（如 `MyLibV1.0.0…`）也是旁证。

**`+` 按钮的稳定标识**：`AutomationId == 'CreateLibraryReference'`（实测）。别按"最左上的按钮"猜——工具条里还有 `(0,0,0,0)` 的空名虚位按钮，会被误选。

---

## 3. 程序挂到任务：任务设置 → 程序分配设置

**不存在"把程序拖到任务上"这个操作**（见 §3.3）。正确入口在右侧编辑器页里：

```
中上 TabbedMdiContainer → 任务设置 选项卡
  → 左侧竖排图标条，第 3 个图标（内部名 BaseTaskPOUSetting，约 (278,328)-(380,380)）
  → 视图 TaskAssociateProgramsView：
       每行 = 程序名 ComboBox + 初始状态 ComboBox（运行/停止）
       按钮： +（添加行） ↑ ↓ 🗑
```

实测要点：

1. 行高 **22 px**；每点一次 `+` 按钮整体下移 22 px —— **必须每次重新按 UIA 找 `+`**，不能缓存坐标。
2. 新加的行程序名是空的，要逐行点开 `程序名` 组合框，再从弹出的 `ListItemControl` 里按名字点选。
3. 组合框里的候选就是工程里的 `程序` 叶子；点选后该程序才真正进入任务的执行列表。
4. 初始状态默认 `运行`。
5. `程序属性` 对话框里**没有任务字段**（只有 名称/命名空间/版本/作者/创建时间/更新时间/注释），别去那里找。

### 3.1 一次可用的驱动写法

```python
def plus_button():      # 第一个 left 在 370~395、宽 <45 的 ButtonControl
def program_combos():   # left 在 400~440、宽 >800 的 ComboBox，按 top 排序
for name in WANT:
    pb = plus_button()
    click(centre(pb))                    # 加一行
    combos = program_combos()
    t, b = combos[-1].top, combos[-1].bottom
    click(700, (t + b) // 2)             # 点开最后一行的程序名
    items = scan('ListItemControl', name)
    click(centre(items[0]))
```

### 3.2 校验

工程树里 `任务 > PrimaryTask` 的子节点数 = 已分配程序数；叶子名就是程序名。

### 3.3 三条实测不通的路（不要再试）

| 做法 | 结果 |
| --- | --- |
| 把 `程序` 叶子拖到 `任务`/`PrimaryTask` 上 | 合成鼠标拖拽不产生拖动影像，树只显示"选中"，任务下没有新增 |
| 右键 `任务` / `PrimaryTask` | **完全没有上下文菜单**（不是灰，是没有） |
| 在 `程序属性` 里找任务字段 | 没有该字段 |

---

## 4. 变量表 / 数据类型表编辑

两块表都是 WPF 自定义控件，**单元格本身是常驻编辑框**，这带来两个后果：

1. 右键几乎总是弹出 **IME 文本服务菜单**（简体中文/微软拼音/中/英文/全/半角/…），而不是表格的上下文菜单。
2. `Alt+字母` 加速键在单元格聚焦时会被吞掉。

**可用的操作**：单击单元格选中 → 直接 `keybd_event` 打字（实测字符会进入单元格）→ `Enter` 提交 / `Esc` 放弃。

**已知做不到的**（实测 6 种写法都失败）：

- 删除一条**名为空**的全局变量行：`删除(D)`（能点到）、`Delete` 键、`Esc`、清空数据类型、`Ctrl+A`+`Delete`、工具栏 `删除(D)` 按钮 —— 行都留在原地。
- 该行**会被导出**：`.smc2` 里的变量行是 `++D=<类型> AT=<地址> Const=1 G=VAR_GLOBAL`，空名行就是**缺 `N=` 字段**的那一行；编译时报 `变量名是空。 全局变量 - 名称`。

> 推论：这条错误是**数据**层面的，不是界面没刷新。想彻底消掉只能在界面上做出一次"真删除"（人工：选中该行的行号格 → 右键 → 删除(D)），或用 `.smc2` 离线改（未验证，见 extending.md）。

数据类型表的右键菜单是另一套，可用：`新建数据类型(N)` / `新建成员(M)` / `删除(D)` / `全选` / `更新偏移` / `展开全部` / `折叠全部`。

**建成员的正确姿势**（2026-10-31）：不需要打开成员页。选中结构体行 → 右键 → `新建成员(M)`，成员会以**同一张表格的子行**插入，接着就地写 `名称` → `Tab` → `数据类型` → `Enter`。判定成员是否存在只能看行**第一列名称是否完全相等**（结构体行与成员行同表，`row_text` 里含名字会把结构体行也算进去）；`展开全部` 用来确认成员真的挂在目标结构体下面。

---

## 5. 读编译结果

- 工具栏 `编译控制器(B)`（`HelpText`）或 `工程(P) > 检查所有程序(C)`（`Alt+P` 然后按 `C`）。
- **不要截图识别了**（0.3.0 的写法已过时）：面板头部是两个 `TextControl`（`'385'` + `'错误'`、`'0'` + `'警告'`），直接读 `Name` 就行；下方是 `DataGridControl`（`top > 630`），支持 `ScrollPattern`，可逐屏收到全量。
- 现成脚本：`ss_build.py totals|list|run <pid> [out.txt]`；落盘一律 UTF-8（控制台 GBK 会乱码）。
- 列表列：`编号 / 说明 / 程序 / 位置`；`说明` 可能含换行，按 `编号` 去重。

细节见 [control-tree.md §9](control-tree.md#9-输出--编译面板) 与 [pitfalls §26](pitfalls.md#26-编译错误列表几何定位--滚动--utf-8)。

---

## 6. 重建一个工程时的"不可搬运"清单（实测）

| 类别 | 结果 |
| --- | --- |
| 设备 / EtherCAT / NX 总线 组态 | **搬不动**（不在 POU 复制语义里）。缺了它，所有 `X100`、`MC://_MC_AX[1]` 之类地址报 `地址不合法。` |
| 安全（Safety）应用 | 搬不动，`.smc2` 里的 Safety* 实体全部缺失 |
| 编辑保护的 POU（源工程里被锁的程序/功能） | 右键 `剪切/复制/带有副本复制` 全部灰，剪贴板哈希不变 → 只能跳过并记录 |
| 库工程里的 FB / 数据类型 | 通过挂 `.slr` 引用获得，不要指望逐个粘贴 |
| 空名变量行 / 空数据类型行 | 见 §4，删除不掉就记录 |

重建完成后的自检顺序：**树子节点数 → 任务分配 → 编译错误数 → 导出 → digest 比对**。

---

## 7. 在已有库 FB 上加功能 → 重建 .slr → 换进目标工程（端到端，2026-11-13 实测）

场景：目标工程已经引用了一个封装好的轴控库 FB，要在**不破坏存量调用**的前提下给这个 FB 加一段新功能
（本轮是末端振动抑制），再让目标工程用上新库。整条链路 = **改库源 → 创建库 → （必要时）离线对齐接口 →
换引用强制重载 → 重编译 → 菜单保存**。前提：手上有一个**库源工程**（标题带 `[库]`，`创建库(C)` 才点亮，见 §1）。

> 安全：全程**离线编译验证**，不下载/不在线/不改控制器（SKILL.md §7 红线）。动手前**备份目标工程**。
> 改库源用"按轴开关、默认 OFF"的形态（[offline-surgery §9](offline-surgery.md)），不启用时走原逻辑分支、不破坏存量调用——
> 这是**编译/结构层面的验证，不是运行时实测**；示例运动参数只属于其工程语境，不具普适安全性。

### 7.1 改库源 FB 并创建库

1. 在库源工程里给目标 FB 加功能（界面改，或离线注入实体子树 + 按轴开关，见 [offline-surgery §8/§9](offline-surgery.md)）。
2. `工程(P) > 库(L) > 创建库(C)` → 确认「创建库时工程会自动保存…」`是(Y)` → 进度条 → `创建库文件` 保存框。
3. **保存框默认目录 = 软件库目录、默认文件名 = 原 .slr 名**，直接保存会**覆盖已安装的原库**！
   先把文件名设成**新的完整路径**（`ValuePattern.SetValue` 在这个框可用，设完回读校验），再 `保存(S)`。详见 [pitfalls §77](pitfalls.md)。
   产出：一份新的 `.slr`（带着库源里的 FB 形参名）。

### 7.2 （必要时）离线把新库接口对齐到目标所依据的已编译库

如果目标工程的调用点报 `'<形参名>'不是输入-输出变量。`，多半是**库源形参名与目标原先依据的已编译库漂移**
（例如源是 `iMasterNum`、原已编译库是 `diMasterNum`）。**不要**回界面逐个改形参——按
[offline-surgery §10](offline-surgery.md) 的配方，在新 `.slr` 上**只对该 FB 的接口+体**离线改名，
和原已编译库（pristine，只读基准）做 **Id 归一化**校验（体字节全等、接口归一化后全等），守住别的 FB 字节不变。
根因与判据见 [pitfalls §78](pitfalls.md)。

### 7.3 在目标工程里"换引用"强制重载库缓存（关键，别跳过）

**改磁盘 `.slr` 后 Sysmac 不会自动重载**，直接重编译错误一条不少；`库索引` 的**刷新(↻)键恒灰**也用不了。
唯一可行 = **删旧引用行 + 重加同一路径**（[pitfalls §79](pitfalls.md)）。用 `ss_libref.py`（提权通道）：

```bash
S=<skill目录>/scripts
python $S/ss_libref.py <目标pid> <log.txt> open                 # 工程>悬停库>显示索引，打开库索引（全程鼠标绕 IME）
python $S/ss_libref.py <目标pid> <log.txt> replace "<新.slr完整路径>"  # 选第一行→删→+→剪贴板贴路径→校验→打开→消警告→确定
python $S/ss_libref.py <目标pid> <log.txt> warn                 # 补消可能 >2s 才冒出来的「引用库」警告
```

- **替换不是追加**：新旧 `.slr` 库名相同（内部 Library id 不同）时，不删旧行直接 `+` 会撞名出两行 ⇒ 必须先删后加。
- 填文件名**只用剪贴板 `Ctrl+A/Ctrl+V`**（控制组合键不受 IME 影响），**校验 `Value==目标路径` 后才点 `打开(O)`**；
  `auto.SendKeys(路径)` 会被中文 IME 变候选、产生非法文件名并弹模态错误冻住全部 UIA（[pitfalls §76](pitfalls.md)）。
- 库索引改动**点「确定」才提交**，中途「关闭」可整体放弃 ⇒ 换引用阶段安全可回退。

### 7.4 重编译 + 菜单保存 + 验收

```bash
python $S/ss_build.py run <目标pid> <errors.txt>     # 点编译控制器→轮询到稳定且有本轮编译证据→全量读错误列表（无证据/读不到=非0）
python $S/ss_save.py <目标pid> --menu --file <目标.smc2>   # 文件(F)>保存 走 UIA；Ctrl+S 会被残留弹层吃掉（§66）
```

- 编译面板**刚点完会读到上一轮的陈旧计数**。`ss_build.py run` 现要求"两个计数都读到 + 连续两次稳定且进度条不忙 +
  有本轮编译证据（见过忙 / 计数变化 / 网格内容变化）"，任一不满足返回非 0;**CPU 不再涨只是旁证，不能单独当编译完成的证明**
  （[pitfalls §81](pitfalls.md)）。本轮重载后从 12 错收敛到 **0 错 / 0 警告**（当时实测）。
- **裸 `Ctrl+S` 不落盘**（表格里没关的下拉是独立顶层小窗会吃键盘），必须 `--menu` 走 `文件(F)>保存(S)`。
  落盘成功的判据是 `.smc2` 的 **sha256 变化且归档仍有效**：只有 `SAVED` 退出 0，文件消失/损坏判 `MISSING`/`INVALID`
  （[pitfalls §66](pitfalls.md)、[§81](pitfalls.md)）。
- 验收三件：① 目标 `.oem` 的 `ReferredLibraries`/`LibraryFilePath` 指向**新 `.slr`**；② 编译 **0 错 0 警告**；
  ③ 新库里确有功能标记（如按轴开关字段、新功能块名）。离线读 ZIP 即可核，不必再动界面。
  结构复核可加跑 `ss_verify.py <目标.smc2>`（普通格式配套文件齐全、任务关联不悬空；安全 CPU 实体只记 INFO），但它不替代 ② 的真编译实测。
- **库成员字节一致性（实测，主审独立只读 ZIP 核对）**：本轮库所属的 **125 个归档成员与原工程逐字节一致**——
  印证"只改目标 FB、守住其余成员字节不变"（[offline-surgery §10](offline-surgery.md) 的 `GUARDS`）确实做到。
  这是离线可核的结构证据，仍不替代 ② 的真编译与运行时实测。

### 7.5 收尾注意

- 库源 `.smc2` 若仍开在某个 Sysmac 实例里，它持有**改之前**的陈旧内存副本：从它保存/创建库会把磁盘补丁打回原形
  （[pitfalls §80](pitfalls.md)）。离线改完磁盘后，让该实例**从磁盘重开**或**不保存地关闭**，保证磁盘是唯一事实源。
- 被 Sysmac 开着的 `.smc2`/`.slr` **写锁定**，离线 `os.replace` 会 `WinError 5`；先关工程或改副本（§80）。


## 8. 看被引用库里的 POU 源码（含"源码可见"库的验收，2026-11-21 实测）

引用库（`.slr`）里的 POU **不在工程树里**，`ss_uimap.py open <树路径>` 够不着；库索引那张表又不暴露行（§2 更正）。
唯一稳定通道是"工具箱 → 右键实例 → 转到下层"：

```
1) 打开任一程序编辑器（梯形图即可）        ss_uimap.py open <pid> <out> 1.0.0.0.0
2) 工具箱出现库分组 ` <库名> ( <版本> )`    AutomationId='groupToggle'
   展开 → 列出该库全部 POU                  ss_libsrc.py <pid> <out> toolbox
3) 在梯形图上对**该库 FB 的实例**右键 → 菜单「转到下层」（Ctrl+Shift+L）
                                            ss_libsrc.py <pid> <out> goto <x> <y>
   菜单项按 Name Invoke（不是按坐标点菜单位置）
4) 打开 `<FB名> - <实例名>` 文档窗口
     Pane(DocumentWindow) → Custom(StructuredTextView) → Custom(SyntaxEditorView)
       → Text(AutomationId='textEditor', class='SyntaxEditor')
5) 取全文                                  ss_libsrc.py <pid> <out> text
   TextPattern.DocumentRange.GetText(-1)
```

判据与实测数字：

- `goto` 成功 = 出现新 `DocumentWindow`（脚本日志 `new_docs=[...]`）；没有就是坐标没落在实例上，或菜单项名变了
  （脚本会把抓到的菜单项全列出来，照着改 `--item`）。
- `text` 输出 = `<out>.st`（单编辑器）或 `<out>.<n>.st`（多编辑器），日志给 `chars/lines/sha256/首末行`。
  实测一个 FB：**整段源码**，与离线明文**逐字节一致**（只做 CRLF→LF 归一化）。
- `toolbox` 默认会自动展开折叠分组；**折叠分组不向 UIA 暴露子项**，`--no-expand` 时只拿到分组名。
- `text` 只对 ST 页有效：梯形图/变量表没有 `textEditor`，脚本会返回 1 并写明原因，不是故障。

保存后怎么离线复核"库确实是源可见"（不依赖 UI，直接读 `.smc2`）：

```python
# 1) 库引用旗标：LibraryModel 下是【元素文本】形式，不是属性
'<IsSource>true</IsSource>' in xml and '<IsDisableSourceDisplay>false</IsDisableSourceDisplay>' in xml
# 2) 源码已落盘：数 <StructuredTextModel> 实体，逐个取 <Text> 与离线明文比 sha256
# 3) 别被同名节点骗：<BuildOption> 下也有一个 LibraryModel（工程自身，Name=工程名、路径空），
#    它的 IsDisableSourceDisplay=true 属正常，不是"没改成功"
```

一次完整的"源可见"验收（2026-11-21 实测，全程副本只读 + 不保存关闭）：

| 项 | 实测值 |
| --- | --- |
| UI 全文 | 整段源码（行数与离线明文相同） |
| 与离线明文 | 逐字节一致（仅 CRLF→LF） |
| 工程内嵌 | 7 个 `StructuredTextModel`，最大者即该明文 |
| 库旗标 | `<IsSource>true</IsSource>` + `<IsDisableSourceDisplay>false</IsDisableSourceDisplay>` |
| 工程哈希 | 打开前/关闭后一致（未保存） |

## 9. 判型：先跑 `ss_libtype.py`，别手数标签（2026-11-21 实测）

判型是"解密 / 重建 / 编译体解析"三条路的分岔口，判错会把整条分析带偏。**先跑命令，再决定路线**：

```bash
python $S/ss_libtype.py "库.slr"              # 人读
python $S/ss_libtype.py "工程.smc2" --json     # 机器读
python $S/ss_libtype.py --selftest            # 11 项自检（含两个陷阱夹具）
```

输出长这样（真实文件）：

```
FILE    库.slr
        entries=49
TYPE    AES_HIDDEN    IsSource=true + IsDisableSourceDisplay=true + 有密文
FLAGS   IsSource=true  IsDisableSourceDisplay=true  IsBackwardCompatibleNoSource=(absent)  Password=(empty)
        model: Name='<库名>' Version=1.0.0 role=entity
BODY    EncryptedFile=7 (raw=0)  BuiltLibraryFile=0  StructuredTextModel=7  cipher=7 plain=0 built=0 empty=0
UNICODE Utf8=7
NEXT    常规库+禁显：走无源库解密流程 §4 解密（key/IV 由 EncryptionLock 自包含推导）
WARN    ESCAPING: 原始 XML 里 <EncryptedFile> 计数=0，html.unescape 后=7 —— 直接数原始 XML 会误判…
```

### 9.1 五个结论型别

| TYPE | 条件 | 走哪条路 |
| --- | --- | --- |
| `AES_HIDDEN` | `IsSource=true` + `Disable=true` + 有密文 | 解密（decrypt §4）；要交付可读库再走 rebuild |
| `AES_VISIBLE` | `IsSource=true` + `Disable=false` + **仍有密文** | **不用解**：Sysmac 自己解；但密文+钥匙都在库里，分发等于公开源码 |
| `NO_SOURCE` | `IsSource=false` 或 `NoSource=true`（通常伴 `BuiltLibraryFile`） | AES 失效 → 编译体解析；有明文参照 → rebuild 路径 c |
| `PLAIN_VISIBLE` | 无密文 + 明文 `<Text>` | 已是源可见库，直接导出/对照 |
| `UNKNOWN` | 没找到模型或旗标缺失 | 不猜，记录样本 |

### 9.2 两个必须知道的陷阱

1. **`<EncryptedFile>` 是 HTML 转义的**（实体 XML 里存成 `&lt;EncryptedFile&gt;`）。
   对原始 XML 数 `<EncryptedFile>` 得 **0** ⇒ 会误判"这个库没有加密源码"。
   工具内部先 `html.unescape`，并把 **raw 与 unescaped 两个计数一起打印**；两者不等时抛 `ESCAPING` 警告。
   **看到 `EncryptedFile=7 (raw=0)` 就是这条陷阱的现场。**
2. **`.smc2` 里有两个 `LibraryModel`**：`ReferredLibraries>ReferredLibrary` 下的是被引用库；
   `BuildOption` 下的是**工程自身**的构建选项（`Name`=工程名，`IsDisableSourceDisplay=true` 属正常）。
   拿错一个会把"源可见"判成"禁显"。工具按祖先链剔除 `BuildOption`，两者旗标不一致时抛警告。

### 9.3 顺带结论：有密文 ≠ 源码被隐藏

改旗标重建库样本`IsDisableSourceDisplay=false`，但 7 个密文 Body 与原库**逐字节相同**：

```
SAME  <lock 指纹>   (×7，全部 SAME)
```

即"改旗标"只放开显示，密文和钥匙都还在，Sysmac 现解现显示。所以：

- 想**自己看**、保持库形态 → 改旗标即可（`AES_VISIBLE`），体积几乎不变；
- 想**真交付源码**、不带走密文 → 必须走明文装配（`PLAIN_VISIBLE`），体积会明显下降（本例约降到三分之一）。

### 9.4 验收（五个真实样本）

| 样本 | TYPE | 关键计数 |
| --- | --- | --- |
| 常规库样本 | `AES_HIDDEN` | `EncryptedFile=7 (raw=0)` / `STM=7` |
| 无源码库样本 | `NO_SOURCE` | `0` / `BuiltLibraryFile=8` |
| 改旗标重建库样本 | `AES_VISIBLE` | `7 (raw=0)` / `Disable=false` |
| 无源码工程样本 | `NO_SOURCE` | `0` / `8` / `role=referred` |
| 明文装配工程样本 | `PLAIN_VISIBLE` | `0` / `STM=7` / `plain=7` |
