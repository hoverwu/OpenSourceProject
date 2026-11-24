# EasyBuilder X MCP + Skill

作者 hoverwu · 版本 0.5.0（MCP 服务器 0.3.0，24 个工具）· 实测版本 EasyBuilder X V1.01.376s

用 Windows UIA 与坐标地图控制威纶通 / 威纶（WEINVIEW / Weintek）**EasyBuilder X**（EBX）HMI 组态软件，并提供画面 JSON 生成、校验、导入与验收工具。

> EBX 没有公开承诺的稳定 API：没有 COM/SDK/插件，`.ebxprj` 是加密二进制容器。通用可控入口是 Windows UIA；Ribbon 与画布不可见，只能按窗口内坐标操作。本仓库把「坐标地图 + UIA 语义 + 原生对话框 AutomationId」固化成领域工具。

## 两条 JSON 路线

1. **UIA 重建（通用）**：`ebx-screen/1.0` → 新建画面 → 逐元件放置/写属性/绑标签/建导航。实测 40/40 元件、17/17 标签、3/3 导航任务、3/3 按钮文字成功，约 29 分钟；样式取 EBX 默认值。
2. **原生 Screen View 技术预览（快速）**：EBX V1.01.376s 内含受 `technical_preview` 与 `enable_ebx_socket_server` 控制的本机 loopback Socket。显式授权启用后，可导出/导入画面 JSON 并执行 Changeset。8 控件导入全流程约 0.5 秒，无绑定画面编译约 7.1 秒，离线导航验证通过。

**技术预览不是公开稳定 API。** 不要在其他版本或机器上擅自创建标记；端口随实例变化，客户端从 `%APPDATA%/Weintek/EasyBuilder X/ai-sockets/<pid>.json` 发现并 ping。Socket 协议版本为字符串 `"1.4"`，原生归档 Schema 为 `"1.1"`。

当前原生路线的硬边界：

- `Text.text` / `Button.text` 只接受字符串库引用，不接受普通内联文字；归档不能嵌入字符串库。可先用 `--omit-text`，或先在目标工程经字符串表 CSV/XLSX 准备对应 ID。
- 先在 EBX `工程文件 > 变量` 创建 Project 变量，再通过 `Variable://Project/<tag>` 绑定；已实测真实 Project 变量无未解析引用。缺失变量会保留占位并阻塞编译。
- 导入返回 `all_ok=true` 不代表完整成功；转换器还会检查顶层/操作级 `success`、`unresolved_references` 与 `missing_references`。
- `tags[].address` 不会改写原生绑定。批量改地址应操作变量库/设备标签，或替换 JSON tag 后重新导入；设备导出的 `Variable://[PLC]/GlobalVariables/<tag>` 原样回导会报 `index_references_are_missing`。
- JS Resource 仅证明 `.js` 文件可导入；未找到 JS Object/Action 执行入口，不能把 EBPro JS SDK 能力当成本机 EBX 能力。

## Changeset 与字符串引用

文本属性接受以下 `displayString` 形式：

```json
[
  "String://Project:ID[31]",
  {"path":"<字符串库路径>","indexReference":31},
  {"path":"<字符串库路径>","indexReferences":{"zh-CN":31}},
  null
]
```

修改既有控件文字时，使用规范实体路径 `画面名/元件名`：

```json
{
  "schema_version": "1.4",
  "method": "applyChangeset",
  "params": {
    "operations": [{
      "type": "set_property",
      "entity": "参数设定/标题",
      "property": "text",
      "value": "String://Project:ID[31]"
    }]
  }
}
```

## 内容

