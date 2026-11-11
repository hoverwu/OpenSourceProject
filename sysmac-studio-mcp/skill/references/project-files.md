# 工程文件：新建 / 导入 / 另存为 / 导出 / 校验

Sysmac 的工程文件是 `.smc2`（本质是 ZIP）。所有文件级操作都在 `文件(F)` 菜单下，对话框是**原生 Win32 文件对话框**（类 `#32770`），不是 WPF。

## 1. 新建工程

入口两条，等价：

- 启动页 → `NewProjectToggle`（RadioButton）
- 已打开工程时 → `文件(F) > 新建`（未实测）

向导字段与定位见 [control-tree.md](control-tree.md#2-新建工程向导约-104-节点)。填完点 `CreateButton`（Name=`创建(_C)`）。

**成功判据**：主窗口标题变成 `<工程名> - <控制器名> - Sysmac Studio (64bit)`；`MainDockSite` 出现；`ss.py state` 能读到 `mode=Offline`。

**等待**：点创建后软件要生成工程（几百 ms ~ 数秒），轮询 `StatusBar` 的 `ProgressBar` 直到 0×0，再轮询标题变化，不要用固定 `sleep`。

> 向导里的"设备"三件套（类型 / 型号 / 版本）决定了工程里默认有哪些东西。型号是**分两级**选的：先系列，再具体型号；选完第一级，第二级 ComboBox 的选项会变。

## 2. 导入（整工程导入，会先关闭当前工程）

`文件(F) > 导入(I)...`（启动页左侧也有 `导入(I)...`）→ 原生打开对话框 → 选 `.smc2` → `打开(O)`。

实测行为（**重要**）：

1. **先关闭当前工程**，弹 `确定退出前保存工程?`（是 / 否 / 取消）；
2. 按文件的全部内容**建出一个新工程**；
3. 工程名自动加序号（源 `Demo` → 新 `Demo_2`）；
4. 作者 / 注释 / 类型**原样保留**（取自 `.smc2` 里的 solution xml）。

⚠ 第 1 步意味着：**内存里没另存到磁盘的工程会在这里永久丢失**。实测踩过一次——刚粘贴完 105 个 POU 的目标工程被清空。**导入前先 `文件>保存` 或 `另存为`。**

导入成功判据：标题里的工程名变成 `<原名>_<n>`；`ss.py state` 能读到新标题；工程树节点数恢复。

## 3. 另存为

`文件(F) > 另存为(A)...`，两步：

1. **工程属性**对话框：`工程名称`（可改）、`作者`（可改）、`注释`（可改）、`类型`（只读）、密码区（**不要碰**）→ `保存(S)`；
2. 原生保存对话框 → 选目录与文件名 → `保存(S)`（已存在会再弹 `确认另存为`）。

完成后：

- 主窗口标题变成新工程名；
- `作者` 写进 `.smc2` 内的 solution xml（可用下面的校验脚本核对）；
- 内存中的工程即绑定到新文件（后续 `保存` 写这个文件）。

> 想在"换名字/换作者"的同时保留原工程，用另存为是最省事的路径：它不会改动原文件。

## 4. 导出

`文件(F) > 导出(E)...` → 原生「导出文件」对话框：

- 已停在**上次使用的目录**；
- 文件名预填 `<工程名>.smc2`；
- 类型固定 `Sysmac Studio V1.08或更高的工程文件 (*.smc2)`；
- 点 `保存(S)`，若文件已存在 → `确认另存为`（`是(Y)` / `否(N)`）。

⚠ **覆盖确认框的坐标点击经常无效**（对话框位置会变）。用 UIA：

```bash
python <SKILL_DIR>/scripts/ss.py click <pid> 是(Y)
```

导出与另存为的区别（实测）：导出产出的是**当前内存状态的快照**，不改路径、不改标题；另存为会把工程切到新文件。

**控件名坑（实测）**：这个对话框里 `文件名:` 其实是 **ComboBox 套 EditControl**，里面那个 `EditControl` 的 UIA `Name` 也是 `文件名:`——**不是** `文件名(N):`。按 `文件名(N):` 找会得到 "no filename edit" 然后空手而归。稳定的取法是 **`AutomationId == '1001'`**。

**写文件名的正确姿势（实测，2026-10-30 修正）**：

```python
u.SetForegroundWindow(dialog)                        # 必须，否则键盘发给主窗口
ed = find(dialog, 'EditControl', aid='1001')         # 或退化为对话框里唯一的 Edit
click(ed); ctrl('a')                                 # 选中原名
set_clip('我的工程.smc2'); ctrl('v')                  # 中文只能走剪贴板
find(dialog, 'ButtonControl', aid='1').Click()        # 保存(S)
```

- ⚠ **`ed.GetValuePattern().SetValue(...)` 在 V1.68 会抛 `COMError -2147220992`**（该控件不实现 ValuePattern），旧版本笔记里"用 SetValue 写完整路径"是错的；
- ⚠ `SendKeys` 打不出中文；
- ⚠ 从命令行传 Windows 完整路径时反斜杠可能被 shell 吃掉（实测盘符后的分隔符全丢、变成盘符相对路径，软件弹 `文件名无效。`）——只传文件名，让对话框停在上次目录。

实测几何（125% DPI）：`保存(S)` (693,566,803,599)、`取消` (818,566,928,599)、文件名 Edit (169,434,921,456)、覆盖确认 `是(Y)` 在**另一个 `#32770`** 里 (988,541,1069,570)。坐标只作对照，实际按 AutomationId 取。

导出成功后判据：**mtime 变了 + `testzip()` 为 None**（同一工程重复导出大小会变，别拿"字节数相同"当失败）。

**导出的是内存快照**：若批处理中途改过数据类型/命名空间，导出前先编译一次再导出——实测出现过 18:46 的导出比内存**少 12 个数据类型页**（旧快照）的情况，容易被误判为"导出丢东西"。

## 5. `.smc2` 内部结构

```
<GUID>/<GUID>.oem                 实体索引（<Entity type="..."> 计数来源）
<GUID>/<GUID>.xml                 solution 元数据（<Author> / <ProjectType> / 注释 …）
<GUID>/<entities>/**.xml|.xaml|.png   每个实体一个文件
<GUID>/.stsdb4                    工程元数据数据库（二进制）
```

条目名里有 GUID 前缀，**跨文件比对时必须先规范化**，否则永远对不上。

## 6. 导出校验配方（强烈建议每次批量搬运后跑）

```python
import zipfile, re, hashlib, collections

def norm(n):
    return re.sub(r'^[0-9a-fA-F-]{36}', 'GUID', n)

def digest(path):
    z = zipfile.ZipFile(path)
    assert z.testzip() is None, 'zip CRC 损坏'
    hist = collections.Counter(n.rsplit('.', 1)[-1] for n in z.namelist())
    files = {norm(n): hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if not n.endswith('/')}
    oem = [n for n in z.namelist() if n.endswith('.oem')][0]
    ents = collections.Counter(re.findall(r'<Entity type="([^"]+)"', z.read(oem).decode('utf-8', 'replace')))
    return hist, files, ents

h1, f1, e1 = digest('source.smc2')
h2, f2, e2 = digest('export.smc2')
print('条目类型差异:', h1 - h2, h2 - h1)
print('仅在源:', sorted(set(f1) - set(f2))[:10])
print('仅在新:', sorted(set(f2) - set(f1))[:10])
diff = [k for k in f1.keys() & f2.keys() if f1[k] != f2[k]]
print('内容不同:', diff[:10], '共', len(diff))
print('实体计数差异:', e1 - e2, e2 - e1)
```

判读标准：

- 条目类型直方图一致；
- 规范化名字集合一致；
- `.oem` 里各类 `<Entity type>` 计数一致；
- **允许不同**的只有：`.stsdb4`（工程元数据）、`NexBuildVerifierGroup`（时间戳类）；
- `testzip()` 必须返回 `None`。

一个真实基准（供量级参考，不是标准）：源 7,627,924 B / 导出 7,628,443 B；1392 xml、808 xaml、133 json、133 png、9 svg；`Program 9`、`Function 16`、`FunctionBlock 80`、`PouBody 126`、`Variables 107`、`DataType 58`、`NexEcatConfiguration 2`、`NxCpuRack 3`、`HmiPage 32`；2506 条条目逐字节相同——**字节数不同但内容几乎全同**，说明体积差异来自元数据/时间戳，不一定是丢东西。

第二个真实基准（**逐项手工重建**，2026-10-30，带设备/ECAT/安全的源工程 → 只搬 POU 的新工程）：

| 指标 | 源 | 重建 |
| --- | --- | --- |
| 源文件 | 3.6 MB / 1548 条目 | 2.5 MB / **318 条目** |
| Program | 11（含 5 个安全程序） | 5 |
| Function | 26 | 23（3 个被编辑保护） |
| FunctionBlock | 49 | 49 |
| PouBody | 97 | 87 |
| Variables | 88 | 78 |
| DataType | 35 | 15（20 个属于安全/被保护 POU/设备结构） |
| Group | 37 | 11（分组层级没重建） |
| NexEcatConfiguration / NexNXBusConfiguration | 49 / 137 | 2 / 2（**设备组态缺失**） |
| 编译 | — | 6890 错误 / 1033 警告，绝大多数是 `地址不合法。` |

**判读**：这种差距不是"漏搬"，是**架构限制**（POU 剪贴板不携带设备组态/安全应用/被保护 POU）。写重建成报告时要按类别交代，不要声称"逐字节一致"。

顺带一条 `.smc2` 文本格式的实用知识：全局变量在 XML 里就是一行行 `++D=<数据类型> N=<名称> AT=<地址> Const=1 G=VAR_GLOBAL`。
**没有 `N=` 字段的那行就是"空名变量"**——也就是说界面里删不掉的无名行已经写进文件了，会稳定贡献一条 `变量名是空。` 编译错误（见 [pitfalls.md §22](pitfalls.md#22-变量表里名为空的行删不掉而且会被导出)）。

## 7. 完整搬运流程（把一个工程复制成另一个工程）

实测可行的组合（配置部分只能整体带过去）：

```
1. 关闭/备份：确认源工程已在磁盘上
2. 文件 > 导入(I)... 读源 .smc2        → 得到完整副本 <原名>_<n>
3. 文件 > 另存为(A)...                 → 改工程名 + 作者，落到目标目录
4. 按需在副本里删/改（删除前核对内部名）
5. 文件 > 导出(E)...                   → 目标 .smc2
6. 跑 §6 校验                          → 条目/实体计数与源一致
```

如果只是要"程序与功能块"，用工程树的 `编辑>复制/粘贴` 或 [多选复制](project-tree.md#6-多选复制批量搬-pou的主路径) 更直接；但**配置带不过去**（见 [project-tree.md](project-tree.md#7-搬不动的东西实测结论不要再重复试)）。
