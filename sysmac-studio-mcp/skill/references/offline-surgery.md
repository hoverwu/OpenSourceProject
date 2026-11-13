# 文件层面的实体移植（`.smc2` / `.slr` 是 zip）

> 适用场景：**界面剪贴板搬不动的组态**（EtherCAT、NX 总线、安全 CPU、机架单元、轴设置）。
> 这不是"绕过软件"的黑客手段，而是利用它自己的文件格式：**产出的文件仍然要能被软件打开、编译、导出**。改动前先备份，改完必须复验（§7）。

实测环境：Sysmac Studio V1.68 64bit / Windows 11。结论标注了"实测"，没标的按未验证对待。

## 1. 容器结构

一个 `.smc2` 就是 zip：

```
<SolutionGUID>/
  <SolutionGUID>.oem            ← 实体树（纯 XML，BOM + <?xml ...?>）
  <SolutionGUID>.xml / .log / .manifest / .ValidationResults / ...
  <EntityGUID>.xml|.dat|.model|.conn|.element|...   ← 每个实体自己的数据，基名 = 实体 id
  ...（还有别的 GUID 目录，比如库、安全工程）
```

`.oem` 的骨架：

```xml
<?xml version="1.0" encoding="utf-8"?>
<sysmac schemaVersion="1">
  <Entity type="Solution" subtype="" id="..." name="工程名" DN="..." SDName="...">
    <AccessInfos/>
    <ChildEntities>
      <Entity type="Group" ...>
        <ChildEntities>
          <Entity type="NexEcatConfiguration" .../>
        </ChildEntities>
      </Entity>
    </ChildEntities>
  </Entity>
</sysmac>
```

要点（实测）：

- **文件基名 = 实体 `id`**。搬一个实体的前提是把它 `id` 开头的所有配套文件一起搬。
- 属性区别：`type` 是实体类别（`NexEcatConfiguration` / `Device` / `DataType` / `Group` / `Program` …）；`subtype` 为空且 `type='DataType'` 的节点是**数据类型页**，`namespace` 属性是它的命名空间名。
- 子树内部的 GUID 引用**自洽**，整段搬过去照样能用；跨工程的外部 GUID 引用（实测源有 1328 处）在副本里 0 命中，加载时被忽略，**不用管**。

## 2. 操作流程（四步）

```python
import zipfile, xml.etree.ElementTree as ET

# 1) 读两边 .oem
def read_oem(z):
    name = [n for n in z.namelist() if n.endswith('.oem')][0]
    return name, ET.fromstring(z.read(name).decode('utf-8-sig'))

# 2) 在源里选子树，收集 id
ids = set()
def walk(e):
    if e.tag.endswith('Entity'):
        ids.add(e.get('id'))
    for c in e: walk(c)
walk(src_subtree)

# 3) 在副本 .oem 里替换/追加该子树（ElementTree 直接 insert/remove）

# 4) 写回 zip：.oem 必须带 BOM 和声明，配套文件按基名前段命中 ids 拷贝
new_oem = b'\xef\xbb\xbf<?xml version="1.0" encoding="utf-8"?>\r\n' + ET.tostring(croot, encoding='utf-8')
for n in src.namelist():
    base = n.rsplit('/', 1)[-1]
    if base.split('.')[0] in ids:
        zo.writestr(folder + '/' + base, src.read(n))
```

参考实现均为外部一次性脚本（不随 Skill 发布）：EtherCAT / 安全 CPU 子树移植、删重复数据类型页、改 POU 体文本——做法就是上面四步，按目标实体类型换定位条件即可。

## 3. 几个实测案例

| 目标 | 源里的定位 | 规模 |
| --- | --- | --- |
| EtherCAT 组态 | 源 `ChildEntities` 下 `type='NexEcatConfiguration'` 的节点（一个网络 = 一个节点） | 251 id / 158 文件 |
| 安全 CPU | `NXBus0`（`type='NexNXBusConfiguration'`）下 `type='Device' name='new_SafetyCPU0'` | 197 id / 509 文件 |
| 删除重复数据类型页 | `Group`（数据）下 `type='DataType' subtype='' name='数据类型2x'` | 13 页 / 26 id |
| 补被保护功能 | `type='Function'` 节点 + 其 `PouBody`/`Variables` | 每支 4 文件 |

安全 CPU 子树里含 `SafetyMasterConfiguration`、16 个 `LogicalExchangeDevice`、`SafetyTaskGroup`、`SafetyApplication`、`SafetyFiles`、`ILX0..ILX96`。**它缺了，`S` 地址类报错不会消失**（实测 97 条）。

