@echo off
rem EasyBuilder X dedicated MCP server (normal privilege, Medium IL)
rem author: hoverwu  version: 0.2.0  (24 tools)
rem
rem Uses PYTHON if set, otherwise "python" from PATH.
rem Install deps with:  python -m pip install -r requirements.txt
cd /d "%~dp0"
if "%PYTHON%"=="" (
    set "PYTHON=python"
)
"%PYTHON%" ebx_mcp_server.py 8788
