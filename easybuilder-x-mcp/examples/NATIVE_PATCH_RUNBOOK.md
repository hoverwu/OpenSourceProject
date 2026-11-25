# EasyBuilder X 既有画面增量补丁

作者：hoverwu ｜ 版本：1.0.0 ｜ 日期：2026-11-25 ｜ 适用：EasyBuilder X V1.01.376s 本机技术预览

本文说明如何修改既有画面的少量控件，而不重建整页。补丁格式为 `ebx-native-patch/1.0`，由 `tools/ebx_native_patch.py` 执行；MCP 工具是同一实现的薄封装。

## 1. 先明确边界

- Screen View / AI Socket 是受预览开关控制的本机功能，不是公开稳定 API。启用开关、重启 EBX 前必须获得用户明确授权；其他版本或机器必须重新验证。
- Socket 只监听 loopback，端口由实例注册文件发现。协议版本为字符串 `"1.4"`，原生归档 Schema 为 `"1.1"`。
- 原生归档不能创建 Project 变量或字符串库。开始前在 EBX `工程文件 > 变量` 建立所需 Project 变量，并经 `工程文件 > 字符串` 准备所需字符串 ID。
- 本工具 MVP 只处理 root 层的 Text / Numeric / Lamp / Button。复杂群组、报警、趋势、动画、宏与跨工程模板保真度不在验收范围内。
- 不要用 `importScreenView` 回导同名画面来“更新”：实测会创建 `名称 (2)` 副本。既有画面增量修改使用 `applyChangeset`，由本工具封装。

## 2. 标准流程：capture → 编辑 → dry-run → apply

先在隔离测试工程中启用已授权的预览并打开工程。以下命令均从项目根目录运行：

```bat
cd /d "<项目根>"
python tools\ebx_native_patch.py capture --screen "监控" --output out\监控.patch.json --evidence-dir out\ai_socket
```

用文本编辑器或 AI 编辑生成的补丁：

1. 保留 `screen` 与 `base_hash`；
2. 在 `operations` 中填写要修改的裸元件名；
3. 尽可能给 `set_property` / `set_event` 填写写前 `before` 值；
4. 保存为 UTF-8 JSON。

先预检，不写 EBX：

```bat
cd /d "<项目根>"
python tools\ebx_native_patch.py apply out\监控.patch.json --dry-run --evidence-dir out\ai_socket
```

`dry_run` 返回当前基线哈希、逐项 `pending/satisfied/conflict` 状态和展开后的原生操作。只有 `ok=true` 且没有冲突时才正式应用：

```bat
cd /d "<项目根>"
python tools\ebx_native_patch.py apply out\监控.patch.json --evidence-dir out\ai_socket
```

工具会先导出写前快照，再应用 Changeset、导出读回并逐项验证。返回 `noop=true` 表示目标状态已经满足，不会重复创建或重复写入。不要把 `all_ok=true` 单独当成功；本工具还检查操作级成功、未解析引用、缺失引用和写后状态。

## 3. MCP 调用

专用 MCP v0.4.0 提供两个工具：

- `ebx_native_patch_capture(screen)`：捕获画面并返回带 `base_hash` 的空操作补丁，不写 EBX。
- `ebx_native_patch_apply(patch, dry_run=false)`：执行同一套 Schema 预检、冲突检查、写前快照、应用、回读与失败回滚。

推荐顺序：

1. 调用 capture；
2. 将 operations 填入返回的 patch；
3. 以 `dry_run=true` 调用 apply；
4. 确认无冲突后以 `dry_run=false` 正式调用；
5. 检查 `verification.ok`、`statuses` 与 `response`，不要只看 HTTP/MCP 调用成功。

MCP 工具不会自动启用预览标记，也不会代替用户授权。

## 4. 操作与属性编码

| 操作 | 用途 | 关键约束 |
| --- | --- | --- |
| `set_property` | 修改既有控件属性 | `entity` 是不含 `/` 的裸元件名；工具自动补画面路径 |
| `set_event` | 修改既有控件事件 | 给出 `event` 与 `statements` 数组 |
| `add_entity` | 新增控件并配置属性/事件 | 同名但内容不同会冲突，不会覆盖；工具展开为 add + 后续 set 操作 |
| `remove_entity` | 删除单个控件 | 必须单独执行；无法自动恢复被删对象 |

已开放且经过读回验证的属性编码：

