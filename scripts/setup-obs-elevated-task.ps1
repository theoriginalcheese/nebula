# Creates the NebulaLaunchOBS scheduled task so Nebula can start OBS elevated
# without a UAC prompt on every launch. Approve UAC once when this script runs.
# Matching task name: obsauto/monitor.py -> OBS_LAUNCH_TASK_NAME

$ErrorActionPreference = "Stop"

$taskName = "NebulaLaunchOBS"
$obs = "C:\Program Files\obs-studio\bin\64bit\obs64.exe"
$work = "C:\Program Files\obs-studio\bin\64bit"

if (-not (Test-Path $obs)) {
    Write-Error "OBS not found at $obs"
    exit 1
}

$action = New-ScheduledTaskAction `
    -Execute $obs `
    -Argument "--minimize-to-tray" `
    -WorkingDirectory $work

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Principal $principal `
    -Settings $settings `
    -Description "Launch OBS elevated for Nebula (Hoyoverse fullscreen capture) without UAC on each start." `
    -Force | Out-Null

Write-Host "OK: Scheduled task '$taskName' created (RunLevel Highest)."
Write-Host "Test with: schtasks /run /tn $taskName"
