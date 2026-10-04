#Requires -Version 5.1
<#
.SYNOPSIS
  Install Pisces on Windows Server 2019: venv, dependencies, 24/7 scheduled task.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\Install-PiscesWindows.ps1
#>
param(
    [string]$InstallPath = "",
    [int]$IntervalMinutes = 5,
    [switch]$SkipTask
)

$ErrorActionPreference = "Stop"

if (-not $InstallPath) {
    $InstallPath = Split-Path -Parent $PSScriptRoot
}
# Allow running from Desktop\Pisces or C:\Pisces without extra flags.
$InstallPath = (Resolve-Path $InstallPath).Path
$PythonExe = Join-Path $InstallPath "venv\Scripts\python.exe"
$BatPath = Join-Path $PSScriptRoot "Run-PiscesBot.bat"
$TaskName = "PiscesSupportBot"

Write-Host "Install path: $InstallPath"

function Find-Python {
    $candidates = @(
        @{ Cmd = "py"; Args = @("-3") },
        @{ Cmd = "python"; Args = @() },
        @{ Cmd = "python3"; Args = @() }
    )
    foreach ($c in $candidates) {
        $cmd = Get-Command $c.Cmd -ErrorAction SilentlyContinue
        if ($cmd) {
            return @{ File = $cmd.Source; PrefixArgs = $c.Args }
        }
    }
    return $null
}

$python = Find-Python
if (-not $python) {
    Write-Host @"
Python was not found on PATH.

On Windows Server 2019:
1. Download Python 3.11 or 3.12 from https://www.python.org/downloads/windows/
2. Run the installer as Administrator
3. Check: Install for all users
4. Check: Add python.exe to PATH
5. Re-open this PowerShell window and run this script again
"@
    exit 1
}

Write-Host "Using Python: $($python.File)"

Set-Location $InstallPath

if (-not (Test-Path (Join-Path $InstallPath ".env"))) {
    Write-Warning ".env not found. Copy your working .env onto this server before starting the bot."
}

$knowledgeDir = Join-Path $InstallPath "knowledge"
$pdfCount = @(Get-ChildItem -Path $knowledgeDir -Filter "*.pdf" -ErrorAction SilentlyContinue).Count
Write-Host "Knowledge PDFs found: $pdfCount"
if ($pdfCount -lt 1) {
    Write-Warning "No PDFs in knowledge\. Copy the knowledge folder from your PC or answers will be weak."
}

if (-not (Test-Path $PythonExe)) {
    Write-Host "Creating virtual environment..."
    & $python.File @($python.PrefixArgs + @("-m", "venv", "venv"))
}

Write-Host "Installing Python packages..."
& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r (Join-Path $InstallPath "requirements.txt")

Write-Host "Running connection test..."
& $PythonExe (Join-Path $InstallPath "main.py") --test-connections
$testExit = $LASTEXITCODE

if ($SkipTask) {
    Write-Host "Skipping scheduled-task install (-SkipTask)."
    exit $testExit
}

Write-Host "Registering scheduled task '$TaskName' (runs at startup as SYSTEM)..."

$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$BatPath`"" `
    -WorkingDirectory $InstallPath

$trigger = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
$settings.ExecutionTimeLimit = "PT0S"

$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "PiscesER1 Marine support bot polls ServiceDesk Plus and replies from the knowledge base" `
    -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 2
Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State

$logFile = Join-Path $InstallPath "pisces_support_bot.log"
Write-Host ""
Write-Host "Done."
Write-Host ""
Write-Host "Useful commands:"
Write-Host "  Get-ScheduledTask -TaskName $TaskName"
Write-Host "  Get-Content `"$logFile`" -Tail 50"
Write-Host "  Stop-ScheduledTask -TaskName $TaskName"
Write-Host "  Start-ScheduledTask -TaskName $TaskName"
Write-Host ""
Write-Host "If SMTP failed in the connection test, fix SMTP settings in .env then restart the task."

exit 0
