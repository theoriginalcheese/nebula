<#
.SYNOPSIS
    Logon task that keeps tools/nebula_on_game.py running.

.DESCRIPTION
    Registers "NebulaOnGame" to start at logon and run until logoff. A game
    only exists in an interactive session, so this is an AtLogOn task for the
    current user, not a SYSTEM startup task. No elevation required.

    The watcher is the thing that stays up. Nebula itself is started only
    when a known game exe is running, and it starts hidden in the tray.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\install_nebula_on_game_task.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\install_nebula_on_game_task.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'NebulaOnGame',
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo 'tools\nebula_on_game.py'
$python = 'C:\Users\antho\AppData\Local\Programs\Python\Python313\pythonw.exe'
if (-not (Test-Path $python)) {
    $python = Join-Path (Split-Path -Parent (Get-Command python -ErrorAction Stop).Source) 'pythonw.exe'
}

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        "Removed scheduled task '$TaskName'."
    } else {
        "No scheduled task named '$TaskName'."
    }
    return
}

foreach ($p in @($script, $python)) {
    if (-not (Test-Path $p)) { throw "Missing: $p" }
}

$action = New-ScheduledTaskAction -Execute $python `
    -Argument "`"$script`"" `
    -WorkingDirectory $repo

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME `
    -LogonType Interactive -RunLevel Limited

# Zero limit: the default kills a task after 72 hours. This one is the
# always-on piece. IgnoreNew so a second logon does not stack watchers.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description 'Stays running and starts Nebula, hidden, when a known game exe appears.' | Out-Null

"Registered '$TaskName' (at logon, as $env:USERNAME, no time limit)."
"Start it now with:  Start-ScheduledTask -TaskName $TaskName"
