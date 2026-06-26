$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

python scripts\local_scheduler.py --once
if ($LASTEXITCODE -ne 0) {
    throw "Flight data update failed with exit code $LASTEXITCODE"
}
