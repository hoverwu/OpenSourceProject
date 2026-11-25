# EasyBuilder X MCP + Skill

作者 hoverwu · 版本 0.6.0（MCP 服务器 0.4.0，26 个工具）· 实测版本 EasyBuilder X V1.01.376s

用 Windows UIA 与本机 Screen View 技术预览控制威纶通 / 威纶（WEINVIEW / Weintek）**EasyBuilder X**（EBX）HMI 组态软件，提供画面 JSON 生成、校验、导入、增量补丁与验收工具。

> EBX 没有公开承诺的稳定 API：没有 COM/SDK/插件，`.ebxprj` 是加密二进制容器。通用可控入口是 Windows UIA；Ribbon 与画布不可见，只能按窗口内坐标操作。另一个快速入口是 V1.01.376s 本机技术预览，但不得当成官方稳定接口。

## 三条制图路线

| 路线 | 用途 | 实测 |
| --- | --- | --- |
| **原生整页导入** | 从紧凑 JSON 快速生成 Text/Numeric/Lamp/Button 页面 | 8 控件全流程约 0.5 s；无绑定页编译约 7.1 s，离线导航通过 |
| **原生增量补丁** | 修改既有控件或增加少量控件，不重建整页 | 新增 3 个对象、19 个原生操作约 0.154 s；支持冲突检查、回读、幂等与失败回滚 |
| **UIA 重建** | 不启用预览时的通用工作桥 | 40/40 元件、17/17 标签、3/3 导航任务、3/3 按钮文字，约 29 min；样式取 EBX 默认值 |

**技术预览不是公开稳定 API。** 不要在其他版本或机器上擅自创建标记；启用开关前必须获得用户明确授权。客户端从 `%APPDATA%/Weintek/EasyBuilder X/ai-sockets/<pid>.json` 发现 loopback 实例并 ping。Socket 协议版本为字符串 `"1.4"`，原生归档 Schema 为 `"1.1"`。

当前原生路线的硬边界：

- `Text.text` / `Button.text` 只接受字符串库引用，不接受普通内联文字；归档不能嵌入字符串库。先在目标工程经字符串表 CSV/XLSX 准备对应 ID，或生成时省略文字。
- 先在 EBX `工程文件 > 变量` 创建 Project 变量，再通过 `Variable://Project/<tag>` 绑定；缺失变量会保留占位并阻塞编译。
- 导入返回 `all_ok=true` 不代表完整成功；转换器还会检查顶层/操作级 `success`、`unresolved_references` 与 `missing_references`。
- `tags[].address` 不会改写原生绑定。批量改地址应操作变量库/设备标签，或替换 JSON tag 后重新导入；设备 URI 原样回导会报 `index_references_are_missing`。
- 同名 `importScreenView` 会创建 `名称 (2)` 副本，不会替换既有画面；增量修改使用补丁工具。
- Changeset 批次不是原子事务；失败时前序操作可能已生效。
- JS Resource 仅证明 `.js` 文件可导入；未找到 JS Object/Action 执行入口，不能把 EBPro JS SDK 能力当成本机 EBX 能力。

## 内容

```text
easybuilder-x-mcp/
  SKILL.md                       Agent 主入口：能力边界、配方、坑与验证流程
  README.md                      本文件
  ebx_mcp_server.py              FastMCP HTTP 服务器，26 个 ebx_* 工具
  start-ebx-mcp.bat              一键启动（普通权限，无需 UAC）
  ebx-mcp-smoke-test.py          只读自检
  requirements.txt               uiautomation / fastmcp / pillow
  tools/
    ebx_ai_socket.py             原生预览 Socket 客户端（注册发现 + NDJSON）
    ebx_native_codegen.py        紧凑 JSON → 原生 Screen View，导入并回读验证
    ebx_native_patch.py          既有画面增量补丁：capture/dry-run/apply/回滚
    ebx_screen_importer.py       UIA 逐元件重建
    ebx_layout.py                MCP 与导入器共用 Ribbon 坐标
    validate_screen_json.py      画面 JSON 校验
    export_screen_json.py        已有 spec → ebx-screen/1.0 JSON
    mcp_call_once.py             命令行调用 MCP 工具
    sync_skill.py                部署 Skill 并校验 sha256
    test_ebx_*.py                原生协议/转换/补丁/MCP 离线测试
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
    Native_Patch_Sample.json          增量补丁样例
    NATIVE_PATCH_RUNBOOK.md           补丁前提、流程、失败语义与验收
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

## 26 个 MCP 工具

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
| 原生增量补丁 | `ebx_native_patch_capture` / `ebx_native_patch_apply` |
| 编译 / 模拟 | `ebx_compile` / `ebx_offline_simulate` / `ebx_stop_simulation` |
| 产物核验 | `ebx_artifacts` |

原生预览客户端与转换器仍是独立脚本；MCP 只新增补丁 capture/apply 薄封装，不重复实现协议逻辑，也不自动启用预览。

## 原生快速导入样例

先在隔离测试工程中启用已授权的预览并准备变量/字符串库，再执行：

```bat
cd /d "<本目录>"
python tools\validate_screen_json.py examples\C2_Native_Sample.screen.json --screens 参数设定
python tools\ebx_native_codegen.py examples\C2_Native_Sample.screen.json --screens 参数设定 --omit-text --output out\C2.native.json
python tools\ebx_native_codegen.py examples\C2_Native_Sample.screen.json --screens 参数设定 --omit-text --import --evidence-dir out\C2_import
```

导入后检查冲突、回读、事件与诊断，再编译和离线模拟。含不存在变量的页面可能导入成功但编译停滞，不要只看导入结果。

## 既有画面增量补丁

```bat
cd /d "<本目录>"
python tools\ebx_native_patch.py capture --screen "监控" --output out\监控.patch.json
rem 编辑 operations，保留 capture 返回的 base_hash
python tools\ebx_native_patch.py apply out\监控.patch.json --dry-run
python tools\ebx_native_patch.py apply out\监控.patch.json
```

补丁支持 `set_property`、`set_event`、`add_entity` 与单独的 `remove_entity`。工具检查 canonical 基线、写前值、实时 Schema，保存写前快照，应用后导出回读；已满足时返回 no-op。失败时尽可能逆序回滚，但删除操作无法自动恢复，权威兜底仍是 `.ebxprj` 备份。

完整说明与属性编码见 [examples/NATIVE_PATCH_RUNBOOK.md](examples/NATIVE_PATCH_RUNBOOK.md)，通用样例见 [examples/Native_Patch_Sample.json](examples/Native_Patch_Sample.json)。样例的全零 `base_hash` 必须替换为 capture 的真实值。

## 离线测试

```bat
cd /d "<本目录>"
python -m unittest discover -s tools -p "test_ebx_*.py"
python -m unittest discover -s tools -p "test_validate_screen_json.py"
python -m py_compile ebx_mcp_server.py tools\ebx_ai_socket.py tools\ebx_native_codegen.py tools\ebx_native_patch.py
```

当前完整离线回归共 42 项通过。不要对 `tools/` 使用宽泛 `test_*.py` 发现；生产包只保留纯离线测试。

## 安全与边界

- 全程普通权限，不需要管理员或 UAC。
- 创建预览标记、修改系统设置、安装依赖前遵循用户授权；本仓库不代替授权。
- 模拟器首次防火墙提示不代点。
- 删除被引用画面前先备份 `.ebxprj`。
- 不逆向 `.ebxprj`，不把技术预览当官方稳定接口。
- 本仓库不含现场工程、`.ebxobj`、凭据、调试截图或运行日志。
