<#
.SYNOPSIS
    Install (or refresh) the boot-time scheduled task that serves the phone app.

.DESCRIPTION
    Registers "NebulaPhoneApp" to run tools/serve_phone_app.py at system start,
    so the iOS home-screen app is reachable after a reboot without anyone
    logging in.

    Runs as SYSTEM with an At-Startup trigger, deliberately unlike the
    machine's other Nebula-adjacent tasks (IdleSleep, LlamaSwap,
    NebulaLaunchOBS), which are user-session logon tasks because they need a
    desktop session - CUDA and input detection are not available to session 0.
    A static file server needs none of that, and an at-logon task would stay
    dead after a reboot until someone logged in, which is exactly what this is
    meant to avoid.

    The agent itself is not started here: it lives inside desktop Nebula, which
    already auto-starts from the Startup folder at logon. So after a bare
    reboot the app loads and honestly reports the studio as unreachable until
    you log in.

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

$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' `
    -LogonType ServiceAccount -RunLevel Highest

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

"Registered '$TaskName' (SYSTEM, at startup, port $Port)."
"Start it now with:  Start-ScheduledTask -TaskName $TaskName"
