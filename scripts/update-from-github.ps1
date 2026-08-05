# Pull the latest Nebula source from GitHub (ff-only).
# Use this on a laptop/desktop that runs `python main.py` from a git clone.
# Packaged Nebula.exe users: Settings → Updates → Check for updates instead.
#
# Usage (from the repo root, or anywhere):
#   powershell -ExecutionPolicy Bypass -File scripts\update-from-github.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $root ".git"))) {
    Write-Error "Not a git checkout: $root"
    exit 1
}

Set-Location $root
Write-Host "Fetching origin..."
git fetch origin
$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if (-not $branch) { $branch = "main" }
Write-Host "Fast-forwarding $branch from origin/$branch ..."
git pull --ff-only origin $branch
Write-Host "Done. Current HEAD:"
git log -1 --oneline
Write-Host ""
Write-Host "Restart Nebula (python main.py) to load the new code."
