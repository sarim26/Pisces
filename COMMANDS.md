# PiscesER1 Marine Support Bot - Command Reference

## Running the Bot

| Command | Description |
|---------|-------------|
| `python main.py --mode once` | Process all open tickets once and exit |
| `python main.py --mode continuous` | Run continuously (default: every 5 minutes) |
| `python main.py --mode continuous --interval 10` | Run continuously every 10 minutes |
| `python main.py --test-connections` | Test ServiceDesk Plus and Gemini API connections |
| `python main.py --status` | Show bot statistics and recent activity |
| `python main.py --version` | Show version number |
| `python main.py --help` | Show all available options |

---

## Viewing Responses

| Command | Description |
|---------|-------------|
| `python view_responses.py` | List all responses (summary view) |
| `python view_responses.py --ticket 123456` | View full response for a specific ticket |
| `python view_responses.py --processed` | View all processed tickets with status |

---

## Examples

### Start the bot for production (continuous mode)
```powershell
cd C:\path\to\Pisces
python main.py --mode continuous --interval 5
```

### Process tickets once (for testing or scheduled runs)
```powershell
python main.py --mode once
```

### Check if everything is configured correctly
```powershell
python main.py --test-connections
```

### View bot performance stats
```powershell
python main.py --status
```

### See what responses the bot has generated
```powershell
python view_responses.py
```

### View the full response for ticket #393966
```powershell
python view_responses.py --ticket 393966
```

---

## Stopping the Bot

When running in continuous mode:
- Press `Ctrl+C` to stop gracefully

---

## Quick Reference

```
┌─────────────────────────────────────────────────────────────┐
│ QUICK START                                                 │
├─────────────────────────────────────────────────────────────┤
│ 1. Test connections:  python main.py --test-connections     │
│ 2. Run once:          python main.py --mode once            │
│ 3. Run continuous:    python main.py --mode continuous      │
│ 4. View responses:    python view_responses.py              │
│ 5. Check status:      python main.py --status               │
└─────────────────────────────────────────────────────────────┘
```

