# 报警与趋势页：JSON 导出 / 导入全过程（实测记录）

作者：hoverwu ｜ 版本：1.0.0 ｜ 日期：2026-11-07 ｜ 适用：EasyBuilder X V1.01.376s / cMT3075XH / 1024×600

本文记录「把报警与趋势那一页导出成 JSON，再导入另一台电脑的 EasyBuilder X」这件事**实际是怎么做的**，包括用到的命令、真实输出、校验方法与两条导入路线。配套文件：

| 文件 | 说明 |
| --- | --- |
| `out/Alarm_Trend.screen.json` | 导出的画面数据（schema `ebx-screen/1.0`，20,274 B） |
| `tools/export_screen_json.py` | 导出器（规格 + 标签表 → JSON） |
| `tools/validate_screen_json.py` | 校验器（本次新增，可独立运行） |
| `tools/ebx_screen_importer.py` | 导入器（JSON → UIA 重建画面） |
| `out/ebx_screen_importer.py` | 导入器便携副本（单文件，可随 JSON 一起拷走） |
| `out/IMPORT_README.md` | 迁移包说明（前提、参数、排错） |

---

## 0. 结论先说

1. **EasyBuilder X 没有画面级 JSON 导入导出**。打开对话框只认 `.ebxprj` / `.ebxobj`；官方结构化交换只有字符串表 CSV/XLSX、宏 `.ebm`、审计 CSV、图片。所以 JSON 是**我们自己定义的中间格式**，导入靠 UIA 驱动界面重建。
2. 导入有两条真正能走通的路：
   - **路线 A：原生复制/粘贴** —— 同版本、目标工程已有同名设备与标签时最省事，样式全保留；
   - **路线 B：JSON + 导入器** —— 可留档、可版本管理、可跨机器重建，样式取 EBX 默认值。
3. 导出不是"从 `.ebxprj` 里解析"（工程是加密容器），而是从**构建规格 `work/hmi_spec.json` + 标签表 `work/tags/PipeTags.txt`** 生成；这两个文件与工程内实际落点一致（元件按同一套坐标生成）。

---

## 1. 导出的过程

### 1.1 输入数据

| 输入 | 内容 |
| --- | --- |
| `work/hmi_spec.json` | 本工程的画面构建规格：每页元件的类型（文本/数值/指示灯/按钮）、名称、x/y/w/h、文本内容、绑定变量、切换画面任务 |
| `work/tags/PipeTags.txt` | 从 Omron NJ/NX 导出的变量表（制表符分隔：NAME / DATATYPE / ADDRESS / COMMENT），共 38 条 |

### 1.2 命令

```bat
cd /d "<项目根>"
python tools\export_screen_json.py 报警与趋势 out\Alarm_Trend.screen.json
```

第二个参数可省略，默认写到 `out\Alarm_Trend.screen.json`。

### 1.3 输出摘要（本次实际结果）

```json
{
  "out": "out/Alarm_Trend.screen.json",
  "screen": "报警与趋势",
  "elements": 40,
  "by_type": { "static_text": 20, "indicator": 9, "numeric_display": 8, "button": 3 },
  "tags": 38,
  "used_tags": 17
}
```

- 40 = 页面原有 37 个元件（20 文本 + 9 灯 + 8 数值）+ 3 个导航按钮；
- 38 条标签清单全部带进 JSON，本页实际使用 17 条；
- 文件 20,274 B，UTF-8 无 BOM，换行 LF。

### 1.4 结构要点

| 层级 | 字段 | 说明 |
| --- | --- | --- |
| 顶层 | `schema` / `generator` / `source_project` | `ebx-screen/1.0`；generator 记录工具版本、作者、导出时间 |
| 顶层 | `target` | 版本、机型、画面尺寸、缩放 |
| 顶层 | `device` | 设备名 PLC_NX502、驱动、IP、寻址方式（CIP 变量名） |
| 顶层 | `tags[]` / `used_tags[]` | 全部变量 / 本页实际使用 |
| 顶层 | `import` | `native_json_support: false` + 前提 + `style_policy` |
| `screen` | `name` / `width` / `height` / `element_count` / `elements[]` | 元件字段：`id` / `type` / `ebx_kind` / `name` / `x` / `y` / `w` / `h`，可选 `text` / `tag` / `readonly` / `label` / `task{type,target}` |

### 1.5 导出后的校验（必做）

