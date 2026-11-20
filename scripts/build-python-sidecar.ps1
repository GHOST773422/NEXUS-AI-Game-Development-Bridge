# NEXUS Stage 10 — Build Standalone Python 3.12+ Sidecar Executable (Windows x64)
# Produces apps/desktop/src-tauri/binaries/nexus-daemon-x86_64-pc-windows-msvc.exe
param(
    [string]$PythonExe = "python",
    [switch]$SkipSelfTest
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BinDir = Join-Path $RepoRoot "apps\desktop\src-tauri\binaries"
$TargetName = "nexus-daemon-x86_64-pc-windows-msvc"
$SidecarPath = Join-Path $BinDir "$TargetName.exe"
$WorkDir = Join-Path $env:TEMP "nexus-pyinstaller-build"

Write-Host "=== NEXUS Sidecar Build (Target: Windows x86_64) ==="
$pyVersion = & $PythonExe --version 2>&1
Write-Host "Using Python: $pyVersion"

& $PythonExe -c "import sys; assert sys.version_info >= (3, 12), f'Python 3.12+ required, found {sys.version}'"
& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -e "$RepoRoot\core[packaging]"

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

$EntryScript = Join-Path $WorkDir "nexus_daemon_entry.py"
Set-Content -Path $EntryScript -Encoding UTF8 -Value @"
import sys
from core.nexus_core.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
"@

Push-Location $RepoRoot
try {
    & $PythonExe -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --console `
        --name $TargetName `
        --distpath $BinDir `
        --workpath (Join-Path $WorkDir "build") `
        --specpath $WorkDir `
        --paths $RepoRoot `
        --collect-submodules core.nexus_core `
        --collect-submodules integrations `
        --collect-submodules sdk `
        --hidden-import aiosqlite `
        --hidden-import fastapi `
        --hidden-import uvicorn `
        --hidden-import websockets `
        --hidden-import mcp `
        $EntryScript
} finally {
    Pop-Location
}

if (-Not (Test-Path $SidecarPath)) {
    throw "PyInstaller finished without creating expected binary: $SidecarPath"
}

if (-Not $SkipSelfTest) {
    $TestDataDir = Join-Path $env:TEMP "nexus-sidecar-selftest-$([guid]::NewGuid().ToString('N'))"
    try {
        $verOutput = & $SidecarPath --version
        Write-Host "Sidecar --version: $verOutput"
        $healthOutput = & $SidecarPath --health-once --data-dir $TestDataDir
        Write-Host "Sidecar --health-once verified ($TestDataDir)."
    } finally {
        if (Test-Path $TestDataDir) {
            Remove-Item -Recurse -Force $TestDataDir
        }
    }
}

Write-Host "Built sidecar binary: $SidecarPath"
