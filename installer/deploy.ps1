<#
    Scribe installer — works even with Windows Smart App Control enabled.

    It does NOT run an unsigned .exe: it downloads the release source, verifies
    the SHA256, installs the Python dependencies into a private virtual
    environment and launches the app with your signed pythonw.exe.

    Usage
    -----
        # one-liner (PowerShell):
        irm https://raw.githubusercontent.com/<repo>/main/installer/deploy.ps1 | iex

        # or download Scribe.bat and run it, or:
        powershell -ExecutionPolicy Bypass -File deploy.ps1

    Options
    -------
        -Repo <owner/name>      GitHub repository (default: the official one)
        -Version <x.y.z>        Install a specific version instead of the latest
        -InstallDir <path>      Where to install (default %LOCALAPPDATA%\Programs\Scribe)
        -Autostart              Start Scribe when you sign in
        -NoShortcut             Do not create Start-menu/desktop shortcuts
        -NoDesktopIcon          Only create the Start-menu shortcut
        -NoLaunch               Install but do not start the app
        -SkipHashCheck          Do not verify the download checksum (not recommended)
#>
[CmdletBinding()]
param(
    [string]$Repo = "diegosg-dev/scribe",
    [string]$Version = "latest",
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'Programs\Scribe'),
    [switch]$Autostart,
    [switch]$NoShortcut,
    [switch]$NoDesktopIcon,
    [switch]$NoLaunch,
    [switch]$SkipHashCheck
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:Repo = $Repo

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Get-PythonExe {
    foreach ($candidate in @('python', 'py')) {
        if (-not (Get-Command $candidate -ErrorAction SilentlyContinue)) { continue }
        $probe = if ($candidate -eq 'py') { @('-3', '--version') } else { @('--version') }
        try {
            $out = & $candidate @probe 2>&1
            if ($LASTEXITCODE -eq 0 -and "$out" -match '^Python 3\.(1[1-9]|[2-9]\d)') {
                return (Get-Command $candidate -CommandType Application).Source
            }
        } catch { }
    }
    return $null
}

function Resolve-Release {
    param([string]$Requested)
    $headers = @{ 'User-Agent' = 'Scribe-Installer' }
    if ($Requested -and $Requested -ne 'latest') {
        $ver = $Requested.TrimStart('v')
        return @{ Tag = "v$ver"; Version = $ver }
    }
    Write-Host "  asking GitHub for the latest release..." -NoNewline
    try {
        $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$script:Repo/releases/latest" -Headers $headers
    } catch {
        Fail "could not reach GitHub ($($_.Exception.Message)). Check your internet connection."
    }
    $ver = $release.tag_name.TrimStart('v')
    Write-Host " $ver"
    return @{ Tag = $release.tag_name; Version = $ver }
}

# ---------------------------------------------------------------- preflight --
Write-Host ""
Write-Host "  Scribe installer" -ForegroundColor White
Write-Host "  ---------------" -ForegroundColor DarkGray

$python = Get-PythonExe
if (-not $python) {
    Write-Host ""
    Write-Host "Python 3.11+ was not found. Install it first (takes a minute):" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "    winget install -e --id Python.Python.3.12" -ForegroundColor White
    Write-Host ""
    Write-Host "Then run this installer again."
    exit 1
}
Write-Host "  python  : $(& $python --version)"

if ($InstallDir -eq (Join-Path $env:LOCALAPPDATA 'Programs\Scribe') -and
    (Test-Path (Join-Path $InstallDir 'Scribe.exe'))) {
    Write-Host ""
    Write-Host "  note: an installer-based Scribe exists in the same folder." -ForegroundColor Yellow
    Write-Host "        Uninstall it from Settings > Apps to avoid two copies listening" -ForegroundColor DarkGray
    Write-Host "        for the same dictation key." -ForegroundColor DarkGray
}

# ----------------------------------------------------------------- download --
$release = Resolve-Release -Requested $Version
$ver = $release.Version
$srcName = "Scribe-$ver-src.zip"
$baseUrl = "https://github.com/$Repo/releases/download/$($release.Tag)"

Write-Step "Downloading Scribe $ver"
$tmp = Join-Path $env:TEMP ("scribe-install-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$zipPath = Join-Path $tmp $srcName
try {
    Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/$srcName" -OutFile $zipPath
} catch {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    Fail "could not download $srcName ($($_.Exception.Message))."
}

if (-not $SkipHashCheck) {
    Write-Host "  verifying checksum..."
    $sumsPath = Join-Path $tmp 'SHA256SUMS'
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/SHA256SUMS" -OutFile $sumsPath
    } catch {
        Fail "could not download SHA256SUMS; re-run with -SkipHashCheck to override."
    }
    $expected = (Select-String -Path $sumsPath -Pattern ([regex]::Escape($srcName)) |
                 Select-Object -First 1).Line -split '\s+' | Select-Object -First 1
    $actual = (Get-FileHash -Algorithm SHA256 -Path $zipPath).Hash.ToLower()
    if (-not $expected) { Fail "no checksum found for $srcName in SHA256SUMS." }
    if ($expected -ne $actual) {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
        Fail "checksum mismatch! expected $expected but got $actual. Aborting."
    }
    Write-Host "  checksum OK" -ForegroundColor Green
}

