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
