# EasyBuilder X MCP + Skill

作者 hoverwu · 版本 0.8.1（MCP 服务器 0.6.0，31 个注册工具 / 4 个常驻入口）· 实测版本 EasyBuilder X V1.01.376s

用 Windows UIA 与本机 Screen View 技术预览控制威纶通 / 威纶（WEINVIEW / Weintek）**EasyBuilder X**（EBX）HMI 组态软件，提供画面 JSON 生成、校验、导入、增量补丁与验收工具。

> EBX 没有公开承诺的稳定 API：没有 COM/SDK/插件，`.ebxprj` 是加密二进制容器。通用可控入口是 Windows UIA；Ribbon 与画布不可见，只能按窗口内坐标操作。另一个快速入口是 V1.01.376s 本机技术预览，但不得当成官方稳定接口。

## 官方 JSON 规范核查

截至 2026-11-25，在威纶通官方产品页、教学、操作手册列表与软件列表中**未找到公开的完整 Screen View JSON 或 AI Socket 规范**。官方物料证实 EBX 的物件属性/事件/方法、按钮事件与原生模拟流程，但没有定义本工具使用的 `header.schemaVersion`、`body.screens`、控件类型枚举或 Socket 方法名。

因此，本仓库的 `ebx-screen/1.0`、`ebx-native-patch/1.0` 都是自制格式；原生 Screen View 归档是 **V1.01.376s 本机技术预览的运行时契约**，不是官方承诺的稳定 API。每次导入会向 EBX 获取实时 `getScreenViewJsonSchema`，以该版本返回的 Schema 做写前校验。

官方参考：