## 4. 改不动的地方

- **加密 `PouBody`**：`<EncryptedFile><EncryptionLock ...>` 的 POU 体，文本层改一个字节都让引用失效。
  - 推论：**不要靠改 FB 声明来解决参数名不一致**，改**调用点**（调用点一般在别的 POU 的文本体里，可改）。
  - 实测：`FB_AxisGenm` 参数 `diMasterNum` vs 副本的 `iMasterNum`，改调用点 24 处即成。
- **同名实体撞车时先看归属**：两组同名的数据类型页往往一套来自被引用库、一套是程序自建；删错那套会把库侧类型一起弄坏。判据是它们挂在不同 `Group` 下，`namespace` 与结构体集合完全重合。
- **`Program` 壳与任务分配点耦合**：单拷 `Program` 节点而不拷分配关系，会让树/计数不一致。

## 5. 为什么能这么干（正确性边界）

软件加载时按 `.oem` 建实体树，再按实体 id 找自己的配套文件；**它不校验"这批实体是不是本工程原生创建"**。所以实体能"换血"，但代价是：

- 你看不到任何 UI 提示，错了只会表现为"打开失败 / 编译一堆错 / 编辑器空"；
- 一旦格式细节记错（BOM、命名空间、属性名），软件可能**静默丢实体**而不是报错——所以必须做 §7 的复验。

## 6. 与界面路线的关系

| 需求 | 界面 | 文件移植 |
| --- | --- | --- |
| 搬 POU（程序/功能/功能块） | ✅ 剪贴板可用（被保护的除外） | 可用但没必要 |
| 搬 EtherCAT / NX 总线 / 安全 CPU / 机架单元 | ❌ 5 条路径全失败 | ✅ 实测可行 |
| 学"软件怎么操作" | ✅ 唯一途径 | ❌ 学不到控件与流程 |

**不要把文件移植当成"学会了组态"**：它跳过的是你对 `EtherCAT 编辑器`、`CPU·扩展机架` 等界面的理解。做通用 Skill 时，界面路线仍是主线，文件路线作为"界面搬不动时的兜底"。

## 7. 复验清单（缺一不可）

1. `zipfile.ZipFile(p).testzip()` 返回 `None`；
2. 条目数、实体数、按类型计数与预期一致（思路：遍历 `.oem` 统计 `type`）；
3. **软件能打开**（`ShellExecute` 交给默认程序即可，会起新实例）；
4. **软件能编译**：`编译控制器` → 面板头部 `0 错误`;
5. 用软件自己 **导出一次**，交付的是导出产物而不是手工 zip——导出会重排签名/元数据（`Solution` id 会换新，并会补一个 `SafetyProject` 实体，属正常）。

## 8. 从零新建 POU（ST 功能块 / 程序）+ 任务 —— 实测可行（2026-11-06 修订）

参考实现为外部一次性注入脚本（不随 Skill 发布）：读 `*.st`
声明段生成 SLWD 变量表与实体树，向 `.smc2` 追加实体与配套文件。

实测：向某库工程 `.smc2`（`ProjectType=LibraryProject`）注入
2 个 ST 功能块 + 1 个程序（ST 代码放在多段梯图的**内联 ST 块**里）+ 1 个 200 ms 任务
→ 打开正常，`编译控制器` **0 错误 0 警告**（面板 0/0 + 错误网格 0 行 + 错误跟踪日志 0 新增字节）。
库工程本身原先是 0 个 `Program` 实体，说明库工程可以承载程序实体。

### 8.1 实体骨架

