# sysmac-studio-control Skill

作者 hoverwu ｜ 版本 0.11.0 ｜ 非官方

用 Windows UI Automation 读取与操作欧姆龙 Sysmac Studio 的 Agent Skill：工程树导航、编辑器测绘、变量/轴/EtherCAT 组态、在已有库 FB 上按轴开关加功能并重建/换 `.slr` 库、编译错误读取、真落盘保存与归档校验。主入口是 [SKILL.md](SKILL.md)，实测细节在 [references/](references/)，命令行驱动在 [scripts/](scripts/)，EtherCAT 批量插入计划示例在 [examples/](examples/)。

## 目录

```text
SKILL.md          Agent 主入口：能力、边界、配方、安全红线
scripts/          命令行脚本（ss.py / ss_uimap.py / ss_ecat_*.py / ss_save.py 等）
references/       控件树、坑清单、架构、项目文件、回归清单
examples/         通用 EtherCAT 计划示例（plan.sample.json）
```

## 安装

把本目录复制为 Qoder 用户 Skill 目录：

```bat
xcopy /E /I "<本目录>" "%USERPROFILE%\.qoder-cn\skills\sysmac-studio-control"
```

或在发布包根目录用同步工具（带 SHA-256 校验）：

```bat
cd /d "<发布包根目录>"
.venv\Scripts\python tools\sync_skill.py
```

安装后新开会话加载。

## 依赖与运行前提

- Windows 10/11，Python 3.10+；脚本依赖见 [requirements.txt](requirements.txt)（完整钉版在发布包根目录 `requirements.txt`），装进项目内虚拟环境，不污染系统解释器。
- Sysmac Studio 以高完整性（管理员）运行时，脚本也必须提权，否则 UIPI 会挡住 UIA 读取；普通权限目标可用普通权限脚本。
- 实测基线：Sysmac Studio V1.68 64bit / Windows 11 / 125% 缩放。换机器、换 DPI、换版本后先跑 [references/extending.md](references/extending.md) 的版本回归清单；文档里的坐标与行高是实测基线，不是跨机器常量（`SS_ROW_H`、`SS_ROWS_PER_NOTCH`、`SS_AXTABLE_*` 环境变量可覆盖）。
- 文档中提到的 `*.txt` 实测日志与录制文件是本机运行时产物，不随 Skill 发布；需要时按对应配方重跑生成。

## 安全红线

- 绝不读取、输入、导出序列号、授权文件或凭据；许可（License）相关窗口只识别并避开。
- `online` / `download` / `upload` / `reset` 等改变真实控制器状态的动作，没有用户当轮明确同意不得执行。
- 删除、重命名、另存为、导出覆盖前先确认目标工程已落盘并备份。
- 批量写入后必须真正保存（`ss_save.py --file <目标.smc2>`），以 sha256 或归档内容复核，不能只看界面。