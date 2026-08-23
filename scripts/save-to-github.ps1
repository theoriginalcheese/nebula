# Save this checkout onto origin/main (same as Settings → Updates → Save this machine).
# Packaged Nebula.exe users: Settings → Updates → Check for updates instead.
#
# Usage (from the repo root, or anywhere):
#   powershell -ExecutionPolicy Bypass -File scripts\save-to-github.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $root ".git"))) {
    Write-Error "Not a git checkout: $root"
    exit 1
}

Set-Location $root
python -m obsauto.updater save
exit $LASTEXITCODE
