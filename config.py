"""
config.py — All thresholds and credentials loaded from environment variables.
Adjust thresholds here (or via .env) as you experiment with alert volume.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Jira ──────────────────────────────────────────────────────────────────────
JIRA_BASE_URL   = os.environ["JIRA_BASE_URL"]        # e.g. https://yourcompany.atlassian.net
JIRA_EMAIL      = os.environ["JIRA_EMAIL"]           # your atlassian account email
JIRA_API_TOKEN  = os.environ["JIRA_API_TOKEN"]       # https://id.atlassian.com/manage-profile/security/api-tokens
JIRA_A1A_PROJECT = os.getenv("JIRA_A1A_PROJECT", "A1A")   # project key for A1A board
JIRA_OCA_PROJECT = os.getenv("JIRA_OCA_PROJECT", "OCA")   # project key for OCA board

# ── Slack ─────────────────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]  # Incoming webhook URL for #alerts-ticket-slo
# Optional: bot token if you want to use Slack API instead of webhooks
SLACK_BOT_TOKEN   = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL     = os.getenv("SLACK_CHANNEL", "#alerts-ticket-slo")

# ── Alert thresholds (easy to tune) ───────────────────────────────────────────
# Rule 1: A1A ticket sitting in Open with no update
A1A_IDLE_MINUTES         = int(os.getenv("A1A_IDLE_MINUTES", "15"))

# Rule 2: OCA ticket sitting in Open with no update
OCA_IDLE_HOURS           = float(os.getenv("OCA_IDLE_HOURS", "7"))

# Rule 3: OCA ticket not closed N hours after creation
OCA_MAX_AGE_HOURS        = float(os.getenv("OCA_MAX_AGE_HOURS", "24"))

# How long to wait before re-alerting on the same ticket+rule (avoids spam)
ALERT_COOLDOWN_HOURS     = float(os.getenv("ALERT_COOLDOWN_HOURS", "1"))

# Rule 3 is a one-shot alert (don't re-fire every cooldown window)
RULE3_ALERT_ONCE         = os.getenv("RULE3_ALERT_ONCE", "true").lower() == "true"

# ── Dedup store ───────────────────────────────────────────────────────────────
# Path to the JSON file used as a lightweight dedup/state store.
# Swap for Redis URL in production (see dedup.py).
DEDUP_STORE_PATH = os.getenv("DEDUP_STORE_PATH", ".alert_state.json")
REDIS_URL        = os.getenv("REDIS_URL", "")          # optional — leave blank to use JSON file

# ── Poller ────────────────────────────────────────────────────────────────────
# Only used when running the script directly in loop mode (not via cron/Lambda).
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))  # 5 minutes
