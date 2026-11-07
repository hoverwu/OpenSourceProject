# EasyBuilder X MCP + Skill

用 UIA 与坐标地图控制威纶通 / 威纶（WEINVIEW / Weintek）**EasyBuilder X**（EBX）HMI 组态软件的专用 MCP 服务器，外加一份给 Agent 直接执行的 Skill 手册。

作者 hoverwu · 版本 0.3.0（MCP 服务器 0.2.0，24 个工具）· 实测版本 EasyBuilder X V1.01.376s

> EBX 没有官方 API：没有 COM/SDK/插件，`.ebxprj` 是加密二进制容器。唯一通用入口是 Windows UIA，而 UIA 在 EBX 里存在关键不对称：面板和对话框可读可点，Ribbon 与画布完全不可见，只能按坐标操作。本仓库把「坐标地图 + UIA 语义 + 原生对话框 AutomationId」固化成一组领域工具，避免每次重新摸索。

## 这个项目解决什么问题

自动化 EBX 最容易在五个地方翻车，这里的每条都是实测结论：

1. **UIA 找不到 Ribbon**：QtitanRibbon 自绘，页签/图标 0 个节点；只能按窗口内坐标点（页签行 y=51，按钮行 y=100）。
2. **对话框藏在三个地方**：原生 `#32770`、无标题顶层 `Qt5QWindowIcon`、主窗子树里的子 `WindowControl`；只找一种会永远等不到「是否保存」。
3. **属性面板读不到值**：右侧属性 dock 嵌套深度 >18，遍历给 16 层永远是 `None`；必须 ≥30 层并按控件引用取值。
4. **画面树/元件列表是 TreeControl 行**：画面树在左区第一棵，元件列表在第二棵，而且**元件 dock 没有 TabControl**，按页签找会永远为空。
5. **编译是大文件流式写入**：中途能抓到十几 MB 的半成品，必须等大小/mtime 稳定才能判成功。

## 内容

```text
easybuilder-x-mcp/
  SKILL.md                       Agent 主入口：能力边界、UIA 树模型、六条铁律、配方与坑
  ebx_mcp_server.py              FastMCP HTTP 服务器，24 个 ebx_* 工具（127.0.0.1:8788）
  start-ebx-mcp.bat              一键启动（普通权限，无需 UAC）
  ebx-mcp-smoke-test.py          只读自检：工具清单 + 状态 + 画面列表 + UIA 结构
  requirements.txt               uiautomation / fastmcp / pillow
  tools/
    mcp_call_once.py             命令行调一次 MCP 工具并打印 JSON
    sync_skill.py                把 SKILL.md 部署到用户 skills 目录并校验 sha256
    export_screen_json.py        EBX 画面 → ebx-screen/1.0 JSON
    ebx_screen_importer.py       读 JSON 用 UIA 重建画面（新建画面 → 放元件 → 绑标签 → 建导航）
    validate_screen_json.py      校验画面 JSON 自洽（数量/ID/标签/边界/跳转）
    del_screen.py                按名字删除一个画面
    ebx_probe.py / ebx_act.py    六探针与驱动脚本（MCP 不可用时的兜底）
    sendinput.py                 SendInput 真实按键（Qt 不认 SendKeys）
  references/
    EASYBUILDERX-UIA-AGENT-GUIDE.md   UIA 知识手册（活文档，含更新记录）
    EBX-MCP-CONTROL-PLAN.md           方案与实测台账
    RESEARCH-LEDGER.md                情报台账（官方来源 + 实测证据）
  examples/
    Alarm_Trend.screen.json           40 元件 / 38 标签 / 3 条导航任务的真实导出
    IMPORT_README.md                  导入前提与排错
    EXPORT_IMPORT_RUNBOOK.md          导出与导入全过程（含实测输出）
```

## 安装

要求 Windows 10/11 + Python 3.10+，本机以 Python 3.13 实测。

