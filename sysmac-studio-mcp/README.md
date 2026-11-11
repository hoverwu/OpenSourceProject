# Sysmac Studio MCP + Skill

作者 hoverwu · MCP 桥接器 0.2.0 · Skill 0.10.1 · 实测环境 Sysmac Studio V1.68 64bit / Windows 11

非官方工具：用 Windows UI Automation 读取和操作欧姆龙 Sysmac Studio，并把批量工程操作固化成可重复执行的 Skill 脚本。MCP 部分是对第三方 `uiautomation-mcp` 的本地 HTTP 桥接；Skill 部分是面向 Agent 的操作手册与命令行脚本。

> 本仓库只包含可复用代码与文档，不包含现场工程、`.smc2`/`.slr` 产物、调试截图、日志、虚拟环境或任何本机绝对路径。

## 内容

```text
sysmac-studio-mcp/
  serve_http.py              本地 HTTP MCP 桥（只绑 127.0.0.1）
  start-mcp.ps1 / .bat       一次 UAC 启动；自动发现解释器；不杀无关进程
  setup.bat                  创建项目内 .venv 并安装依赖
  mcp_smoke_test.py          只读自检：握手 / 工具清单 / 窗口 / UIA 树
  requirements.txt           钉版依赖
  tools/
    sync_skill.py            把 skill/ 同步到 Qoder 用户 Skill 目录并校验
    check_release.py         发布前检查：绝对路径 / 二进制产物 / Python 语法
  skill/
    SKILL.md                 Agent 主入口：能力、边界、配方、安全红线
    README.md / requirements.txt   Skill 安装说明与脚本依赖子集
    scripts/                 Sysmac Studio 命令行驱动与归档校验脚本
    references/              控件树、坑清单、架构、回归清单
    examples/                EtherCAT 批量插入计划示例（通用设备名）
```

## 安装

要求 Windows 10/11、Python 3.10+，以及已合法安装并授权的 Sysmac Studio。本工具不读取、不输入、不导出任何序列号或授权文件。

```bat
cd /d "<本目录>"
setup.bat
```

等价手动命令：

```bat
cd /d "<本目录>"
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

依赖默认从 PyPI 安装到项目内 `.venv`，不污染系统解释器。需要离线安装时，自行准备与 `requirements.txt` 对应的 wheel，然后使用：

```bat
.venv\Scripts\python -m pip install --no-index --find-links "<wheel目录>" -r requirements.txt
```

## 启动 MCP

```bat
cd /d "<本目录>"
start-mcp.bat
```

双击或运行后会请求一次 UAC；服务器在提权窗口中前台运行。保持该窗口打开，按 `Ctrl+C` 或关闭窗口即可停止。

- 默认端口 `8765`。改端口：先 `set MCP_PORT=8766` 再运行 `start-mcp.bat`，或直接 `powershell -File start-mcp.ps1 -Port 8766`。
- 解释器优先级：`-Python` / `PYTHON` 环境变量 → 目录内 `.venv` → `venv` → PATH 中的 `python` / `python3` / `py`。
- 服务器只绑定 `127.0.0.1`，不接收外部主机连接；桥接器本身不发送遥测。
- 启动器不会强杀其它 Python 进程；端口被占用时会报错，请关闭旧服务或换端口。

为什么需要提权：Sysmac Studio 可能以 High IL 运行，普通权限 MCP 进程受 UIPI 限制读不到其 UIA 树。UIPI 不限制 loopback socket，因此普通权限客户端可以连接提权的本地 HTTP 服务。若目标软件本身不提权，可用 `python serve_http.py --allow-medium` 做普通权限调试。

## 自检与注册

另开一个普通权限终端：

```bat
cd /d "<本目录>"
.venv\Scripts\python mcp_smoke_test.py --port 8765
```

打开 Sysmac Studio 后做完整链路验证：

```bat
.venv\Scripts\python mcp_smoke_test.py --port 8765 --require-sysmac
```

在支持 MCP 的客户端中添加 URL 型服务器（通常需新开会话才生效）：

```json
{ "url": "http://127.0.0.1:8765/mcp" }
```

第三方 `uiautomation-mcp` 的两个已知行为：每次 `list_windows` 会清空内部 element 缓存，之前的 `elementId` 失效；返回里的 `processName` 实际是 ClassName，且不含 PID。需要精确 PID/HWND 时优先用 Skill 的 `ss.py wins`。

## 安装与使用 Skill

源稿唯一事实源是本目录下的 `skill/`。同步到 Qoder 用户 Skill 目录：

```bat
cd /d "<本目录>"
.venv\Scripts\python tools\sync_skill.py
.venv\Scripts\python tools\sync_skill.py --check
```

也可手动把 `skill/` 复制为 `%USERPROFILE%\.qoder-cn\skills\sysmac-studio-control\`。安装后新开会话加载。

直接运行 Skill 脚本示例（脚本本身也需要提权上下文）：

```bat
.venv\Scripts\python skill\scripts\ss.py wins
.venv\Scripts\python skill\scripts\ss.py state auto
.venv\Scripts\python skill\scripts\ss_uimap.py treelabels <pid> tree.txt
```

同机多个 Sysmac 实例时必须显式传 `<pid>`，不要依赖 `auto`。工程文件路径、输出目录、端口和解释器都由参数或环境变量传入；脚本不假设任何固定盘符或用户名。

## 安全边界

- 绝不读取、输入、导出序列号、授权文件或凭据；许可相关窗口只允许识别并避开。
- `online` / `download` / `upload` / `reset` / `drive_mode` / `program_mode` / `sync` 等会改变真实控制器状态的动作，没有用户当轮明确同意不得执行。
- 删除、重命名、另存为、导出覆盖前先确认目标工程已保存到磁盘，并先备份。
- 坐标、矩形和停靠布局必须现读；文档中的控件 ID 是版本相关线索，不是跨机器常量。
- 批量写入后必须真正落盘，并以文件哈希或归档内容复核，不能只看界面。

## 可移植性与验证

换机器或升级 Sysmac Studio 后，先跑 `skill/references/extending.md` 的回归清单。发布前检查：

```bat
.venv\Scripts\python tools\check_release.py
```

该检查会拒绝本机专属的 Windows 绝对路径（`C:\Windows`、`C:\Program Files` 等每台机器都一样的系统路径除外）、图片/工程/日志等产物，并用 AST 解析校验全部 Python 脚本语法（不生成 `__pycache__`）。运行时生成的日志、截图和工程产物已被 `.gitignore` 排除。

## 第三方依赖

MCP 服务实现来自 `uiautomation-mcp`（MIT），本仓库不内置其源码或虚拟环境，只通过 `requirements.txt` 声明依赖。其它依赖包括 `uiautomation`（Apache-2.0）、`fastmcp`（Apache-2.0）、`pillow`（MIT-CMU）。请遵守 Sysmac Studio 本身的许可条款；本项目与欧姆龙无官方关联。