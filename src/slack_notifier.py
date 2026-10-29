"""
slack_notifier.py — Sends formatted alerts to Slack via Incoming Webhooks.

Uses Slack Block Kit for rich messages. Each alert gets:
  • Emoji + one-line title
  • Ticket summary as context
  • Key fields (idle time, assignee, etc.) as a mini table
  • Direct link button to the Jira ticket
"""

from __future__ import annotations

import logging
from typing import Any

import requests

import config
from src.rules import Alert

log = logging.getLogger(__name__)

_RULE_LABELS = {
    "rule1_a1a_idle":       "A1A — Idle in Open",
    "rule2_oca_idle":       "OCA — Idle alert",
    "rule3_oca_not_closed": "OCA — Past SLO age",
    "rule4_order":          "Out-of-order pickup",
}


def _rule_label(rule_id: str) -> str:
    for prefix, label in _RULE_LABELS.items():
        if rule_id.startswith(prefix):
            return label
    return rule_id


def _build_blocks(alert: Alert) -> list[dict[str, Any]]:
    """Build Slack Block Kit payload for a single alert."""
    blocks: list[dict] = []

    # Header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"{alert.emoji}  Ticket SLO Alert — {_rule_label(alert.rule_id)}",
            "emoji": True,
        },
    })

    # Title (mrkdwn)
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": alert.title,
        },
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": "Open in Jira", "emoji": False},
            "url": alert.url,
            "action_id": "open_jira",
        },
    })

    # Ticket summary (context line)
    if alert.detail:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"_{alert.detail}_"}],
        })

    # Key fields as two-column section
    if alert.fields:
        field_blocks = [
            {"type": "mrkdwn", "text": f"*{k}*\n{v}"}
            for k, v in alert.fields.items()
        ]
        # Slack limits section fields to 10; chunk if needed
        for i in range(0, len(field_blocks), 10):
            blocks.append({
                "type": "section",
                "fields": field_blocks[i:i+10],
            })

    blocks.append({"type": "divider"})
    return blocks


def send_alert(alert: Alert) -> bool:
    """
    Post a single alert to the Slack webhook.
    Returns True on success, False on failure (logs the error).
    """
    payload = {
        "username":   "Ticket SLO Bot",
        "icon_emoji": ":ticket:",
        "channel":    config.SLACK_CHANNEL,
        "blocks":     _build_blocks(alert),
        # Fallback text for notifications / accessibility
        "text": f"{alert.emoji} {alert.title}",
    }

    try:
        resp = requests.post(config.SLACK_WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code == 200 and resp.text == "ok":
            log.info("Slack alert sent: %s", alert.dedup_key)
            return True
        else:
            log.error(
                "Slack webhook returned %s: %s", resp.status_code, resp.text
            )
            return False
    except requests.RequestException as e:
        log.error("Failed to send Slack alert for %s: %s", alert.dedup_key, e)
        return False


def send_batch(alerts: list[Alert]) -> int:
    """Send multiple alerts. Returns the count that succeeded."""
    return sum(send_alert(a) for a in alerts)
from datetime import datetime, timezone


def _format_ticket_line(t: dict) -> str:
    opened = t["created_at"].strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"• <{t['url']}|*{t['key']}*> — {t['summary']}\n"
        f"   Opened: {opened} | Assignee: {t['assignee']} | Status: {t['status']}"
    )


def _bucket_block(title: str, tickets: list[dict], tag: str = "") -> list[dict]:
    heading = f"*{title}*"
    if tag:
        heading += f"  `{tag}`"
    heading += f" — {len(tickets)} ticket(s)"

    blocks: list[dict] = [{
        "type": "section",
        "text": {"type": "mrkdwn", "text": heading},
    }]
    if not tickets:
        return blocks
    lines = [_format_ticket_line(t) for t in tickets]
    for i in range(0, len(lines), 10):
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n\n".join(lines[i:i + 10])},
        })
    return blocks


def _build_digest_blocks(digest: dict) -> list[dict]:
    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": "📊 Ticket SLO Digest", "emoji": True}},
        {"type": "context", "elements": [{
            "type": "mrkdwn",
            "text": f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        }]},
        {"type": "divider"},
    ]

    if "a1a" in digest:
        blocks.append({"type": "header", "text": {"type": "plain_text", "text": "🅰️ A1A / CDP SLO Warning", "emoji": True}})
        a1a = digest["a1a"]
        blocks.extend(_bucket_block(f"Open > {config.A1A_IDLE_MINUTES:.0f} min", a1a["open"]))
        blocks.extend(_bucket_block(
            f"In Progress {config.A1A_ACTIVE_MIN_HOURS:.0f}–{config.A1A_ACTIVE_MAX_HOURS:.0f} hrs", a1a["active"]
        ))
        blocks.extend(_bucket_block(f"Waiting/Blocked > {config.A1A_WAITING_DAYS:.0f} days", a1a["waiting"]))
        blocks.append({"type": "divider"})

    if "oca" in digest:
        blocks.append({"type": "header", "text": {"type": "plain_text", "text": "🅾️ OCA SLO Warning", "emoji": True}})
        oca = digest["oca"]
        blocks.extend(_bucket_block(
            f"Open {config.OCA_OPEN_AGING_MIN_HOURS:.0f}–{config.OCA_OPEN_AGING_MAX_HOURS:.0f} hrs",
            oca["open_aging"], tag="URGENT",
        ))
        blocks.extend(_bucket_block(
            f"Open < {config.OCA_OPEN_FRESH_MAX_HOURS:.0f} hrs",
            oca["open_fresh"], tag="NORMAL",
        ))
        blocks.extend(_bucket_block(f"In Progress ≥ {config.OCA_PROGRESS_MIN_HOURS:.0f} hrs", oca["in_progress"]))
        blocks.extend(_bucket_block(f"Blocked/Waiting > {config.OCA_WAITING_MIN_HOURS:.0f} hrs", oca["blocked"]))
        blocks.append({"type": "divider"})

    return blocks


def send_digest(digest: dict) -> bool:
    """Post the full two-board digest to Slack. Splits into multiple messages if needed (50-block limit)."""
    all_blocks = _build_digest_blocks(digest)
    ok = True
    for i in range(0, len(all_blocks), 45):
        payload = {
            "username": "Ticket SLO Bot",
            "icon_emoji": ":bar_chart:",
            "channel": config.SLACK_CHANNEL,
            "blocks": all_blocks[i:i + 45],
            "text": "Ticket SLO Digest",
        }
        try:
            resp = requests.post(config.SLACK_WEBHOOK_URL, json=payload, timeout=10)
            if not (resp.status_code == 200 and resp.text == "ok"):
                log.error("Slack digest webhook returned %s: %s", resp.status_code, resp.text)
                ok = False
        except requests.RequestException as e:
            log.error("Failed to send Slack digest: %s", e)
            ok = False
    return ok