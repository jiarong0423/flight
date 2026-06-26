$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

function Invoke-Git {
    git @args
    if ($LASTEXITCODE -ne 0) {
        throw "git $args failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path ".git")) {
    Invoke-Git init
}

Invoke-Git branch -M main

$ExistingRemote = git remote
if ($ExistingRemote -notcontains "origin") {
    Invoke-Git remote add origin https://github.com/jiarong0423/flight.git
}

if (-not (git config user.name)) {
    Invoke-Git config user.name "jiarong0423"
}

if (-not (git config user.email)) {
    Invoke-Git config user.email "259321806+jiarong0423@users.noreply.github.com"
}

Invoke-Git add .
Invoke-Git commit -m "Initial GitHub Pages flight calendar"
Invoke-Git push -u origin main

Write-Host "Pushed to https://github.com/jiarong0423/flight"
Write-Host "Now open Settings > Pages and select: Deploy from a branch / main / root"
