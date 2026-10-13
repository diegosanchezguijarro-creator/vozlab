<#
    VozLab — run from source (no installer, no signed .exe needed).

    Use this when Windows Smart App Control blocks the unsigned VozLab-Setup.exe.
    The app is launched by your signed pythonw.exe, so SAC is happy, and you get
    the same tray app, wizard and settings.

    Usage (from the client folder of the repo):

        powershell -ExecutionPolicy Bypass -File tools\install_from_source.ps1
#>

$ErrorActionPreference = 'Stop'
$ClientDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$VenvDir   = Join-Path $ClientDir '.venv'
$AppData   = Join-Path $env:APPDATA 'VozLab'
$Shortcut  = Join-Path ([Environment]::GetFolderPath('Programs')) 'VozLab.lnk'

Write-Host "VozLab source install" -ForegroundColor Cyan
Write-Host "  source : $ClientDir"

# ---------------------------------------------------------------- python ----
$python = $null
foreach ($candidate in @('python', 'py')) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) {
        $args = if ($candidate -eq 'py') { @('-3', '--version') } else { @('--version') }
        try { & $candidate @args | Out-Null; $python = $candidate; break } catch { }
    }
}
if (-not $python) {
    throw "Python was not found. Install it first:  winget install -e --id Python.Python.3.12"
}
$version = (& $python --version) -replace 'Python ', ''
Write-Host "  python : $version ($python)"

# ------------------------------------------------------------------ venv ----
if (-not (Test-Path (Join-Path $VenvDir 'Scripts\pythonw.exe'))) {
    Write-Host "`nCreating virtual environment..." -ForegroundColor Cyan
    & $python -m venv $VenvDir
}
$venvPython = Join-Path $VenvDir 'Scripts\python.exe'
$venvPythonW = Join-Path $VenvDir 'Scripts\pythonw.exe'

Write-Host "`nInstalling dependencies (a minute or two)..." -ForegroundColor Cyan
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -r (Join-Path $ClientDir 'requirements.txt')

# -------------------------------------------------------------- shortcut ----
Write-Host "`nCreating Start Menu shortcut..." -ForegroundColor Cyan
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($Shortcut)
$link.TargetPath = $venvPythonW
$link.Arguments = '"' + (Join-Path $ClientDir 'run_vozlab.py') + '"'
$link.WorkingDirectory = $ClientDir
$link.IconLocation = (Join-Path $ClientDir 'assets\icon.ico')
$link.Description = 'VozLab — local voice dictation'
$link.Save()

New-Item -ItemType Directory -Force -Path $AppData | Out-Null

Write-Host "`nDone." -ForegroundColor Green
Write-Host "  Start menu : VozLab"
Write-Host "  Settings   : $AppData\config.json"
Write-Host "  Log        : $AppData\vozlab.log"
Write-Host "`nLaunching VozLab now (tray icon should appear)..."
Start-Process -FilePath $venvPythonW -ArgumentList ('"' + (Join-Path $ClientDir 'run_vozlab.py') + '"') -WorkingDirectory $ClientDir

Write-Host "`nTip: enable 'Start with Windows' in VozLab Settings to launch it at login."