- [EasyBuilder X 产品页](https://www.weinview.cn/EasyBuilderX)
- [文件菜单教学（2026-10-27）](https://www.bilibili.com/video/BV1r2HF64Edz)
- [物件导向设计与自定义模板（2026-11-20）](https://www.weinview.cn/cpdt/3654.html)
- [操作手册列表（2026-09-16）](https://www.weinview.cn/czsc) / [软件列表](https://www.weinview.cn/rj)

手册全文与更新说明正文未完成完整核验，因此结论是“未找到公开规范”，不是“功能不存在”。EasyBuilder Pro 的 AI 助理资料不能作为 EasyBuilder X AI Socket 的证据。

## 四条制图路线

| 路线 | 用途 | 实测 |
| --- | --- | --- |
| **原生整页导入** | 从紧凑 JSON 快速生成 Text/Numeric/Lamp/Button 页面 | 8 控件全流程约 0.5 s；无绑定页编译约 7.1 s，离线导航通过 |
| **原生增量补丁** | 修改既有控件或增加少量控件，不重建整页 | 新增 3 个对象、19 个原生操作约 0.154 s；支持冲突检查、回读、幂等与失败回滚 |
| **原生复用与验收** | 克隆既有画面、轻量查询对象、生成 PNG 快照 | 两个 8 控件副本回读哈希一致；全工程 133 对象查询约 0.024 s；快照哈希一致且视觉正常 |
| **UIA 重建** | 不启用预览时的通用工作桥 | 40/40 元件、17/17 标签、3/3 导航任务、3/3 按钮文字，约 29 min；样式取 EBX 默认值 |

**技术预览不是公开稳定 API。** 不要在其他版本或机器上擅自创建标记；启用开关前必须获得用户明确授权。客户端从 `%APPDATA%/Weintek/EasyBuilder X/ai-sockets/<pid>.json` 发现 loopback 实例并 ping。Socket 协议版本为字符串 `"1.4"`，原生归档 Schema 为 `"1.1"`。

当前原生路线的硬边界：

- `Text.text` / `Button.text` 只接受字符串库引用，不接受普通内联文字；归档不能嵌入字符串库。先在目标工程经字符串表 CSV/XLSX 准备对应 ID，或生成时省略文字。
- 先在 EBX `工程文件 > 变量` 创建 Project 变量，再通过 `Variable://Project/<tag>` 绑定；缺失变量会保留占位并阻塞编译。
- 导入返回 `all_ok=true` 不代表完整成功；转换器还会检查顶层/操作级 `success`、`unresolved_references` 与 `missing_references`。
- `tags[].address` 不会改写原生绑定。批量改地址应操作变量库/设备标签，或替换 JSON tag 后重新导入；设备 URI 原样回导会报 `index_references_are_missing`。
- 同名 `importScreenView` 会创建 `名称 (2)` 副本，不会替换既有画面；增量修改使用补丁工具。
- 画面克隆完整保留源画面的属性、事件和内部引用，但**不会把切屏目标重定向到副本**；需要独立导航时再生成补丁。
- `queryObjects` 只返回名称、类型和 x/y，适合快速存在性检查，不能替代完整导出、回读或回滚基线。
- Changeset 批次不是原子事务；失败时前序操作可能已生效。
- JS Resource 仅证明 `.js` 文件可导入；未找到 JS Object/Action 执行入口，不能把 EBPro JS SDK 能力当成本机 EBX 能力。

## 内容

```text
easybuilder-x-mcp/
  SKILL.md                       Agent 主入口：能力边界、配方、坑与验证流程
  README.md                      本文件
  ebx_mcp_server.py              FastMCP HTTP 服务器，31 个注册工具 / 4 个常驻入口
  start-ebx-mcp.bat              一键启动（普通权限，无需 UAC）
  ebx-mcp-smoke-test.py          分层目录与只读工具自检
  requirements.txt               uiautomation / fastmcp / pillow / jsonschema
  tools/
    ebx_ai_socket.py             原生预览 Socket 客户端（注册发现 + NDJSON）
    ebx_native_codegen.py        紧凑 JSON → 原生 Screen View，导入并回读验证
    ebx_native_patch.py          既有画面增量补丁：capture/dry-run/apply/回滚
    ebx_native_reuse.py          画面克隆、轻量对象查询与原生 PNG 快照
    ebx_mcp_catalog.py           分层目录、中文/英文检索与工具代理
    ebx_screen_importer.py       UIA 逐元件重建
    ebx_layout.py                MCP 与导入器共用 Ribbon 坐标
    validate_screen_json.py      画面 JSON 校验
    export_screen_json.py        已有 spec → ebx-screen/1.0 JSON
    mcp_call_once.py             命令行调用 MCP 工具
    sync_skill.py                同步 Skill + references 并校验 SHA-256
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

## 分层 MCP 调用

`tools/list` 只返回 4 个常驻入口，避免把 31 个完整参数 Schema 全部塞进模型上下文。按工具名、描述、输入/输出 Schema 的 JSON 序列化字节实测：11,793 → 1,664 B，初始目录负载减少 **85.9%**；这是字节口径，不等于账单或实际 Token 精确降幅。

| 入口 | 用途 |
| --- | --- |
| `ebx_status` | 查看 EBX 进程、主窗口、工程与监听端口 |
| `ebx_catalog(domain="", tool="")` | 无参数看领域总览；给领域看工具摘要；给精确工具名看完整输入/输出 Schema |
| `ebx_find_tools(query, domain="", limit=6)` | 中文子串、英文别名、精确工具名与参数名检索，返回紧凑 Markdown |
| `ebx_call_tool(name, arguments)` | 通过 FastMCP 正常调用链执行查到的工具 |

推荐调用顺序：

1. `ebx_catalog()` 查看 7 个领域与工具数量。
2. `ebx_find_tools("增量补丁")` 或 `ebx_catalog(domain="native")` 定位工具。
3. `ebx_catalog(tool="ebx_native_patch_apply")` 获取完整参数 Schema。
4. `ebx_call_tool(name="ebx_native_patch_apply", arguments={...})` 执行。

| 领域 | 能力 |
| --- | --- |
| `project` | 状态、启动、新建、打开、另存为、产物 |
| `observe` | 窗口、UIA 树、查找、结构导出、截图、Ribbon 地图 |
| `screen` | 画面枚举、切换与元件列表 |
| `native` | 原生生成/导入、dry-run、补丁、克隆、查询、快照 |
| `uia` | 语义点击、坐标点击、Ribbon、真实按键 |
| `legacy_json` | 无预览时的 UIA 慢速整页重建 |
| `build` | 编译、离线模拟与停止 |

31 个原 `ebx_*` 工具仍已注册，旧客户端可以继续按原名直接调用；代理不会改变权限、校验或返回语义。原生预览客户端与转换器复用同一套 Python 实现，MCP 只提供薄封装，不自动启用预览。Socket 客户端在首次解析后缓存端口；连接失败时清除自动解析的端口，下一次调用才重新发现实例。

## 原生快速导入样例

先在隔离测试工程中启用已授权的预览并准备变量/字符串库，再执行：

```bat
cd /d "<本目录>"
python tools\validate_screen_json.py examples\C2_Native_Sample.screen.json --screens 参数设定
python tools\ebx_native_codegen.py examples\C2_Native_Sample.screen.json --screens 参数设定 --omit-text --output out\C2.native.json
python tools\ebx_native_codegen.py examples\C2_Native_Sample.screen.json --screens 参数设定 --screen 新画面名 --omit-text --dry-run --evidence-dir out\C2_dryrun
python tools\ebx_native_codegen.py examples\C2_Native_Sample.screen.json --screens 参数设定 --screen 新画面名 --omit-text --import --evidence-dir out\C2_import
```

写前流程固定为：获取 EBX 实时 Schema → Draft 2020-12 校验 → 冲突检测 → 严格导入结果检查 → `getViewByScreenName` 与完整 `exportScreenView` 双重回读 → 诊断。Schema 不合法、依赖缺失或存在冲突时直接返回 `NATIVE_SCHEMA_VALIDATION_FAILED`、`SCHEMA_VALIDATOR_UNAVAILABLE` 或 `IMPORT_CONFLICT`，不会继续导入。dry-run 只做校验和冲突检测，不写 EBX。

导入后仍应编译和离线模拟。含不存在变量的页面可能导入成功但编译停滞，不要只看导入结果。MCP 可用 `ebx_native_generate` 离线生成、`ebx_native_import(dry_run=True)` 预检、`ebx_native_import` 正式导入。

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
python -m py_compile ebx_mcp_server.py tools\ebx_ai_socket.py tools\ebx_mcp_catalog.py tools\ebx_native_codegen.py tools\ebx_native_patch.py tools\ebx_native_reuse.py
```

当前完整离线回归共 79 项通过（75 项 EBX + 4 项验证器）。不要对 `tools/` 使用宽泛 `test_*.py` 发现；生产包只保留纯离线测试。

## 安全与边界

- 全程普通权限，不需要管理员或 UAC。
- 创建预览标记、修改系统设置、安装依赖前遵循用户授权；本仓库不代替授权。
- 模拟器首次防火墙提示不代点。
- 删除被引用画面前先备份 `.ebxprj`。
- 不逆向 `.ebxprj`，不把技术预览当官方稳定接口。
- 本仓库不含现场工程、`.ebxobj`、凭据、调试截图或运行日志。