```bat
cd /d "<本目录>"
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

EasyBuilder X 默认装在 `%ProgramFiles%\EasyBuilderX\EasyBuilderX.exe`。装在别处时设置环境变量：

```bat
set EBX_EXE=D:\Tools\EasyBuilderX\EasyBuilderX.exe
```

## 启动与自检

```bat
cd /d "<本目录>"
start-ebx-mcp.bat
```

`start-ebx-mcp.bat` 的解释器优先级：`PYTHON` 环境变量 → 目录内 `.venv` / `venv` → PATH 里的 `python`。也可先 `set PYTHON=<解释器路径>` 显式指定。

另开一个终端自检（只读，不会改动工程；EBX 未启动也能看到工具清单）：

```bat
cd /d "<本目录>"
set NO_PROXY=
set no_proxy=
python ebx-mcp-smoke-test.py 8788
```

> 若 `NO_PROXY` 里含 `[::1]`，httpx 会抛 `InvalidURL: Invalid port: ':1]'`，所以客户端先清空这两个变量；自检脚本内部也会清一次。

把服务器注册进支持 MCP 的客户端（需新开会话才生效）：

```json
{ "url": "http://127.0.0.1:8788/mcp" }
```

## 24 个工具

| 场景 | 工具 |
| --- | --- |
| 状态 / 启动 | `ebx_status` / `ebx_launch` |
| 窗口 / 树 / 查找 | `ebx_windows` / `ebx_tree` / `ebx_find` |
| UIA 结构导出 | `ebx_uia_dump(scope=main\|dialogs\|popups\|all)` |
| 点击 | `ebx_click_name`（面板/对话框）、`ebx_click_xy`（窗口内坐标）、`ebx_ribbon`（页签/按钮/文件后台） |
| 截图 / 坐标图 | `ebx_screenshot` / `ebx_ribbon_map` |
| 按键 | `ebx_keys("ctrl+s")`（SendInput） |
| 工程 | `ebx_new_project` / `ebx_save_as` / `ebx_open` |
| 画面 | `ebx_screen_list` / `ebx_screen_open` / `ebx_screen_elements` |
| 页面 JSON | `ebx_import_screen_json` / `ebx_import_status` |
| 编译 / 模拟 | `ebx_compile` / `ebx_offline_simulate` / `ebx_stop_simulation` |
| 产物核验 | `ebx_artifacts` |

命令行调一次任意工具：

```bat
python tools\mcp_call_once.py ebx_status
python tools\mcp_call_once.py ebx_screen_list
python tools\mcp_call_once.py ebx_import_screen_json "{\"json_path\":\"examples/Alarm_Trend.screen.json\",\"screen\":\"导入测试\",\"limit\":1,\"no_bind\":true,\"no_nav\":true,\"no_save\":true}"
```

## 页面 JSON 迁移（有前提，别期待一键还原）

EBX **没有画面级 JSON 导入导出**：打开对话框只认 `.ebxprj/.ebxobj`，「反编译」只是把 `.ebxobj` 还原成 `.ebxprj`；官方导入导出仅覆盖字符串表、宏指令、审计 CSV、图片。

这里实现的桥是 `ebx-screen/1.0`：导出把画面描述成 `target/device/tags/used_tags/elements[]`，导入用 UIA 逐元件重建。实测在目标工程里重建整页 **40/40 元件、17/17 标签、3/3 切换画面任务、3/3 按钮文字**全部成功，耗时约 29 分钟（限制：样式为 EBX 默认值，报警条目/趋势图对象/动画/宏不在 schema 内）。

使用前提：

- 目标机同版本 EBX，窗口最大化到 1920×1080（100% 缩放），面板保持默认布局；
- 目标工程已有同名设备与变量标签，否则加 `--no-bind`；
- 第一次先小样试跑：`--limit 1 --no-bind --no-nav --no-save`，确认无误再整页跑。

详见 [examples/EXPORT_IMPORT_RUNBOOK.md](examples/EXPORT_IMPORT_RUNBOOK.md) 与 [examples/IMPORT_README.md](examples/IMPORT_README.md)。

## 把 Skill 装到 Qoder

`SKILL.md` 是本目录的唯一源稿。Qoder 的用户级 Skill 目录为 `%USERPROFILE%\.qoder-cn\skills\easybuilder-x-mcp\`，把本目录复制过去即可；也可用自带脚本同步并校验：

```bat
python tools\sync_skill.py
python tools\sync_skill.py --check
```

## 安全与边界

- 全程普通权限：EBX 的 manifest 是 `asInvoker`（Medium IL），不需要管理员，也不需要 UAC。
- 模拟器首次可能弹防火墙授权：脚本**不会代点**，交给人决定。
- 删除被其他画面按钮引用的画面会让导航任务换内部 ID 而失效——操作前先备份 `.ebxprj`。
- 不逆向 `.ebxprj`：高熵加密，没有公开格式。
- 本仓库只包含可复用工具与文档，不含任何现场工程、`.ebxobj` 产物与调试截图。

## 未验证边界

报警/配方/表格的 Excel（`libxl.dll`）导入导出入口；com-x:8000 / dserver-x:24763 应用层协议；编译记录文本读取；高 DPI / Ribbon 折叠 / 非中文界面下的坐标；已有元件的移动/多选/对齐。

更完整的实测记录见 `references/` 下三份文档。
