# PiscesER1 Marine Support Bot - Deployment Guide

## Overview

This bot automatically responds to customer support tickets in ServiceDesk Plus using Google Gemini AI.

## Prerequisites

- Python 3.8 or higher
- ServiceDesk Plus (On-Premise) with API access enabled
- Google Gemini API key
- Internet connection (for Gemini API calls only)

## Quick Start

### 1. Install Dependencies

```powershell
cd C:\path\to\Pisces
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and update with your values:

```powershell
copy .env.example .env
```

Edit `.env` file with your configuration:

```env
# ServiceDesk Plus Configuration
SDP_BASE_URL=http://your-servicedesk-server:8081/api/v3
SDP_API_KEY=YOUR_SERVICEDESK_API_KEY

# Gemini AI Configuration
GEMINI_API_KEY=YOUR_GEMINI_API_KEY

# Email Escalation Contacts (optional)
EMERGENCY_CONTACT=emergency@yourcompany.com
SENIOR_MANAGER=manager@yourcompany.com
TECHNICAL_LEAD=techlead@yourcompany.com
```

### 3. Test Connections

```powershell
python main.py --test-connections
```

You should see:
```
ServiceDesk Plus API connection successful
Gemini API connection successful
All connection tests passed!
```

### 4. Run the Bot

**Run once (process current tickets):**
```powershell
python main.py --mode once
```

**Run continuously (recommended for production):**
```powershell
python main.py --mode continuous --interval 5
```

---

## Deployment Options

### Option 1: Windows Task Scheduler (Simplest)

1. Open Task Scheduler: `taskschd.msc`
2. Create Basic Task:
   - **Name:** PiscesER1 Support Bot
   - **Trigger:** Every 5 minutes
   - **Action:** Start a program
   - **Program:** `python`
   - **Arguments:** `C:\path\to\Pisces\main.py --mode once`
   - **Start in:** `C:\path\to\Pisces`

### Option 2: Windows Service (24/7 Operation)

Use NSSM (Non-Sucking Service Manager):

1. Download NSSM from https://nssm.cc/download
2. Install as service:
   ```cmd
   nssm install PiscesSupportBot
   ```
3. Configure:
   - **Path:** `C:\Python39\python.exe`
   - **Arguments:** `C:\path\to\Pisces\main.py --mode continuous`
   - **Working Directory:** `C:\path\to\Pisces`

### Option 3: Docker

```powershell
# Build image
docker build -t pisces-support-bot .

# Run container
docker run -d --name pisces-bot --env-file .env -v ./data:/app/data pisces-support-bot
```

---

## Configuration Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `SDP_BASE_URL` | ServiceDesk Plus API URL | Required |
| `SDP_API_KEY` | ServiceDesk Plus API key | Required |
| `GEMINI_API_KEY` | Google Gemini API key | Required |
| `CHECK_INTERVAL_MINUTES` | Minutes between checks | 5 |
| `MAX_TICKETS_PER_RUN` | Max tickets per cycle | 10 |
| `LOG_LEVEL` | Logging level | INFO |

---

## Files Structure

```
Pisces/
├── main.py              # Entry point
├── support_bot.py       # Core bot logic
├── ai_processor.py      # Gemini AI integration
├── servicedesk_client.py # ServiceDesk Plus API client
├── escalation_notifier.py # Email escalations
├── database.py          # SQLite database manager
├── models.py            # Data models
├── config.py            # Configuration loader
├── view_responses.py    # View bot responses
├── requirements.txt     # Python dependencies
├── .env                 # Your configuration (create from .env.example)
├── .env.example         # Configuration template
├── Dockerfile           # Docker configuration
└── docker-compose.yml   # Docker Compose configuration
```

---

## Monitoring

### View Bot Status
```powershell
python main.py --status
```

### View Generated Responses
```powershell
python view_responses.py
python view_responses.py --ticket TICKET_ID
python view_responses.py --processed
```

### Log Files
- Location: `pisces_support_bot.log`
- Auto-rotates at 10MB
- Keeps 30 days of logs

### Database
- Location: `pisces_support_bot.db` (SQLite)
- Auto-cleanup of records older than 30 days

---

## Troubleshooting

### Connection Failed
1. Check API keys in `.env` file
2. Verify ServiceDesk Plus server is reachable
3. Ensure internet access for Gemini API

### No Tickets Processing
1. Check if there are open tickets in ServiceDesk Plus
2. View processed tickets: `python view_responses.py --processed`
3. Check log file for errors

### Bot Not Responding
1. Check `pisces_support_bot.log` for errors
2. Run connection test: `python main.py --test-connections`
3. Verify API keys are valid

---

## Security Notes

1. **Never commit `.env` file** - Contains sensitive API keys
2. **Restrict file permissions** on `.env` and database files
3. **Use firewall rules** - Only allow outbound to Gemini API
4. **Keep Python updated** - Apply security patches

---

## Support

For issues or questions, contact your system administrator.

