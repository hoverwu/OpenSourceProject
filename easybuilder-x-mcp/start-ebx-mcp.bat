@echo off
rem EasyBuilder X dedicated MCP server (normal privilege, Medium IL)
rem author: hoverwu  version: 0.2.0  (24 tools)
rem
rem Interpreter order: PYTHON env var > .venv\Scripts\python.exe > venv\Scripts\python.exe > python on PATH
rem Install deps with:  python -m pip install -r requirements.txt
cd /d "%~dp0"
if "%PYTHON%"=="" if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON=%~dp0.venv\Scripts\python.exe"
if "%PYTHON%"=="" if exist "%~dp0venv\Scripts\python.exe" set "PYTHON=%~dp0venv\Scripts\python.exe"
if "%PYTHON%"=="" set "PYTHON=python"
"%PYTHON%" ebx_mcp_server.py 8788