| 层级 | type / subtype | 配套文件 | 要点 |
| --- | --- | --- | --- |
| 功能块 / 功能 | `FunctionBlock` / `StructuredText`、`Function` / `StructuredText` | — | 挂 `功能块` 组（`121a614c-…`）下 |
| 程序 | `Program` / **`MultipartLadder`** | — | ★ 这是本节最容易错的一条，见 §8.4：`StructuredText` 不是合法的程序 subtype |
| 程序变量表 | `Variables` / **`Ladder`** | `<vars-id>.xml` | 子实体**只有** `SourceHolder`（**没有** `PouIFLibraryHolder`）；文件仍是 SLWD 纯文本 |
| FB/函数变量表 | `Variables` / `StructuredTextFunctionBlock`、`StructuredTextFunction` | `<vars-id>.xml` | 子实体 `PouIFLibraryHolder` + `SourceHolder`；SLWD 纯文本、CRLF、无 BOM |
| ST 本体（FB/函数） | `PouBody` / `StructuredText`，**version="0.2"** | `<body-id>.xml` | 子实体 `SourceHolder` + `PouBodySourceHolder`；version 写 `"0"` ⇒ 报“必须存在至少1行有效代码(注释除外)” |
| 段（程序） | `PouBody` / `Ladder`，`name` = 段名（`PrgMain`/`Config`/…） | `<body-id>.xml` | 子实体 `SourceHolder` + `PouBodySourceHolder` + **`Inline` / `StructuredText`**（`name` = ST 块 EID） |
| 源名链接 | `PouBodySourceHolder` | `<pbsh-id>.xml` | `FileNameWithoutExtension` = `FB_`（程序沿用 `Fn_`）+ 该 POU 的 trackingId 去横线 |
| 调试设置 | `DebugProgramSetting`（仅程序） | `<dbg-id>.xml` | `<data><DebugProgramSetting Flag="False" /></data>`，BOM |
| 书签 | 随本体 | `<body-id>.BookmarkGroup` | 空 `<Bookmarks/>`；**可省**（程序本体没有也能编译，实测某引用库的 `MachineState_A` 就没有） |

ST 本体（FB/函数）文件格式：`<StructuredTextModel xmlns="…StructuredText.Core" …><Text>…</Text></StructuredTextModel>`，
换行写成 `&#xD;` 加真实换行，`<` `>` 做 XML 转义（软件读入时正常解码）。

程序的段文件是**梯图 JSON**（UTF-8 带 BOM，行尾 `\r\n`），ST 代码放在一个 `IST` 块里：

```json
{"CLs":[{"__type":"IST","EID":"<ST 块 EID>","H":130,"TXT":"<ST 源码，内换行转义为 \r\n>","W":400}],
 "CMT":"STMultiSection(<同一 EID 的大写>)","LRI":1,"RRI":2,"VLs":[]}
```

`__type` 只能是 `IST`（内联 ST）；`ST` 是变量框（`{"__type":"ST","Var":"Info_Dumb"}`），
把源码塞进去不会被编译。段名、段数都自由（真实工程用 `PrgMain`/`Config`/`Region`）。

程序实体 `version="0"` 合法；`usingNamespaces` 可省。

### 8.2 ST 语法必须按 Sysmac 收口

工程内 41 个既有 ST 本体共 205 处 `END_xx`，**100% 带分号**：

- `END_IF` / `END_FOR` / `END_CASE` / `END_WHILE` / `END_REPEAT` 后必须带 `;`（IEC 通用写法可省）。
  缺分号只报 `缺少‘;’`，还会在同段连带报一串 `未定义的标识符` / `错误语法‘<’`，很容易误判成变量表没载入。
- 不支持嵌套调用 `MIN(MAX(a,b),c)`：报 `无效的输入参数组合`；两参数的 `MAX(…)` / `MIN(…)` 正常。
  限幅一律写显式 `IF x < lo THEN x := lo; END_IF;`（顺带解决跨平台参数顺序差异）。
- `VAR_INPUT` 在 FB 内部只读：给输入赋值报 `输入变量‘x’不能被赋值`，先拷到局部变量再限幅。
- **不做隐式窄化转换**：`LREAL` 赋给 `REAL` 报 `无法将LREAL转换为REAL`，必须写
  `REAL_TO_…` / `LREAL_TO_REAL(…)`。反方向（`REAL` → `LREAL`，例如把 `REAL` 实参传给
  `LREAL` 形参）是允许的，所以只有"从 FB 取出 LREAL 输出"这一侧需要显式转换。

### 8.3 任务

`NexTask` 实体挂 `任务` 组（`dfe133d9-…`），配套 `<task-id>.xml`：
`TaskExecutionCondition` 是周期**微秒**（200 ms → `200000`），`ExecutionPriority` 4=主周期 / 5=周期任务；
`<AssociatedProgramData ProgramName="…" IniFileTrackingId="<程序 trackingId 去横线>" SequenceNumber="1" />`。

### 8.4 错误模型的真实症状与"假 0 错"（2026-11-06 定位）

把程序写成 `Program / StructuredText` + `Variables / StructuredTextProgram`（旧版本文档的错误结论）时：

- 工程树能看到程序节点、能打开、能"编译"；
- 程序体里**每一个变量**都报 `未定义的标识符`（本次 37 条），但 FB 内部的变量正常；
- 错误跟踪日志 `%APPDATA%\OMRON\CXAP\Log\SysmacStudioErrorTrace.log` 里出现：
  `Extended data is not an instance of VariableGroups`（`NexSSLightweightDataVariableFormatter.SaveVariables`）、
  `PouIFsRule.UpdateEntityTargetResult` 的 `KeyNotFoundException`、`NexSTBuilderService` 的 `Invalid source`。
  这三条就是"变量表实体没被识别"的铁证，比界面上的错误文本更直接。

