# Windows Server 2019 — Pisces bot

The bot is a Python process. On Server 2019 it runs as a **scheduled task at startup** (`PiscesSupportBot`), not as systemd.

## 1. On this PC — copy the project

Copy the **whole** `Pisces` folder to the server (RDP, USB, or a share). Include:

- all `.py` files
- `requirements.txt`
- `.env` (API keys + Zoho SMTP)
- `knowledge\` (all PDFs)
- `scripts\`

Suggested path on the server:

```text
C:\Pisces
```

Do **not** copy `venv\` from your laptop — the installer creates a new one on the server.

## 2. On the server — install Python (once)

1. Log in as Administrator.
2. Install **Python 3.11 or 3.12** from https://www.python.org/downloads/windows/
   - **Install for all users**
   - **Add python.exe to PATH**
3. Open a **new** Administrator PowerShell and check:

```powershell
py -3 --version
```

## 3. On the server — install and start the bot

```powershell
Set-ExecutionPolicy -Scope Process Bypass
cd C:\Pisces
powershell -ExecutionPolicy Bypass -File .\scripts\Install-PiscesWindows.ps1
```

That script:

- creates `C:\Pisces\venv`
- installs `requirements.txt` (including `pypdf` for the knowledge PDFs)
- runs `python main.py --test-connections`
- registers **PiscesSupportBot** to start at boot as **SYSTEM**
- starts it now (continuous, every 5 minutes)

## 4. Confirm it is running

```powershell
Get-ScheduledTask -TaskName PiscesSupportBot
Get-Content C:\Pisces\pisces_support_bot.log -Tail 80
```

Task **State** should be `Running`. Logs should show Gemini + SDP, and SMTP if `.env` is filled in.

## 5. Network (Server 2019 firewall)

Allow **outbound**:

| Destination | Port | Why |
|-------------|------|-----|
| ServiceDesk Plus (`122.165.246.80`) | 8081 | tickets |
| `generativelanguage.googleapis.com` | 443 | Gemini |
| `smtp.zoho.in` | 465 | customer email |

Inbound ports are not required.

## 6. Day-to-day commands

```powershell
# Stop
Stop-ScheduledTask -TaskName PiscesSupportBot

# Start
Start-ScheduledTask -TaskName PiscesSupportBot

# Restart
Stop-ScheduledTask -TaskName PiscesSupportBot
Start-ScheduledTask -TaskName PiscesSupportBot

# One-off test (stop the task first so two bots don't run)
cd C:\Pisces
.\venv\Scripts\python.exe main.py --test-connections
.\venv\Scripts\python.exe test_knowledge.py
.\venv\Scripts\python.exe main.py --mode once

# Uninstall the startup task
powershell -ExecutionPolicy Bypass -File C:\Pisces\scripts\Uninstall-PiscesWindows.ps1
```

## 7. After you change code or PDFs

Copy the new files onto `C:\Pisces` (keep `.env`), then:

```powershell
cd C:\Pisces
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Stop-ScheduledTask -TaskName PiscesSupportBot
Start-ScheduledTask -TaskName PiscesSupportBot
```
