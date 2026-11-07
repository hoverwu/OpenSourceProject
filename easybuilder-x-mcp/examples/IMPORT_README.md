# 报警与趋势 画面迁移包（EasyBuilder X）

作者：hoverwu ｜ 版本：1.0.0 ｜ 日期：2026-11-07

本目录用于把「报警与趋势」这一页从本机工程搬到另一台电脑的 EasyBuilder X 里。

## 0. 先说清楚一件事

**EasyBuilder X V1.01.376s 没有画面级 JSON 导入/导出。**
它的「打开」只认 `.ebxprj` / `.ebxobj`；官方结构化交换只有字符串表（`.csv/.xls/.xlsx`）、宏（`.ebm`）、审计（`.csv`）和图片。「反编译」也只是把 `.ebxobj` 还原成 `.ebxprj`，不是导出 JSON。

所以本包给的是两条真正能走通的路：

| 路线 | 适合场景 | 代价 |
| --- | --- | --- |
| **A. 画面复制 / 粘贴**（EBX 原生） | 两个工程里已有同名设备与标签；只是一页要搬 | 手动，跨工程需标签完全同名；最省事 |
| **B. JSON + 导入脚本**（本包主体） | 需要留档、版本管理、批量重建，或目标机只有空工程 | 需 Python + uiautomation；按坐标驱动界面，≈30 min/页 |

如果没有特殊需求，**先用 A**；A 不满足（例如目标机是新建工程、要一份可审查与再利用的数据）再用 B。

## 1. 文件清单

| 文件 | 作用 |
| --- | --- |
| `Alarm_Trend.screen.json` | 画面数据（schema `ebx-screen/1.0`），40 个元件 + 38 条标签清单 + 17 个实际使用的标签 |
| `ebx_screen_importer.py` | 导入器：读 JSON，用 UIA 驱动 EBX 界面把画面重建出来（便携副本，单文件） |
| `IMPORT_README.md` | 本文件 |
| `EXPORT_IMPORT_RUNBOOK.md` | 导出 / 导入全过程实录（含命令、真实输出、校验与 MCP 通道） |

JSON 里已写明 `import.native_json_support: false` 与所需环境，可直接给对方工程师看。

## 2. 路线 A：原生复制 / 粘贴

适用：两台机器上都有同一个工程（或至少同名设备 + 同名标签）。

1. 源机打开 `.ebxprj`，双击画面树里的「报警与趋势」，让画面编辑器成为当前页。
2. 画布空白处点一下 → `Ctrl+A` 全选 → `Ctrl+C`。
3. 目标机打开目标工程，**新建一个 1024×600 的画面**（尺寸必须一致，否则粘贴会错位/裁切）。
4. 点画布 → `Ctrl+V`。
5. 逐个核对：指示灯/数值的「标签」是否绑定成功（未绑定会显示空或红色感叹号）、3 个导航按钮的任务是否指向存在的画面。
6. `Ctrl+S` 保存，然后编译验证。

注意：

- 跨工程粘贴时标签按**名字**匹配；名字不一致的元件会变成未绑定，需要手动重绑。
- 画面树里的排序不能拖动改变；启动页恒为「最先创建」的那一页。
- 删除被导航任务引用的画面会弹警告，重建会换内部 ID，旧导航任务失效——操作前先备份 `.ebxprj`。

## 3. 路线 B：JSON + 导入脚本

### 3.1 环境前提（缺一不可）

1. **Windows + EasyBuilder X V1.01.376s**（其他版本 Ribbon 坐标会变，需要重新标定）。
2. EBX 打开目标工程，主窗口**最大化**，屏幕 1920×1080、系统缩放 100%，左右面板保持默认布局。
3. 目标工程里已有设备 **PLC_NX502**（Omron EtherNet/IP NJ/NX），并已导入 JSON `tags[]` 里的同名 CIP 变量。
   没有标签时加 `--no-bind`：元件照建，但不绑定。
4. Python 3.8+，安装依赖：
   ```bat
   pip install uiautomation
   ```