**假 0 错**：外部一次性后台编译脚本用"CPU 静默"判结束，若编译根本没跑起来（Invoke 未生效、
模态窗挡住、编译按钮没点上），它会在 20~40 s 后照样打印"编译结束"并读到 **0 行**错误。
本轮就出现过 `xP := ;` 的故意语法错仍显示 0 行。判据必须是三条同时成立：

1. 启动判据：编译开始后 CPU 时间明显增长（本次 8~50 s，视工程大小）；
2. 面板计数：`N 错误 / M 警告` 两个数字都读到；
3. **错误跟踪日志在编译前后的字节差为 0**（先记 mark，编译后比对；`trace_mark*.txt` 的写法见 §8.5）。

只满足"0 行"不算通过。

### 8.5 落盘与验证流程（本次实际执行）

1. 跑外部注入脚本 `--out <原名>_pipe<N>.smc2` —— 生成工作副本（会丢掉
   `.NexBuildResults` / `.NexBuildVerifierGroup` / `.NexTransferInformation` 三类编译缓存）；
2. 提权执行"重开工作副本 → 后台编译"（外部一次性脚本），对照日志三条判据；
3. 全部通过后，把正式工程**备份**成 `…bak-<yyyyMMdd-HHMM>.smc2`（`sha256` 核对备份与原件一致）；
4. `copy2` 工作副本覆盖正式工程，核对 `sha256` 相等、条目数 253 → 262；
5. 重新打开**正式工程**再编译一次（不是只看副本），仍满足三条判据才算交付。

## 9. 注入 DUT / 改库源 FB 的三条编译硬规则（2026-11-12 真实编译验证）

给库源工程注入新数据类型（DUT）或改已有 FB 时，下面三条任一不满足都会编译报错；
都已用"改→真编译→读错误列表"二分定位并修复到 0 错 0 警告。

1. **DUT 字段 `InitialValue` 必须用 IEC 带类型前缀字面量**：`LREAL#0.0`、`BOOL#FALSE`、`INT#0`。
   裸字面量（`0.0` / `FALSE` / `0`）报「初始值与数据类型不匹配」。留空能编译但**没有默认值**。
   注意区分：**SLWD 变量表**（POU 的 VAR 段）接受裸字面量（另一套解析器），只有 **DUT 字段**要带前缀。
   枚举字段的 IV 留空 = 默认 0。
2. **常量 IN_OUT 实参只能传给带常量属性的 IN_OUT 形参**：源 FB 的 `stAxisName` 若 `Const=1`，
   把它传进新 FB 的 `Axis`（`VAR_IN_OUT`）时，新 FB 的 `Axis` 行也必须加 `Const=1`
   （照 `MC_MoveAbsolute.Axis` 的写法：`++D=_sAXIS_REF N=Axis Ord=0 Const=1 G=VAR_IN_OUT`），
   否则报「带有常量属性的变量不能被指定为没有常量属性的输入-输出变量的参数」。
3. **混合 ENUM+STRUCT 的 DUT 容器根必须 `<data Version="1">`**：枚举用 `BaseType="ENUM"` 容器
   （成员 `BaseType="DINT" EnumValue="N"`），结构体 `BaseType="STRUCT" OffsetType="NJ"`，
   数组 `BaseType="ARRAY[0..n] OF T"`。根版本不对时混合 DUT 解析失败。

按轴开关的推荐形态：在已有轴 FB 的配置结构体里加 `xVibEnable : BOOL := FALSE`，
FB 体内 `IF stAxisCom.stConfig.xVibEnable THEN <新分支> ELSE <原逻辑> END_IF`。
默认 OFF ⇒ 不启用时对所有轴零行为变化，启用才走新分支；这样改库源不会破坏存量调用。

## 10. `.slr` 离线补丁：重建后把 FB 接口对齐到目标所依据的已编译库（2026-11-13 实测）

`创建库` 从库源重建出的 `.slr`，其 FB 形参名跟着**库源**走；若目标工程的调用点依据的是**另一份已编译库**
（形参名有漂移，见 [pitfalls §78](pitfalls.md)），就要在重建出的 `.slr` 上做一次**离线、scoped** 的改名，
而不是回库源界面逐个改形参（界面改 FB 接口既慢又容易误伤别的 FB）。

