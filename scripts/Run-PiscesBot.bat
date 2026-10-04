@echo off
setlocal
cd /d "%~dp0\.."

if not exist "venv\Scripts\python.exe" (
  echo ERROR: venv is missing. Run scripts\Install-PiscesWindows.ps1 as Administrator first.
  exit /b 1
)

if not exist ".env" (
  echo ERROR: .env is missing. Copy .env from your PC or from .env.example and fill in keys.
  exit /b 1
)

venv\Scripts\python.exe main.py --mode continuous --interval 5
exit /b %ERRORLEVEL%