```bat
cd /d "<项目根>"
python tools\validate_screen_json.py out\Alarm_Trend.screen.json --screens 报警与趋势,主监控,参数设定,手动维护
```

本次实际输出：

```json
{
  "file": "out/Alarm_Trend.screen.json",
  "ok": true,
  "screen": "报警与趋势",
  "elements": 40,
  "tags": 38,
  "used_tags": 17,
  "tasks": 3,
  "errors": []
}
```

校验器覆盖 6 项：schema 与 `element_count` 一致、`id`/`name` 唯一、元素引用的标签都在 `tags[]` 内、`used_tags` 与元素实际用到的集合完全一致、所有元件在 1024×600 边界内、`switch_screen` 目标画面存在（3 个任务分别指向 主监控 / 参数设定 / 手动维护）。

> 建议把这两步（导出 + 校验）一起跑；`ok: true` 再拷文件，避免把半成品带到目标机。

---

## 2. 导入路线 A：原生复制 / 粘贴（最省事，保样式）

适用：目标机与源机同版本 EBX，且目标工程已有**同名设备**与**同名变量**；只需要搬一页。

1. 源机打开 `.ebxprj`，双击画面树里的「报警与趋势」进入编辑器。
2. 在画布空白处点一下 → `Ctrl+A` 全选 → `Ctrl+C`。
3. 目标机打开目标工程，**先新建一个 1024×600 的画面**（画面树右键 → 插入画面；尺寸必须一致，否则粘贴会错位/裁切）。
4. 点新画面画布 → `Ctrl+V`。
5. 逐个核对：
   - 数值/指示灯的「标签」是否绑定成功（未绑定会空白或显示异常）；
   - 3 个导航按钮的任务目标是否是本工程里存在的画面；
   - 指示灯颜色、文字格式是否保留（路线 A 会保留）。
6. `Ctrl+S` 保存 → 编译 → 离线模拟点一遍导航。

注意：

- 跨工程粘贴按**变量名**匹配，名字不一致就变成未绑定，需要手动重绑；
- 导航任务里可能带着源工程的内部画面 ID，跨工程后必须逐个重开任务对话框确认；
- 画面树不能拖动排序，启动页恒为"最先创建"的画面；
- 删除被导航任务引用的画面会换内部 ID，操作前先备份 `.ebxprj`。

---

## 3. 导入路线 B：JSON + 导入脚本（可跨机器、可复现）

### 3.1 目标机准备（缺一不可）

1. Windows + **EasyBuilder X V1.01.376s**（其他版本 Ribbon 坐标不同，需重新标定）；
2. EBX 打开目标工程，主窗**最大化**，屏幕 1920×1080、缩放 100%，左右面板默认布局；
3. 目标工程已有设备 **PLC_NX502**（Omron EtherNet/IP NJ/NX），并导入 JSON `tags[]` 里的同名 CIP 变量；没有标签就先跑 `--no-bind`；
4. Python 3.8+ 与 `uiautomation`：
   ```bat
   pip install uiautomation
   ```

### 3.2 操作步骤

```bat
cd /d "拷贝后的目录"
python ebx_screen_importer.py Alarm_Trend.screen.json --limit 8 --no-save
```

先小样试跑：核对 8 个元件的坐标、文本、绑定是否正常；日志里两次标定的原点应一致（`[calib] origin1 == origin2`，本机为 `(245,309)`）。

确认无误后跑全量：

```bat
python ebx_screen_importer.py Alarm_Trend.screen.json --screen 报警与趋势_导入验证
```

参数：`--screen 名称` / `--force`（同名时新建副本）/ `--no-bind` / `--no-nav` / `--limit N` / `--no-save` / `--probe-ribbon`。

**运行期间不要动鼠标键盘，也不要切走 EBX**；任何模态框都会让脚本卡住。每元件约 30~60 秒。

### 3.3 本机实测（2026-11-07，全量）

- 把 `Alarm_Trend.screen.json` 重建为「报警与趋势_导入验证」；
- **40/40 元件成功**（20 文本 / 9 灯 / 8 数值 / 3 按钮）；
- **17/17 标签绑定 ok**；
- **3/3 切换画面任务 ok**（主监控 / 参数设定 / 手动维护，且重开任务对话框复核过）；
- **3/3 按钮文字 ok**；
- 耗时 ≈29 min（19:49 → 20:18）；截图与原页布局一致；
- 验证后删除该画面并保存，工程仍是 4 页。