**为什么能离线改**：`.slr` 是个 ZIP，**没有校验和 / 清单**，软件在"重新引用"时才读它（§79）。
所以直接改 ZIP 里的条目是安全的，改完强制重载即可。

**条目形态**（与 `.smc2` 同构，见 §1）：
- 实体索引在 `<GUID>.oem`（小写 name/id；type=FunctionBlock/Variables/PouBody/DataType/Library）。
- POU 的**接口**与**体**各是一个 `<GUID>.xml`；接口可能是 SLWD 文本（`[SLWD version=1.0]`，`++D=<类型> N=<名> … G=VAR_INPUT`），
  体可能是 XML（`<VariableGroup>`/`<Variable Name="…">`）或内联 ST。**同一个 FB 的接口/体 GUID 在源工程与重建库里一致**，按基名命中。
- POU 主 `<guid>.xml` 常是 **148 字节的 `<NullObject>` 桩**——正常，真正内容在子 xml，别以为坏了。
- **库根实体 GUID 每次建库都不同**（pristine 与重建库的根 id 不一样），这是正常的，不要试图对齐它。

**改名 + 校验配方**（可复用，全程离线、不碰控制器）：

```python
import zipfile, re, os, shutil
VIB      = r'<重建出的.slr>'           # 要改的交付库
PRISTINE = r'<目标原先依据的已编译.slr>'  # 只读基准，绝不覆盖
TARGETS  = ['<FB接口GUID>.xml', '<FB体GUID>.xml']   # 只改这一个 FB
GUARDS   = ['<别的FB接口GUID>.xml', '<别的FB体GUID>.xml']  # 必须保持字节不变
BACKUP   = r'<备份.slr>'

def rename(b):
    bom = b.startswith(b'\xef\xbb\xbf')
    d = b.decode('utf-8-sig')
    d = re.sub(r'(?<!d)iMasterNum', 'diMasterNum', d)   # 负向后顾：已是 di 的不再改
    d = re.sub(r'(?<!d)iSlaveNum',  'diSlaveNum',  d)
    out = d.encode('utf-8')
    return (b'\xef\xbb\xbf' + out) if (bom and not out.startswith(b'\xef\xbb\xbf')) else out

ID_RE = re.compile(rb' Id="[0-9a-fA-F-]+"')             # 每变量 Id 每次建库重生，比较前归一化
norm  = lambda b: ID_RE.sub(b' Id="X"', b)

zv = zipfile.ZipFile(VIB); zp = zipfile.ZipFile(PRISTINE)
infos = zv.infolist(); patched = {}
for ent in TARGETS:
    n  = [x for x in zv.namelist() if x.endswith(ent)][0]
    pn = [x for x in zp.namelist() if x.endswith(ent)][0]
    new = rename(zv.read(n)); ref = zp.read(pn)
    # 体要求字节全等；接口允许只差 Id GUID
    assert new == ref or norm(new) == norm(ref), ent   # 不满足就 abort，绝不写
    patched[n] = new
guards = {g: zv.read([x for x in zv.namelist() if x.endswith(g)][0]) for g in GUARDS}
if not os.path.exists(BACKUP): shutil.copy2(VIB, BACKUP)
tmp = VIB + '.tmp'
with zipfile.ZipFile(tmp, 'w') as zo:
    for it in infos:                                   # 保持条目顺序 + 每条原压缩方式
        zo.writestr(it, patched.get(it.filename, zv.read(it.filename)), compress_type=it.compress_type)
zv.close(); os.replace(tmp, VIB)                       # 目标被 Sysmac 开着会 WinError 5，见 §80
# 复验：TARGETS 纯 i 名=0、di 名=预期数；GUARDS 字节全等；条目总数不变
```

**硬约束**：
1. **scoped**：只改目标 FB 的接口+体；别的 FB（哪怕也有 `iSlaveNum`）必须**字节全等**地守住——它可能是合法的 `INT` 形参，调用点就用 `i` 名。
2. **保 BOM / 压缩方式 / 条目顺序**：`utf-8-sig` 解码、按原 `compress_type` 写回、按 `infolist()` 顺序遍历。
3. **Id 归一化再比**：体字节全等、接口归一化后全等才认；任一不满足 **abort 不写**（先备份）。
4. 改完磁盘**必须强制重载引用**（§79 删旧行+重加），否则编译仍用旧缓存、错误一条不少。
5. 目标 `.slr` 若正被 Sysmac 开着，`os.replace` 会 `WinError 5`（§80）；先关工程或改副本。
