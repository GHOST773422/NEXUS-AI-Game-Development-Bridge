# NEXUS Windows Optional Independent Background Service Registration
# Registers python -m core.nexus_core --serve so external AI/MCP clients and game engines
# can run headlessly even without opening the Tauri Desktop UI.
param(
    [string]$TaskName = "NEXUS-Core-Daemon",
    [string]$PythonExe = "python",
    [string]$DataDir = (Join-Path $env:LOCALAPPDATA "NEXUS"),
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"

if ($Unregister) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Unregistered scheduled task '$TaskName'."
    } else {
        Write-Host "Scheduled task '$TaskName' was not registered."
    }
    exit 0
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogFile = Join-Path $DataDir "logs\nexus-daemon.log"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogFile) | Out-Null

$Args = "-m core.nexus_core --serve --data-dir `"$DataDir`" --log-file `"$LogFile`""
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument $Args -WorkingDirectory $RepoRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "NEXUS AI Game Development Bridge Background Daemon" -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Registered and started independent NEXUS daemon task '$TaskName' (DataDir: $DataDir)."
