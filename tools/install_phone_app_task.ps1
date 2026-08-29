<#
.SYNOPSIS
    Install (or refresh) the boot-time scheduled task that serves the phone app.

.DESCRIPTION
    Registers "NebulaPhoneApp" to run tools/serve_phone_app.py at system start,
    so the iOS home-screen app is reachable after a reboot without anyone
    logging in.

    At-Startup, deliberately unlike the machine's other Nebula-adjacent tasks
    (IdleSleep, LlamaSwap, NebulaLaunchOBS), which are user-session logon tasks
    because they need a desktop session - CUDA and input detection are not
    available to session 0. A file server needs none of that, and an at-logon
    task would stay dead after a reboot until someone logged in, which is
    exactly what this is meant to avoid.

    Runs as the interactive user via S4U rather than as SYSTEM. S4U starts
    without a login and without a stored password, and - the reason it matters
    here - user-profile paths resolve correctly. The games list lives in the
    sync folder under the user's home, so under SYSTEM it would resolve
    somewhere else and the phone would report an empty library. Pass
    -RunAsSystem to override; expect a thinner Games screen if you do.

    The agent inside desktop Nebula is not started here. When it is up the
    server proxies to it (richer: OBS knows the scene and bitrate); when it is
    not, the server builds the same payload from files via
    obsauto/phone_state.py. So a bare reboot with nobody logged in still shows
    recording state, clips, activity, games, peers and the disk forecast.

.NOTES
    Must be run from an elevated PowerShell. SYSTEM tasks are also invisible to
    unelevated `Get-ScheduledTask`, so query them elevated too - "not found"
    from a normal shell means permissions, not absence.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\install_phone_app_task.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\install_phone_app_task.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'NebulaPhoneApp',
    [int]$Port = 8766,
    # Tailscale has no address for a while after boot; the server retries
    # rather than exiting into a race it cannot win.
    [int]$WaitSeconds = 300,
    [switch]$RunAsSystem,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo 'tools\serve_phone_app.py'
# Match the interpreter desktop Nebula itself runs on (see the Startup folder's
# Nebula.cmd), not whatever happens to be first on PATH.
$python = 'C:\Users\antho\AppData\Local\Programs\Python\Python313\pythonw.exe'

function Assert-Elevated {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this from an elevated PowerShell - registering a SYSTEM task needs admin."
    }
}

Assert-Elevated

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
$dist = Join-Path $repo 'mobile\dist'
if (-not (Test-Path $dist)) {
    throw "No build at $dist`nRun: cd mobile; npx expo export --platform web"
}

$action = New-ScheduledTaskAction -Execute $python `
    -Argument "`"$script`" --port $Port --wait $WaitSeconds" `
    -WorkingDirectory $repo

$trigger = New-ScheduledTaskTrigger -AtStartup

if ($RunAsSystem) {
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' `
        -LogonType ServiceAccount -RunLevel Highest
    $who = 'SYSTEM'
} else {
    # S4U: runs at startup with no login and no stored password, while still
    # resolving this user's profile paths.
    $who = "$env:USERDOMAIN\$env:USERNAME"
    $principal = New-ScheduledTaskPrincipal -UserId $who `
        -LogonType S4U -RunLevel Limited
}

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description 'Serves the Nebula iOS companion on the tailnet and proxies /v1 to the phone agent.' | Out-Null

"Registered '$TaskName' (runs as $who, at startup, port $Port)."
"Start it now with:  Start-ScheduledTask -TaskName $TaskName"