```text
easybuilder-x-mcp/
  SKILL.md                       Agent 主入口：能力边界、配方、坑与验证流程
  README.md                      本文件
  ebx_mcp_server.py              FastMCP HTTP 服务器，24 个 ebx_* 工具
  start-ebx-mcp.bat              一键启动（普通权限，无需 UAC）
  ebx-mcp-smoke-test.py          只读自检
  requirements.txt               uiautomation / fastmcp / pillow
  tools/
    ebx_ai_socket.py             原生预览 Socket 客户端（注册发现 + NDJSON）
    ebx_native_codegen.py        紧凑 JSON → 原生 Screen View，导入并回读验证
    ebx_screen_importer.py       UIA 逐元件重建
    ebx_layout.py                MCP 与导入器共用 Ribbon 坐标
    validate_screen_json.py      画面 JSON 校验
    export_screen_json.py        已有 spec → ebx-screen/1.0 JSON
    mcp_call_once.py             命令行调用 MCP 工具
    sync_skill.py                部署 Skill 并校验 sha256
    test_ebx_*.py                原生协议/转换/模态框离线测试
    test_validate_screen_json.py 验证器回归测试
    del_screen.py                按名字删除画面
    ebx_probe.py / ebx_act.py    UIA 探针与驱动兜底
    sendinput.py                 SendInput 真实按键
  references/
    EASYBUILDERX-UIA-AGENT-GUIDE.md   UIA 与原生预览知识手册
    EBX-MCP-CONTROL-PLAN.md           控制方案
    RESEARCH-LEDGER.md                事实与证据台账
  examples/
    Alarm_Trend.screen.json          UIA 重建样例
    C2_Native_Sample.screen.json      原生快速导入样例
    IMPORT_README.md                 UIA 导入前提与排错
    EXPORT_IMPORT_RUNBOOK.md         导出与导入过程
```

## 安装

要求 Windows 10/11 + Python 3.10+。

```bat
cd /d "<本目录>"
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

EasyBuilder X 默认装在 `%ProgramFiles%\EasyBuilderX\EasyBuilderX.exe`。装在别处时设置 `EBX_EXE`。

## 启动与自检

```bat
cd /d "<本目录>"
start-ebx-mcp.bat
```

另开终端：

```bat
cd /d "<本目录>"
set NO_PROXY=
set no_proxy=
python ebx-mcp-smoke-test.py 8788
```

注册 MCP：`{ "url": "http://127.0.0.1:8788/mcp" }`。

解释器优先级：`PYTHON` 环境变量 → 目录内 `.venv` / `venv` → PATH 里的 `python`。

## 24 个 MCP 工具

| 场景 | 工具 |
| --- | --- |
| 状态 / 启动 | `ebx_status` / `ebx_launch` |
| 窗口 / 树 / 查找 | `ebx_windows` / `ebx_tree` / `ebx_find` |
| UIA 结构导出 | `ebx_uia_dump(scope=main\|dialogs\|popups\|all)` |
| 点击 | `ebx_click_name` / `ebx_click_xy` / `ebx_ribbon` |
| 截图 / 坐标图 | `ebx_screenshot` / `ebx_ribbon_map` |
| 按键 | `ebx_keys("ctrl+s")` |
| 工程 | `ebx_new_project` / `ebx_save_as` / `ebx_open` |
| 画面 | `ebx_screen_list` / `ebx_screen_open` / `ebx_screen_elements` |
| 页面 JSON | `ebx_import_screen_json` / `ebx_import_status` |
| 编译 / 模拟 | `ebx_compile` / `ebx_offline_simulate` / `ebx_stop_simulation` |
| 产物核验 | `ebx_artifacts` |

原生预览暂为独立脚本，不冒充已注册的 MCP 工具。

## 原生快速导入样例

先在隔离测试工程中启用预览并打开工程，再执行：

```bat
cd /d "<本目录>"
python tools\validate_screen_json.py examples\C2_Native_Sample.screen.json --screens 参数设定
python tools\ebx_native_codegen.py examples\C2_Native_Sample.screen.json --screens 参数设定 --omit-text --output out\C2.native.json
python tools\ebx_native_codegen.py examples\C2_Native_Sample.screen.json --screens 参数设定 --omit-text --import --evidence-dir out\C2_import
```

导入后检查冲突、回读、事件与诊断，再编译和离线模拟。含不存在变量的页面可能导入成功但编译停滞，不要只看导入结果。

## 离线测试

```bat
cd /d "<本目录>"
python -m unittest discover -s tools -p "test_ebx_*.py"
python -m unittest discover -s tools -p "test_validate_screen_json.py"
python -m py_compile ebx_mcp_server.py tools\ebx_ai_socket.py tools\ebx_native_codegen.py
```

不要对 `tools/` 使用宽泛 `test_*.py` 发现；生产包只保留纯离线测试。

## 安全与边界

- 全程普通权限，不需要管理员或 UAC。
- 创建预览标记、修改系统设置、安装依赖前遵循用户授权；本仓库不代替授权。
- 模拟器首次防火墙提示不代点。
- 删除被引用画面前先备份 `.ebxprj`。
- 不逆向 `.ebxprj`，不把技术预览当官方稳定接口。
- 本仓库不含现场工程、`.ebxobj`、凭据、调试截图或运行日志。
