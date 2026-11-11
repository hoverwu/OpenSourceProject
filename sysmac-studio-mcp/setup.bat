@echo off
rem Create a project-local virtualenv and install dependencies.
rem Author: hoverwu  Version: 0.2.0
setlocal
cd /d "%~dp0"
if defined PYTHON (set "PY=%PYTHON%") else (set "PY=python")
echo Creating .venv with "%PY%" ...
"%PY%" -m venv .venv
if errorlevel 1 exit /b 1
echo Installing dependencies ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
echo Done. Run start-mcp.bat to start the elevated MCP bridge.
endlocal