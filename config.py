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

# ── A1A status names (exact Jira workflow names) ─────────────────────────────
A1A_STATUS_OPEN     = os.getenv("A1A_STATUS_OPEN", "Ready")
A1A_STATUS_ACTIVE   = os.getenv("A1A_STATUS_ACTIVE", "Active")
A1A_STATUS_WAITING  = os.getenv("A1A_STATUS_WAITING", "Waiting/Pending SC")
A1A_STATUS_BLOCKED  = os.getenv("A1A_STATUS_BLOCKED", "Blocked")

# ── OCA status names (exact Jira workflow names) ─────────────────────────────
OCA_STATUS_OPEN     = os.getenv("OCA_STATUS_OPEN", "To Do")
OCA_STATUS_PROGRESS = os.getenv("OCA_STATUS_PROGRESS", "In Progress")
OCA_STATUS_WAITING  = os.getenv("OCA_STATUS_WAITING", "Waiting/Needs Information")
OCA_STATUS_BLOCKED  = os.getenv("OCA_STATUS_BLOCKED", "Blocked/AWGS")

# ── A1A incident-type statuses ────────────────────────────────────────────────
A1A_INC_STATUS_OPEN     = os.getenv("A1A_INC_STATUS_OPEN", "Open")
A1A_INC_STATUS_REOPENED = os.getenv("A1A_INC_STATUS_REOPENED", "Reopened")
A1A_INC_STATUS_PROGRESS = os.getenv("A1A_INC_STATUS_PROGRESS", "In Progress")
A1A_INC_STATUS_WAITING  = os.getenv("A1A_INC_STATUS_WAITING", "Waiting")
A1A_INC_STATUS_BLOCKED  = os.getenv("A1A_INC_STATUS_BLOCKED", "Blocked")
A1A_INC_STATUS_CLOSED   = os.getenv("A1A_INC_STATUS_CLOSED", "Closed")

# ── OCA incident-type statuses ────────────────────────────────────────────────
OCA_INC_STATUS_OPEN     = os.getenv("OCA_INC_STATUS_OPEN", "Open")
OCA_INC_STATUS_PROGRESS = os.getenv("OCA_INC_STATUS_PROGRESS", "In Progress")
OCA_INC_STATUS_NEEDINFO = os.getenv("OCA_INC_STATUS_NEEDINFO", "Needs information")
OCA_INC_STATUS_WAITING  = os.getenv("OCA_INC_STATUS_WAITING", "Waiting")
OCA_INC_STATUS_WAITFB   = os.getenv("OCA_INC_STATUS_WAITFB", "Waiting for feedback")
OCA_INC_STATUS_BLOCKED  = os.getenv("OCA_INC_STATUS_BLOCKED", "Blocked")
OCA_INC_STATUS_CLOSED   = os.getenv("OCA_INC_STATUS_CLOSED", "Closed")

# ── Digest bucket thresholds ──────────────────────────────────────────────────
A1A_ACTIVE_MIN_HOURS      = float(os.getenv("A1A_ACTIVE_MIN_HOURS", "24"))
A1A_ACTIVE_MAX_HOURS      = float(os.getenv("A1A_ACTIVE_MAX_HOURS", "48"))
A1A_WAITING_DAYS          = float(os.getenv("A1A_WAITING_DAYS", "7"))

OCA_OPEN_FRESH_MAX_HOURS  = float(os.getenv("OCA_OPEN_FRESH_MAX_HOURS", "24"))
OCA_OPEN_AGING_MIN_HOURS  = float(os.getenv("OCA_OPEN_AGING_MIN_HOURS", "24"))
OCA_OPEN_AGING_MAX_HOURS  = float(os.getenv("OCA_OPEN_AGING_MAX_HOURS", "48"))
OCA_PROGRESS_MIN_HOURS    = float(os.getenv("OCA_PROGRESS_MIN_HOURS", "24"))
OCA_WAITING_MIN_HOURS     = float(os.getenv("OCA_WAITING_MIN_HOURS", "48"))

# ── Schedules ──────────────────────────────────────────────────────────────────
FAST_PATH_INTERVAL_SECONDS = int(os.getenv("FAST_PATH_INTERVAL_SECONDS", "300"))    # 5 min
DIGEST_INTERVAL_SECONDS    = int(os.getenv("DIGEST_INTERVAL_SECONDS", "7200"))      # 2 hr