日志结束标志：`[ok] 已重建 40 个元件到画面 报警与趋势_导入验证`。

### 3.4 用 MCP 通道跑（推荐，能被 Agent 直接调度）

服务端已把这套流程封装成工具（v0.2.0，共 24 个）：

```bat
cd /d "<项目根>"
start-ebx-mcp.bat
```

客户端注意：若 `NO_PROXY` 含 `[::1]`，httpx 会抛 `InvalidURL: Invalid port: ':1]'`，先清空：

```bat
set NO_PROXY=
set no_proxy=
python ebx-mcp-smoke-test.py 8788
```

单次调用（本次实测：`limit=1` 试跑，不绑标签、不建导航、不保存）：

```bat
python tools\mcp_call_once.py ebx_import_screen_json "{\"json_path\":\"out/Alarm_Trend.screen.json\",\"screen\":\"临时_导入测试\",\"limit\":1,\"no_bind\":true,\"no_nav\":true,\"no_save\":true,\"wait\":170}"
```

返回：

```json
{
  "ok": true, "pid": 9828, "screen": "临时_导入测试", "elements": 40,
  "schema": "ebx-screen/1.0", "log": "...\\out\\import_20261107_204815.log",
  "found": true, "running": false, "target": "临时_导入测试",
  "done": 1, "total": 40, "binds_ok": 0, "tasks_ok": 0,
  "finished": true, "errors": [],
  "tail": [
    "[screen] 现有画面: ['报警与趋势', '主监控', '参数设定', '手动维护']",
    "[screen] 已新建画面: 临时_导入测试",
    "[calib] origin=(245,309)",
    "[done] 1/37 标题 (文本)",
    "[ok] 已重建 1 个元件到画面 临时_导入测试"
  ]
}
```

- `1/37` 的分母是非按钮元件数：3 个导航按钮在单独一轮里建任务/写文字，所以 40 个元件的日志分母是 37；
- `wait` 到点仍未结束就立即返回，用 `ebx_import_status()` 继续查（`running` / `done` / `errors` / `tail`）；
- 试跑完清理：`tools\del_screen.py "临时_导入测试"` 删除画面并通过 `Ctrl+S` 保存，工程回到 4 页。

### 3.5 验收清单

1. 日志最后一行 `[ok] 已重建 N 个元件`，`errors` 为空；
2. 抽检 1 个指示灯、1 个数值、1 个导航按钮（打开任务看目标画面）；
3. 元件列表数量与 JSON `element_count` 一致（`ebx_screen_elements` 可读）；
4. 编译无错误；
5. 离线模拟逐页点导航，3 个按钮都能跳转。

---

## 4. 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| `[ERR] 找不到 EasyBuilder X 主窗口` | 工程未打开或标题不含 `EasyBuilder X`；先打开并最大化 |
| `[ERR] 画面 X 已存在` | 用 `--force`（自动加 `_导入`）或 `--screen` 换名 |
| 元件整体偏移固定距离 | 画布原点标定失败；确认最大化、100%、默认布局，重跑看 `[calib] origin1 == origin2` |
| `[bind] … : fail` | 目标工程缺变量或设备名不是 `PLC_NX502`；先导标签或 `--no-bind` |
| `[task] … : target_not_found` | 目标画面不存在；先建目标页 |
| `[task] … : not_saved` / `mismatch` | 任务未真正落盘；脚本会如实回报，重跑该按钮或改用路线 A |
| 脚本卡住 | 有模态对话框没关；手动关掉再重跑 |
| 终端中文乱码 | Git Bash 按 cp936 显示；JSON 是 UTF-8，不影响导入 |

---

## 5. 交付物

```
out/Alarm_Trend.screen.json      # 画面数据
out/ebx_screen_importer.py       # 导入器便携副本
out/IMPORT_README.md             # 迁移包说明
out/EXPORT_IMPORT_RUNBOOK.md     # 本文（导出/导入全过程）
tools/export_screen_json.py      # 导出器
tools/validate_screen_json.py    # 校验器
tools/ebx_screen_importer.py     # 导入器源文件
tools/del_screen.py              # 删除画面（试跑清理）
tools/mcp_call_once.py           # 单次调用 MCP 工具
```

权威备份仍然是 `.ebxprj` / `.ebxobj`；JSON 是迁移、审查与版本管理的中间格式。