# ------------------------------------------------------------------ extract --
Write-Step "Installing to $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# stop a running copy that lives in this folder
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='Scribe.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*$InstallDir*" } |
    ForEach-Object {
        Write-Host "  stopping running instance ($($_.ProcessId))..."
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

$appDir = Join-Path $InstallDir 'app'
if (Test-Path $appDir) { Remove-Item -Recurse -Force $appDir }

Expand-Archive -Path $zipPath -DestinationPath $tmp -Force
$inner = Join-Path $tmp 'Scribe'
if (-not (Test-Path $inner)) { Fail "unexpected archive layout (no Scribe folder)." }
Move-Item -Path $inner -Destination $appDir

# -------------------------------------------------------------------- venv ---
$venvDir = Join-Path $InstallDir '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$venvPythonW = Join-Path $venvDir 'Scripts\pythonw.exe'

if (-not (Test-Path $venvPython)) {
    Write-Step "Creating virtual environment"
    & $python -m venv $venvDir
    if (-not (Test-Path $venvPython)) { Fail "could not create the virtual environment." }
}

Write-Step "Installing dependencies (first time takes a couple of minutes)"
& $venvPython -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) { Fail "pip upgrade failed." }
& $venvPython -m pip install --quiet -r (Join-Path $appDir 'client\requirements.txt')
if ($LASTEXITCODE -ne 0) { Fail "dependency installation failed." }
Write-Host "  dependencies OK" -ForegroundColor Green

# --------------------------------------------------------------- shortcuts ---
$entryScript = Join-Path $appDir 'client\run_scribe.py'
$iconPath = Join-Path $appDir 'client\assets\icon.ico'
Set-Content -Path (Join-Path $InstallDir 'version.txt') -Value $release.Tag -Encoding ascii
Copy-Item -Path $PSCommandPath -Destination (Join-Path $InstallDir 'deploy.ps1') -Force -ErrorAction SilentlyContinue
$updateSource = Join-Path $PSScriptRoot 'update.ps1'
if (Test-Path $updateSource) {
    Copy-Item -Path $updateSource -Destination (Join-Path $InstallDir 'update.ps1') -Force
}

if (-not $NoShortcut) {
    Write-Step "Creating shortcuts"
    $shell = New-Object -ComObject WScript.Shell
    $targets = @()
    $targets += Join-Path ([Environment]::GetFolderPath('Programs')) 'Scribe.lnk'
    if (-not $NoDesktopIcon) { $targets += Join-Path ([Environment]::GetFolderPath('Desktop')) 'Scribe.lnk' }

    foreach ($path in $targets) {
        $link = $shell.CreateShortcut($path)
        $link.TargetPath = $venvPythonW
        $link.Arguments = '"' + $entryScript + '"'
        $link.WorkingDirectory = (Join-Path $appDir 'client')
        if (Test-Path $iconPath) { $link.IconLocation = $iconPath }
        $link.Description = 'Scribe — local voice dictation'
        $link.Save()
        Write-Host "  $path"
    }
}

# --- cleanup left over from the rename (VozLab -> Scribe) --------------------
$legacyLinks = @(
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'VozLab.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'VozLab.lnk')
)
foreach ($old in $legacyLinks) {
    if (Test-Path $old) {
        Remove-Item $old -Force -ErrorAction SilentlyContinue
        Write-Host "  removed old shortcut $old"
    }
}
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
if (Get-ItemProperty -Path $runKey -Name 'VozLab' -ErrorAction SilentlyContinue) {
    Remove-ItemProperty -Path $runKey -Name 'VozLab' -ErrorAction SilentlyContinue
    Write-Host "  removed old startup entry 'VozLab'"
}

if ($Autostart) {
    Write-Step "Enabling start with Windows"
    $runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    Set-ItemProperty -Path $runKey -Name 'Scribe' -Value ('"' + $venvPythonW + '" "' + $entryScript + '"')
    Write-Host "  registry Run entry added"
}

Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "  Scribe $ver installed" -ForegroundColor Green
Write-Host "  app     : $appDir\client"
Write-Host "  settings: $env:APPDATA\Scribe\config.json"
Write-Host "  logs    : $env:APPDATA\Scribe\scribe.log"
Write-Host ""
Write-Host "  Update later with:  powershell -ExecutionPolicy Bypass -File `"$InstallDir\update.ps1`""

if (-not $NoLaunch) {
    Write-Step "Starting Scribe"
    Start-Process -FilePath $venvPythonW -ArgumentList ('"' + $entryScript + '"') -WorkingDirectory (Join-Path $appDir 'client')
    Write-Host "  look for the microphone icon in the system tray"
}