5. 画面尺寸 1024×600（cMT3075XH）。换机型需同步改 JSON 的 `screen.width/height` 与坐标。

### 3.2 运行

```bat
cd /d "拷贝到目标机后的目录"
python ebx_screen_importer.py Alarm_Trend.screen.json
```

常用参数：

| 参数 | 作用 |
| --- | --- |
| `--screen 名称` | 指定新建画面的名字（默认用 JSON 里的 `报警与趋势`） |
| `--force` | 同名画面已存在时仍新建（自动改成 `名称_导入`） |
| `--no-bind` | 不绑标签（目标机还没导入变量时用） |
| `--no-nav` | 不建切换画面任务、不放按钮 |
| `--limit 8` | 只放前 8 个元件，先试水 |
| `--no-save` | 不自动 `Ctrl+S`（先看效果再决定是否保存） |
| `--probe-ribbon` | 只生成带刻度的 Ribbon 截图，用于换分辨率/DPI 后重新校准 |

**建议第一次先跑 `--limit 8 --no-save`**，确认坐标没错、标签能绑，再跑全量。

### 3.3 它到底做了什么

1. 找 EBX 主窗 → 读画面树，确认目标名未被占用；
2. 新建画面并进入编辑器；
3. 用两次拖拽标定画布原点（本机实测 `(245, 309)` = 画布 (0,0) 的屏幕坐标）；
4. 逐元件：点「元件」页签对应图标 → 画布上按住拖出 x/y/w/h → 属性面板写「名称」→
   文本写「文本」/ 数值与指示灯「标签」绑变量 / 按钮建「切换画面」任务并写按钮文字；
5. 全部完成后 `Ctrl+S`。

一个元件约 30~60 秒，40 个元件约 **29 分钟**。跑的时候别动鼠标键盘，也別切走 EBX。

### 3.4 本机实测结果（2026-11-07）

在开发机上把 `Alarm_Trend.screen.json` 完整重建为「报警与趋势_导入验证」：

- 元件 **40/40** 成功（20 静态文本 / 9 指示灯 / 8 数值 / 3 按钮）；
- 标签绑定 **17/17** ok；
- 切换画面任务 **3/3** ok（主监控 / 参数设定 / 手动维护），并且重新打开任务对话框复核过；
- 按钮文字 **3/3** ok；
- 截图与原页布局一致；验证完已删除该画面并保存，工程仍是 4 页。

也就是说 JSON 与导入器是能用的，不是草案。

## 4. JSON 结构（`ebx-screen/1.0`）

