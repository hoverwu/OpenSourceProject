# Start the Sysmac Studio UIA MCP bridge in an elevated foreground window.
# Author: hoverwu | Version: 0.2.0
#
# Interpreter order: -Python / PYTHON env var > .venv > venv > PATH.
# This script does not kill unrelated Python processes. If the port is busy,
# it stops and asks you to choose another port or close the existing server.
param(
    [int]$Port = 8765,
    [string]$Python = ''
)

$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot
$srv = Join-Path $dir 'serve_http.py'
if (-not (Test-Path -LiteralPath $srv)) {
    throw "Missing server script: $srv"
}
if ($Port -lt 1 -or $Port -gt 65535) {
    throw 'Port must be between 1 and 65535.'
}

function Resolve-Python {
    param([string]$Explicit)
    $candidates = @()
    if ($Explicit) { $candidates += $Explicit }
    if ($env:PYTHON) { $candidates += $env:PYTHON }
    $candidates += (Join-Path $dir '.venv\Scripts\python.exe')
    $candidates += (Join-Path $dir 'venv\Scripts\python.exe')
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    foreach ($name in @('python', 'python3', 'py')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    throw 'Python not found. Install Python 3.10+, create .venv, or set PYTHON=<python.exe>.'
}

$py = Resolve-Python -Explicit $Python
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$admin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $admin) {
    $ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $argLine = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -Port {1} -Python "{2}"' -f $PSCommandPath, $Port, $py
    Start-Process -FilePath $ps -Verb RunAs -ArgumentList $argLine
    Write-Host "Requested elevation for port $Port. Approve the UAC prompt; the server runs in the new window."
    return
}

$listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
if ($listeners | Where-Object { $_.Port -eq $Port }) {
    throw "Port $Port is already in use. Close the existing server or choose another port with -Port <number>."
}

Write-Host "Starting uiautomation-mcp on http://127.0.0.1:$Port/mcp"
Write-Host "Python: $py"
Write-Host 'Keep this window open while the MCP client is connected. Press Ctrl+C or close the window to stop.'
& $py $srv --port $Port
exit $LASTEXITCODE