# Jira SLO Alert Bot

Polls your Jira boards and sends Slack alerts when tickets breach SLO thresholds.

## Alert rules

| # | Board | Condition | Default threshold |
|---|-------|-----------|-------------------|
| 1 | A1A | Ticket idle in **Open** with no update | 15 minutes |
| 2 | OCA | Ticket idle in any non-closed state | 7 hours |
| 3 | OCA | Ticket not closed since creation | 24 hours (one-shot) |
| 4 | A1A | Lower-numbered ticket skipped during pickup | On every occurrence |

All thresholds are env vars — change them without touching code.

---

## Project layout

```
jira-slo-alerts/
├── config.py               — all settings loaded from env
├── poller.py               — main entry point / Lambda handler
├── src/
│   ├── jira_client.py      — Jira REST API wrapper
│   ├── rules.py            — pure rule logic (easy to unit test)
│   ├── dedup.py            — alert dedup store (JSON or Redis)
│   └── slack_notifier.py   — Slack Block Kit message sender
├── tests/
│   └── test_rules.py       — pytest suite for all 4 rules
├── requirements.txt
└── .env.example
```

---

## Setup

### 1. Clone and install

```bash
git clone <your-repo>
cd jira-slo-alerts
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env with your Jira URL, API token, and Slack webhook URL
```

**Get a Jira API token:** https://id.atlassian.com/manage-profile/security/api-tokens

**Get a Slack webhook URL:**
- Go to https://api.slack.com/apps → Create App → Incoming Webhooks
- Activate and add to your `#alerts-ticket-slo` channel

### 3. Run

**Single poll (for cron):**
```bash
python poller.py
```

**Continuous loop:**
```bash
python poller.py --loop
```

**Run tests:**
```bash
pytest tests/ -v
```

---

## Deployment options

### Option A — cron (simplest)

```cron
*/5 * * * * cd /path/to/jira-slo-alerts && python poller.py >> /var/log/slo-alerts.log 2>&1
```

### Option B — AWS Lambda (recommended for production)

1. Zip the project: `zip -r function.zip . -x "*.git*" "tests/*"`
2. Upload to Lambda, set handler to `poller.lambda_handler`
3. Set all env vars in Lambda Configuration → Environment Variables
4. Set REDIS_URL to an ElastiCache Redis instance for persistent dedup state
5. Add an EventBridge (CloudWatch Events) rule: `rate(5 minutes)`

### Option C — GitHub Actions

```yaml
# .github/workflows/slo-alerts.yml
name: SLO Alert Poller
on:
  schedule:
    - cron: '*/5 * * * *'
jobs:
  poll:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt
      - run: python poller.py
        env:
          JIRA_BASE_URL:    ${{ secrets.JIRA_BASE_URL }}
          JIRA_EMAIL:       ${{ secrets.JIRA_EMAIL }}
          JIRA_API_TOKEN:   ${{ secrets.JIRA_API_TOKEN }}
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

> **Note:** GitHub Actions cron has ~1min jitter and doesn't persist files between runs.
> Use the Redis dedup store or commit `.alert_state.json` to a branch to persist state.

---

## Tuning thresholds

Edit `.env` (or Lambda env vars) — no code changes needed:

```bash
A1A_IDLE_MINUTES=20      # increase if Rule 1 is too noisy
OCA_IDLE_HOURS=4         # decrease if OCA tickets are slipping through
OCA_MAX_AGE_HOURS=36     # increase if 24hr is unrealistic for your team
ALERT_COOLDOWN_HOURS=2   # increase to reduce repeat pings
RULE3_ALERT_ONCE=true    # set false to re-alert on Rule 3 every cooldown window
```

---

## What a Slack alert looks like

```
🔔  Ticket SLO Alert — A1A — Idle in Open
─────────────────────────────────────────────
A1A-42 has been idle in Open for 23 min (SLO: 15 min)
_User cannot log in after password reset_

Assignee    Idle     Priority
Alice       23 min   High

[Open in Jira]
```

---

## Upgrading to Redis

Install: `pip install redis`

Set in `.env`:
```
REDIS_URL=redis://localhost:6379/0
```

The code switches automatically — no other changes needed.
Keys are namespaced as `jira_slo_alert:{ticket_key}:{rule_id}` and expire after the cooldown window.
