<#
    Scribe updater — checks GitHub for a newer release and installs it in place.

        powershell -ExecutionPolicy Bypass -File update.ps1
        powershell -ExecutionPolicy Bypass -File update.ps1 -CheckOnly

    Your settings and logs live in %APPDATA%\VozLab and are never touched.
#>
[CmdletBinding()]
param(
    [string]$Repo = "diegosg-dev/vozlab",
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'Programs\VozLab'),
    [switch]$CheckOnly,
    [switch]$Force,
    [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Info($m) { Write-Host $m }
function Good($m) { Write-Host $m -ForegroundColor Green }
function Warn($m) { Write-Host $m -ForegroundColor Yellow }
function Fail($m) { Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }

$versionFile = Join-Path $InstallDir 'version.txt'
if (-not (Test-Path $versionFile)) {
    Fail "no Scribe installation found in $InstallDir (expected version.txt). Install it first with deploy.ps1."
}
$current = (Get-Content $versionFile -Raw).Trim()
Info "Scribe installed: $current"

Info "Checking GitHub for the latest release..."
try {
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" `
                                 -Headers @{ 'User-Agent' = 'VozLab-Updater' }
} catch {
    Fail "could not reach GitHub ($($_.Exception.Message))."
}
$latest = $release.tag_name
Info "Latest release  : $latest"

if ($latest -eq $current -and -not $Force) {
    Good "You are up to date."
    exit 0
}

if ($release.body) {
    Info ""
    Info "What's new in ${latest}:"
    $release.body -split "`n" | Select-Object -First 20 | ForEach-Object { Info "  $_" }
}

if ($CheckOnly) {
    Warn ""
    Warn "An update is available: $current -> $latest"
    Warn "Run this script without -CheckOnly to install it."
    exit 0
}

Info ""
Info "Updating $current -> $latest ..."

# Fetch the new installer from the tag we are upgrading to, so the update logic
# always matches the version being installed.
$deployUrl = "https://raw.githubusercontent.com/$Repo/$latest/installer/deploy.ps1"
$deployPath = Join-Path $env:TEMP ("vozlab-deploy-" + [guid]::NewGuid().ToString('N').Substring(0, 8) + ".ps1")
try {
    Invoke-WebRequest -UseBasicParsing -Uri $deployUrl -OutFile $deployPath
} catch {
    Fail "could not download the installer for $latest ($($_.Exception.Message))."
}

$deployArgs = @{
    Repo = $Repo
    Version = $latest.TrimStart('v')
    InstallDir = $InstallDir
}
if ($NoLaunch) { $deployArgs['NoLaunch'] = $true }

& $deployPath @deployArgs
$code = $LASTEXITCODE
Remove-Item -Force $deployPath -ErrorAction SilentlyContinue
if ($code -ne 0) { Fail "update failed (installer exited with $code)." }

Good ""
Good "Updated to $latest."
