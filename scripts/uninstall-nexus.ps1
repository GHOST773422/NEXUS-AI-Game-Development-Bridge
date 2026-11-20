# NEXUS Clean Windows Uninstaller Helper
# Stops running daemon gracefully, removes optional background service task, runs app uninstaller if present,
# and optionally purges user config/DB in %LOCALAPPDATA%\NEXUS while preserving user game projects.
param(
    [switch]$PurgeUserData,
    [string]$DataDir = (Join-Path $env:LOCALAPPDATA "NEXUS"),
    [string]$RestEndpoint = "http://127.0.0.1:47100",
    [string]$TaskName = "NEXUS-Core-Daemon"
)

$ErrorActionPreference = "Stop"
Write-Host "=== NEXUS Windows Uninstallation Helper ==="

# 1. Request authenticated graceful shutdown if daemon is listening on loopback
$TokenPath = Join-Path $DataDir "daemon.token"
if (Test-Path $TokenPath) {
    $Token = (Get-Content -Raw -Path $TokenPath).Trim()
    if ($Token) {
        try {
            Invoke-RestMethod `
                -Uri "$RestEndpoint/api/v1/daemon/shutdown" `
                -Method Post `
                -Headers @{ Authorization = "Bearer $Token" } `
                -ContentType "application/json" `
                -Body "{}" `
                -TimeoutSec 2 | Out-Null
            Write-Host "Requested graceful daemon shutdown via loopback REST API."
            Start-Sleep -Milliseconds 600
        } catch {
            Write-Host "Daemon REST shutdown not needed or already stopped."
        }
    }
}

# 2. Remove scheduled background service task if registered
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task '$TaskName'."
}

# 3. Terminate any remaining NEXUS desktop or sidecar executables cleanly
foreach ($procName in @("nexus-desktop", "NEXUS", "nexus-daemon", "nexus-daemon-x86_64-pc-windows-msvc")) {
    Get-Process -Name $procName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

# 4. Run installed NSIS uninstaller silently if present in Program Files or LocalAppData
$UninstallerCandidates = @(
    (Join-Path $env:ProgramFiles "NEXUS\uninstall.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\NEXUS\uninstall.exe"),
    (Join-Path $env:LOCALAPPDATA "NEXUS\uninstall.exe")
)
foreach ($uninst in $UninstallerCandidates) {
    if (Test-Path $uninst) {
        Write-Host "Running NSIS uninstaller silently: $uninst /S"
        Start-Process -FilePath $uninst -ArgumentList "/S" -Wait
    }
}

# 5. Purge local NEXUS data/tokens/logs only when explicitly requested
if ($PurgeUserData -and (Test-Path $DataDir)) {
    Remove-Item -Recurse -Force $DataDir
    Write-Host "Purged local NEXUS runtime data directory: $DataDir"
} elseif (Test-Path $DataDir) {
    Write-Host "Preserved user configuration and SQLite history at: $DataDir (pass -PurgeUserData to remove)."
}

Write-Host "NEXUS Windows cleanup completed."
