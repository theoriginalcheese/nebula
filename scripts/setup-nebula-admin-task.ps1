# Registers NebulaRunElevated so a normal launch can come back as administrator
# without a UAC prompt every time. Approve UAC once when this script runs.
# Matching task name: obsauto/admin_launch.py -> NEBULA_ADMIN_TASK
# On-demand only (schtasks /run). It does not start Nebula at logon.

$ErrorActionPreference = "Stop"

$taskName = "NebulaRunElevated"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pythonw = "C:\Users\antho\AppData\Local\Programs\Python\Python312\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    $cmd = Get-Command pythonw -ErrorAction SilentlyContinue
    if ($cmd) { $pythonw = $cmd.Source }
}
$app = Join-Path $repo "spike\app.py"

if (-not (Test-Path $pythonw)) {
    Write-Error "pythonw not found at $pythonw"
    exit 1
}
if (-not (Test-Path $app)) {
    Write-Error "Nebula entry not found at $app"
    exit 1
}

$action = New-ScheduledTaskAction `
    -Execute $pythonw `
    -Argument ("`"{0}`" --show" -f $app) `
    -WorkingDirectory $repo

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
    -Description "Start Nebula as administrator so the dial can sit over elevated games. No UAC on later launches." `
    -Force | Out-Null

Write-Host "OK: Scheduled task '$taskName' created (RunLevel Highest)."
Write-Host "Test with: schtasks /run /tn $taskName"
