@echo off
rem Sysmac Studio UIA MCP bridge. Author: hoverwu  Version: 0.2.0
rem Double-click to request one UAC prompt. The server runs in an elevated window.
rem Optional: set MCP_PORT=8766 before running this file.
setlocal
cd /d "%~dp0"
set "PORT=8765"
if defined MCP_PORT set "PORT=%MCP_PORT%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-mcp.ps1" -Port %PORT%
endlocal