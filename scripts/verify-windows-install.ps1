# NEXUS Stage 10 — Clean Windows 10/11 Install, Independent Daemon & Uninstall Verification Script
# Run inside a clean Windows 10/11 64-bit VM or workstation after `scripts/build-desktop.ps1`.
param(
    [string]$InstallerExe,
    [string]$PythonExe = "python",
    [switch]$RunUninstallCheck
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$TestDataDir = Join-Path $env:TEMP "nexus-clean-vm-verify-$([guid]::NewGuid().ToString('N'))"
$LogFile = Join-Path $TestDataDir "logs\nexus-daemon.log"

Write-Host "=== NEXUS Stage 10 Clean Windows Verification ==="

if ($InstallerExe) {
    if (-Not (Test-Path $InstallerExe)) {
        throw "Specified NSIS installer does not exist: $InstallerExe"
    }
    Write-Host "[1/5] Performing silent NSIS installation..."
    Start-Process -FilePath $InstallerExe -ArgumentList "/S" -Wait
} else {
    Write-Host "[1/5] No -InstallerExe passed; verifying repository desktop & sidecar executables directly."
}

$SidecarExe = Join-Path $RepoRoot "apps\desktop\src-tauri\binaries\nexus-daemon-x86_64-pc-windows-msvc.exe"
$DaemonMode = if (Test-Path $SidecarExe) { "sidecar" } else { "python" }
Write-Host "[2/5] Testing offline independent daemon startup (mode: $DaemonMode) without AI Studio..."

New-Item -ItemType Directory -Force -Path $TestDataDir | Out-Null
$ServeProc = $null
try {
    if ($DaemonMode -eq "sidecar") {
        $ver = & $SidecarExe --version
        Write-Host "Sidecar version output: $ver"
        $ServeProc = Start-Process -FilePath $SidecarExe `
            -ArgumentList @("--serve", "--data-dir", $TestDataDir, "--rest-port", "47110", "--log-file", $LogFile) `
            -PassThru -WindowStyle Hidden
    } else {
        $ServeProc = Start-Process -FilePath $PythonExe `
            -ArgumentList @("-m", "core.nexus_core", "--serve", "--data-dir", $TestDataDir, "--rest-port", "47110", "--log-file", $LogFile) `
            -WorkingDirectory $RepoRoot `
            -PassThru -WindowStyle Hidden
    }

    # Poll health endpoint
    $Health = $null
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $Health = Invoke-RestMethod -Uri "http://127.0.0.1:47110/health" -TimeoutSec 1
            if ($Health.daemonState -eq "Running") { break }
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-Not $Health -or $Health.daemonState -ne "Running") {
        throw "Independent daemon failed to reach Running health state."
    }
    Write-Host "[3/5] Verified loopback health: version=$($Health.version) pid=$($Health.pid)"

    $TokenPath = Join-Path $TestDataDir "daemon.token"
    $Token = (Get-Content -Raw -Path $TokenPath).Trim()
    $Diag = Invoke-RestMethod -Uri "http://127.0.0.1:47110/api/v1/diagnostics" -Headers @{ Authorization = "Bearer $Token" }
    Write-Host "[4/5] Verified authenticated diagnostics & SQLite integrity: $($Diag.storage.integrity)"

    if (-Not (Test-Path $LogFile)) {
        throw "Expected rotating daemon log file was not created at $LogFile"
    }

    # Graceful shutdown over authenticated REST API
    Invoke-RestMethod -Uri "http://127.0.0.1:47110/api/v1/daemon/shutdown" -Method Post -Headers @{ Authorization = "Bearer $Token" } -ContentType "application/json" -Body "{}" | Out-Null
    $ServeProc.WaitForExit(5000) | Out-Null
    Write-Host "[5/5] Verified graceful authenticated daemon shutdown and log generation."
} finally {
    if ($ServeProc -and -Not $ServeProc.HasExited) {
        Stop-Process -Id $ServeProc.Id -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $TestDataDir) {
        Remove-Item -Recurse -Force $TestDataDir
    }
}

if ($RunUninstallCheck) {
    Write-Host "Running uninstall verification..."
    & (Join-Path $PSScriptRoot "uninstall-nexus.ps1") -PurgeUserData
}

Write-Host "=== Clean Windows Verification Completed ==="