```json
{
  "schema": "ebx-screen/1.0",
  "generator": { "tool": "EasyBuilder X UIA bridge", "version": "0.1.0",
                 "author": "hoverwu", "exported_at": "2026-11-07T18:11:43+08:00" },
  "source_project": "PipeHeating_HMI.ebxprj",
  "target": { "software": "EasyBuilder X V1.01.376s", "model": "cMT3075XH",
              "width": 1024, "height": 600, "zoom": 100 },
  "device": { "name": "PLC_NX502", "driver": "Omron EtherNet/IP (NJ/NX Series)",
              "ip": "192.168.250.1", "addressing": "CIP 变量名（GlobalVariables）" },
  "tags": [ { "name": "rTempMeas", "data_type": "REAL", "address": "",
              "comment": "", "rw": "RW", "scope": "GlobalVariables",
              "addressing": "CIP variable name" } ],
  "used_tags": ["rTempMeas"],
  "screen": {
    "name": "报警与趋势", "width": 1024, "height": 600,
    "element_count": 40,
    "elements": [
      { "id": "e01", "type": "static_text", "ebx_kind": "文本",
        "name": "标题", "x": 150, "y": 24, "w": 620, "h": 40,
        "text": "报警与趋势 · 保护监视" },
      { "id": "e18", "type": "numeric_display", "ebx_kind": "数值",
        "name": "出口温度", "x": 150, "y": 242, "w": 170, "h": 68,
        "tag": "rTempMeas", "readonly": false },
      { "id": "n01", "type": "button", "ebx_kind": "按钮",
        "name": "nav_主监控", "x": 520, "y": 548, "w": 140, "h": 38,
        "label": "主监控",
        "task": { "type": "switch_screen", "target": "主监控" } }
    ]
  },
  "import": { "native_json_support": false, "note": "…", "requirements": ["…"],
              "style_policy": "字体/颜色/边框/数据格式均为 EBX 默认值" }
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `type` | `static_text` / `numeric_display` / `indicator` / `button` |
| `ebx_kind` | 对应 EBX 元件页签里的中文名（文本/数值/指示灯/按钮），导入时按它点图标 |
| `x/y/w/h` | 画面绝对像素（左上角 + 宽高），不是相对坐标 |
| `text` | 静态文本内容 |
| `tag` | 绑定变量名；`readonly: true` 表示只读（输入类元件用） |
| `label` | 按钮显示文字 |
| `task.type` | 目前只支持 `switch_screen`；`target` 必须是目标工程里已存在的画面名 |

## 5. 已知限制

- **样式不还原**：字体、颜色、边框、数据格式都是 EBX 默认值（JSON 的 `style_policy` 已注明）。要一模一样的外观，路线 A 更合适。
- **只有四类元件**：静态文本、指示灯、数值、按钮。报警条目、趋势图对象、动画、宏、事件、自定义模板**不在** JSON 内。
- **坐标是绝对像素**：换机型（非 1024×600）要重算；页面缩放必须 100%。
- **Ribbon 是纯坐标**：换 DPI / 分辨率 / 界面语言要重新标定，用 `--probe-ribbon` 生成刻度图。
- **导入依赖界面自动化**：跑的时候不能有人在动键盘鼠标、不能切走 EBX；中途弹任何模态框都会卡住脚本。
- SD 卡/工程层面的权威备份仍然是 `.ebxprj` / `.ebxobj`，JSON 只是迁移与审查用的中间格式。

## 6. 排错

| 现象 | 原因 / 处理 |
| --- | --- |
| `[ERR] 找不到 EasyBuilder X 主窗口` | 工程没打开，或主窗标题不含 `EasyBuilder X`；先把 EBX 打开并最大化 |
| `[ERR] 画面 X 已存在` | 加 `--force`（自动改名 `X_导入`）或 `--screen` 换名 |
| 元件放歪 / 全部偏一个固定距离 | 画布原点标定失败。EBX 必须最大化、100% 缩放、左右面板默认布局；重跑即可，日志里 `[calib] origin=…` 应两次一致 |
| `[bind] … : fail` | 目标工程没有该变量，或设备名不是 `PLC_NX502`；先导入标签，或 `--no-bind` 跳过 |
| `[task] … : target_not_found` | 目标画面在画面树里不存在（顺序/名字敏感），先建好目标页 |
| `[task] … : not_saved` / `mismatch:…` | 任务没真正落盘；脚本会回报而不是假成功。重跑该按钮或改用路线 A 补 |
| 脚本卡住不动 | 有模态对话框没关（保存提示、警告等）；手动关掉再重跑 |
| 中文在终端显示乱码 | Git Bash 用 cp936 解码显示，JSON 本身是 UTF-8，不影响导入 |

## 7. 建议的验收步骤

1. `--limit 4 --no-save` 试跑，肉眼核对 4 个元件位置与绑定；
2. 全量跑（不带 `--no-save`），检查日志最后一行 `[ok] 已重建 40 个元件`；
3. 逐项抽检：1 个指示灯、1 个数值、1 个导航按钮（点开任务看目标画面）；
4. 编译：`F7` 或「工程文件 → 编译」，无错误；
5. 离线模拟逐页点导航，确认 3 个按钮都能跳转。

---

源工程与全套工具见本仓库（`tools/` 下有导出、导入、删画面、打开画面等脚本；知识库见 `references/EASYBUILDERX-UIA-AGENT-GUIDE.md` §10）。
