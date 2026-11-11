# plan.sample.json 说明

作者：hoverwu ｜ 非官方示例。这是 `ss_ecat_build.py` 的通用计划表示例，不含任何本机/私有工程信息，
设备名（耦合器1、NX耦合器2、伺服轴1 等）与节点号都只是占位示例，按自己的工程替换即可。

## 字段含义

UTF-8 JSON 数组，按数组顺序逐步执行。每项：

| 字段 | 含义 |
| --- | --- |
| `step` | 步序号（仅用于日志/`--from`/`--to` 定位）。 |
| `parent` | `master` = 主设备；否则填**父从站行 label 里的唯一子串**（常用设备名，如 `耦合器1`）。 |
| `port` | 留空 = 挂在父行本身（只对 `master` 有意义）；否则填该从站的端口行标签：`X2`/`X3`/`X4`/`X5`/`X6`/`Internal Port`。 |
| `kw` | 工具箱搜索关键字。可用短型号（如 `SV660`）扩大命中。 |
| `pick` | 在 `kw` 的结果里挑**包含这个子串**的那一行（如 `GX-JC06(IN,X2,X3) Main device`、`SV660N`）。 |
| `name` | 插入后写入的设备名。 |
| `node` | 节点号，**留给 renumber 阶段统一写**；插入阶段只校验设备名。 |
| `sub_name` / `sub_node` | 仅 Main+Sub 成对插入时使用（见下）。 |

## 两条必须遵守的实测语义

1. **Main device 是"一对"**：插入 `GX-JC06(IN,X2,X3) Main device` 后，软件会自动在其
   `Internal Port` 下再挂一个 `GX-JC06(X4,X5,X6) Sub-device`，两个节点各占一个节点号。
   示例第 1 步用 `sub_name` / `sub_node` 描述这个自动生成的从站。

2. **同一端口菊花链要倒序写**：插入落在所选端口的"头部"，所以同一端口上串多个从站时，
   计划里要**先写链尾、后写链头**，最终顺序才与目标一致。示例把 NX-ECC203 与 SV660N 分别放在
   `X2`、`X3` 两个不同端口，各自独立，不涉及倒序；若要把它们串在同一端口，请颠倒这两步的先后。

3. **节点号最后统一写**：每次插入都会重排全网络节点号，所以 `node`/`sub_node` 不在插入阶段生效，
   而是建完后用 `renumber` 子命令一次性写入并校验。

## 运行

```
ss_ecat_build.py <pid|auto> plan.sample.json <logdir> --save-each
ss_ecat_build.py <pid|auto> renumber plan.sample.json <logdir>
```

`--save-each` 强烈建议开：组态只存在进程内存里，应用一关全部丢失。`<logdir>` 由调用方给定，
每步各自落盘便于对照。任何一步失败立即停止，不自动换路线、不重试拖拽。