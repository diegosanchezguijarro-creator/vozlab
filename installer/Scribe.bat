@echo off
rem Scribe installer — double-click friendly wrapper around deploy.ps1
rem Works with Smart App Control enabled (no unsigned .exe is executed).
setlocal

set "REPO=diegosg-dev/scribe"
set "SCRIPT=%~dp0deploy.ps1"

if not exist "%SCRIPT%" (
    set "SCRIPT=%TEMP%\scribe-deploy.ps1"
    echo Downloading the installer from GitHub...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "try { Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/%REPO%/main/installer/deploy.ps1' -OutFile '%TEMP%\scribe-deploy.ps1' } catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }"
    if errorlevel 1 (
        echo.
        echo Could not download the installer. Check your internet connection.
        pause
        exit /b 1
    )
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
set "CODE=%ERRORLEVEL%"

echo.
if "%CODE%"=="0" (
    echo Scribe is ready. Look for the microphone icon in the system tray.
) else (
    echo Installation failed ^(code %CODE%^). See the messages above.
)
pause
exit /b %CODE%