| 属性 | 补丁中的值 | 原生 Changeset 编码 |
| --- | --- | --- |
| `x/y/width/height/radius` | JSON 整数，如 `40` | JSON 字符串，如 `"40"` |
| `padding` | `{top,right,bottom,left}`，成员为非负整数 | 同样的结构化对象 |
| `text` | `String://Project:ID[n]` 或 `null` | 原样传递；普通内联文字被拒 |
| `value/readValue` | `Variable://Project/<tag>` 字符串 | `{ "path": "Variable://Project/<tag>" }` |
| `add_entity.properties.tag` | 裸变量名或完整 `Variable://` 引用 | Numeric 自动绑定 `value`，Lamp 自动绑定 `readValue` |

`set_property` 示例：

```json
{
  "type": "set_property",
  "entity": "当前温度",
  "property": "value",
  "before": "Variable://Project/rOldTemp",
  "value": "Variable://Project/rTempMeas"
}
```

`set_event` 的 statements 使用 EBX 原生事件结构。按钮切屏示例：

```json
{
  "type": "set_event",
  "entity": "导航_参数设定",
  "event": "onClick",
  "statements": [
    {
      "type": "call",
      "method": "Method://<system>.changeScreen",
      "parameters": {
        "target": "Object://Screen:参数设定",
        "animation": { "effect": "none" }
      }
    }
  ]
}
```

完整四操作样例见 `Native_Patch_Sample.json`。其中 `base_hash` 全零只是占位，必须用 capture 返回的真实哈希替换；样例中的画面、变量和字符串 ID 也必须按目标工程调整。

## 5. 安全与失败语义

- **基线冲突**：补丁的 `base_hash` 与当前画面 canonical SHA-256 不同就停止。重新 capture、审查差异并生成新补丁，不要强行清空基线。
- **写前检查**：`before` 不匹配会停止，避免覆盖他人的新改动。
- **幂等**：所有目标状态已满足时返回 no-op；新增操作按名称和内容判断，不会重复创建。
- **非原子批次**：EBX Changeset 不是事务。失败时前序操作可能已生效；工具保留逐项响应，并尽可能按逆序恢复写前属性/事件或删除本次新增对象。
- **回滚不是绝对保证**：删除操作无法自动恢复；引用清空、Socket 中断或回滚本身失败时，应使用写前快照与 `.ebxprj` 备份人工恢复。
- **删除必须单独执行**：工具拒绝把 `remove_entity` 与其他操作混在同一补丁中。
- **一次只改一个所有者**：应用期间不要同时用 UI、其他 Agent 或第二个 MCP 会话编辑同一画面。

## 6. 实测性能（本机 V1.01.376s）

- 既有 Numeric 的 6 项几何属性修改约 0.0497 s，回读全部满足。
- 一次新增 Text + Numeric + Button，含字符串、Project 变量绑定与切屏事件，共展开 19 个原生操作，约 0.154 s。
- 重复应用同一补丁返回 no-op，没有重复对象。
- Text / Numeric / Button 分别单独删除，约 0.068 / 0.0592 / 0.035 s；清理后画面哈希恢复原值。
- 这些数字是本机单次实测，不是性能承诺；导出、校验与证据落盘也计入工具流程。

## 7. 官方批量能力边界

- 字符串表支持 CSV / XLS / XLSX 导入导出，适合准备多语言 ID；官方未明确表头、编码、重复 ID 等行为，迁移前先做小样本 round-trip。
- 设备标签导入只在受支持驱动/条件下提供，不是通用变量 CSV 承诺。
- 智慧批次修改可套用共用属性、事件或方法；直接批量改地址未获官方文档证实。
- 自定义模板已证实工程内复用和“应用更改”同步；未找到独立导出文件或跨工程部署格式。
- `ebxtool.exe` 的公开文档命令只有版本与审计 CSV 校验，不是制图或编译 CLI。

## 8. 验收清单

1. dry-run 无冲突，native operations 与预期一致。
2. 正式应用返回 `ok=true`，`verification.ok=true`，所有目标状态 satisfied。
3. 没有顶层或操作级未解析引用、缺失引用。
4. 重复应用返回 no-op。
5. 抽检一个文本、一个数值和一个按钮事件；文字引用与变量绑定均存在。
6. 保存工程，编译并离线模拟；含缺失变量的页面可能导入成功但编译停滞。
7. 临时验收对象逐项删除，确认画面对象清单和哈希恢复预期。

权威备份仍是 `.ebxprj` / `.ebxobj`；补丁与快照用于自动化、审查和版本管理，不替代工程备份。
