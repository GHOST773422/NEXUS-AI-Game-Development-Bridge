# NEXUS Windows 10/11 64-bit Tauri 2 Desktop & Installer Build Script
param(
    [switch]$ServiceMode,
    [switch]$SkipSidecar,
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "=== NEXUS Stage 10 Windows Build Pipeline ==="

# 1. Verify documented Windows prerequisites cleanly
foreach ($tool in @("node", "npm", "cargo", "rustc")) {
    if (-Not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Required build prerequisite '$tool' not found on PATH. See docs/WINDOWS_PACKAGING_AND_INSTALL.md."
    }
}

Write-Host "Node: $(node --version) | Rust: $(rustc --version)"
Write-Host "Checking Python 3.12+..."
& $PythonExe -c "import sys; assert sys.version_info >= (3, 12), f'Python 3.12+ required, found {sys.version}'"

$TauriVersion = cargo tauri --version 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Tauri CLI v2 is required (`cargo install tauri-cli --version '^2.0.0'`)."
}
Write-Host "Tauri CLI: $TauriVersion"

Push-Location $RepoRoot
try {
    Write-Host "[1/5] Syncing Godot addon & staging bundled Unity/Godot adapter resources..."
    npm run sync:godot-addon
    npm run stage:adapters

    if (-Not $SkipSidecar -and -Not $ServiceMode) {
        Write-Host "[2/5] Building standalone PyInstaller sidecar (nexus-daemon-x86_64-pc-windows-msvc.exe)..."
        & (Join-Path $PSScriptRoot "build-python-sidecar.ps1") -PythonExe $PythonExe
    } else {
        Write-Host "[2/5] Skipping embedded sidecar (ServiceMode / SkipSidecar enabled)."
    }

    Write-Host "[3/5] Installing Node dependencies and building offline Vite frontend bundle..."
    if (-Not (Test-Path (Join-Path $RepoRoot "node_modules"))) {
        npm ci
    }
    npm run build

    Write-Host "[4/5] Verifying Python Core & Frontend test suites..."
    & $PythonExe -m unittest discover -s tests/python -p "test_*.py"
    npm test

    Write-Host "[5/5] Compiling Rust Tauri 2 shell and generating Windows NSIS / MSI installers..."
    Push-Location (Join-Path $RepoRoot "apps\desktop\src-tauri")
    $OverridePath = $null
    try {
        if ($ServiceMode -or $SkipSidecar) {
            $OverridePath = Join-Path ([System.IO.Path]::GetTempPath()) "nexus-tauri-nosidecar.json"
            '{"bundle":{"externalBin":[]}}' | Set-Content -Path $OverridePath -Encoding UTF8
            cargo tauri build --config $OverridePath
        } else {
            cargo tauri build
        }
    } finally {
        if ($OverridePath -and (Test-Path $OverridePath)) {
            Remove-Item $OverridePath -Force -ErrorAction SilentlyContinue
        }
        Pop-Location
    }

    $BundleRoot = Join-Path $RepoRoot "apps\desktop\src-tauri\target\release\bundle"
    Write-Host "=== Windows Build Complete ==="
    if (Test-Path $BundleRoot) {
        Get-ChildItem -Path $BundleRoot -Recurse -Include *.exe,*.msi | ForEach-Object {
            Write-Host "Installer artifact: $($_.FullName)"
        }
    }
} finally {
    Pop-Location
}
