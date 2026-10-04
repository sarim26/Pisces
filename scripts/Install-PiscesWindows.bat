@echo off
setlocal
cd /d "%~dp0\.."

echo Installing Pisces from: %CD%
echo.

where py >nul 2>&1
where python >nul 2>&1

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-PiscesWindows.ps1"
set EXITCODE=%ERRORLEVEL%

echo.
if %EXITCODE% NEQ 0 (
  echo Install finished with errors. If you saw "python was not found", install Python 3.11/3.12 and tick "Add python.exe to PATH".
) else (
  echo Install script finished.
)
pause
exit /b %EXITCODE%
