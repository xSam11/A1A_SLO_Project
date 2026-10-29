"""
rules.py — The 4 SLO alert rules.

Each rule function receives ticket data and returns an Alert if the rule fires,
or None if the ticket is within SLO. The rules engine is pure logic — no Slack
or Jira calls happen here. That makes it easy to unit test.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import config

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _idle_minutes(ticket: dict) -> float:
    """Minutes since the ticket was last updated."""
    return (_now() - ticket["updated_at"]).total_seconds() / 60


def _age_hours(ticket: dict) -> float:
    """Hours since the ticket was created."""
    return (_now() - ticket["created_at"]).total_seconds() / 3600


@dataclass
class Alert:
    rule_id:    str          # e.g. "rule1_a1a_idle"
    ticket_key: str          # e.g. "A1A-42"
    title:      str          # short one-liner for Slack
    detail:     str          # longer context string
    url:        str          # direct Jira link
    emoji:      str = "🔔"
    fields:     dict = field(default_factory=dict)  # extra Slack block fields

    @property
    def dedup_key(self) -> str:
        return f"{self.ticket_key}:{self.rule_id}"


# ── Rule 1 ────────────────────────────────────────────────────────────────────

def rule1_a1a_idle(ticket: dict) -> Optional[Alert]:
    """
    Rule 1 — A1A ticket has been sitting in Open with no update for > 15 min.
    Threshold: A1A_IDLE_MINUTES (default 15)
    """
    if ticket["status"].lower() != "open":
        return None

    idle = _idle_minutes(ticket)
    threshold = config.A1A_IDLE_MINUTES

    if idle < threshold:
        return None

    return Alert(
        rule_id="rule1_a1a_idle",
        ticket_key=ticket["key"],
        emoji="⏱️",
        title=f"*{ticket['key']}* has been idle in *Open* for {idle:.0f} min (SLO: {threshold} min)",
        detail=ticket["summary"],
        url=ticket["url"],
        fields={
            "Assignee": ticket["assignee"],
            "Idle":     f"{idle:.0f} min",
            "Priority": ticket["priority"],
        },
    )


# ── Rule 2 ────────────────────────────────────────────────────────────────────

def rule2_oca_idle(ticket: dict) -> Optional[Alert]:
    """
    Rule 2 — OCA ticket has been in Open (or any non-closed state) with no
    update for > 7 hrs.
    Threshold: OCA_IDLE_HOURS (default 7)
    """
    idle_hours = _idle_minutes(ticket) / 60
    threshold  = config.OCA_IDLE_HOURS

    if idle_hours < threshold:
        return None

    return Alert(
        rule_id="rule2_oca_idle",
        ticket_key=ticket["key"],
        emoji="🐢",
        title=f"*{ticket['key']}* has been idle for {idle_hours:.1f} hr (SLO: {threshold} hr)",
        detail=ticket["summary"],
        url=ticket["url"],
        fields={
            "Status":   ticket["status"],
            "Assignee": ticket["assignee"],
            "Idle":     f"{idle_hours:.1f} hr",
            "Priority": ticket["priority"],
        },
    )


# ── Rule 3 ────────────────────────────────────────────────────────────────────

def rule3_oca_not_closed(ticket: dict) -> Optional[Alert]:
    """
    Rule 3 — OCA ticket is still open 24 hrs after creation.
    Threshold: OCA_MAX_AGE_HOURS (default 24)
    This is a one-shot alert by default (RULE3_ALERT_ONCE=true).
    """
    age_hours = _age_hours(ticket)
    threshold = config.OCA_MAX_AGE_HOURS

    if age_hours < threshold:
        return None

    return Alert(
        rule_id="rule3_oca_not_closed",
        ticket_key=ticket["key"],
        emoji="🚨",
        title=f"*{ticket['key']}* is {age_hours:.1f} hr old and still *{ticket['status']}* (SLO: closed within {threshold:.0f} hr)",
        detail=ticket["summary"],
        url=ticket["url"],
        fields={
            "Status":   ticket["status"],
            "Assignee": ticket["assignee"],
            "Age":      f"{age_hours:.1f} hr",
            "Created":  ticket["created_at"].strftime("%Y-%m-%d %H:%M UTC"),
        },
    )


# ── Rule 4 ────────────────────────────────────────────────────────────────────

def rule4_out_of_order(
    in_progress_tickets: list[dict],
    open_tickets: list[dict],
) -> list[Alert]:
    """
    Rule 4 — A ticket was picked up (moved to In Progress) while a lower-numbered
    ticket is still sitting in Open.

    Logic:
      For each In-Progress ticket, check if any Open ticket has a lower ticket_num.
      Alert once per (in_progress_key, skipped_key) pair.

    Returns a list because one In-Progress ticket can skip multiple Open ones.
    """
    alerts: list[Alert] = []

    if not in_progress_tickets or not open_tickets:
        return alerts

    min_open_num = min(t["ticket_num"] for t in open_tickets)

    for ip_ticket in in_progress_tickets:
        # Find all open tickets with a lower number than this in-progress one
        skipped = [
            t for t in open_tickets
            if t["ticket_num"] < ip_ticket["ticket_num"]
        ]
        for skipped_ticket in skipped:
            alerts.append(Alert(
                rule_id=f"rule4_order_{skipped_ticket['key']}",
                ticket_key=ip_ticket["key"],
                emoji="⚠️",
                title=(
                    f"*{ip_ticket['key']}* was picked up while "
                    f"*{skipped_ticket['key']}* (lower number) is still in Open"
                ),
                detail=ip_ticket["summary"],
                url=ip_ticket["url"],
                fields={
                    "Picked up":  ip_ticket["key"],
                    "Skipped":    skipped_ticket["key"],
                    "Assignee":   ip_ticket["assignee"],
                    "Skipped summary": skipped_ticket["summary"],
                },
            ))

    return alerts


# ── Orchestrator ──────────────────────────────────────────────────────────────

def evaluate_all(
    a1a_open:          list[dict],
    oca_open:          list[dict],
    a1a_in_progress:   list[dict],
) -> list[Alert]:
    """
    Run all rules across the current ticket snapshot.
    Returns a flat list of Alert objects that should be sent (before dedup filtering).
    """
    alerts: list[Alert] = []

    # Rule 1 — A1A idle
    for ticket in a1a_open:
        alert = rule1_a1a_idle(ticket)
        if alert:
            log.info("Rule 1 fired: %s", ticket["key"])
            alerts.append(alert)

    # Rules 2 + 3 — OCA
    for ticket in oca_open:
        alert2 = rule2_oca_idle(ticket)
        if alert2:
            log.info("Rule 2 fired: %s", ticket["key"])
            alerts.append(alert2)

        alert3 = rule3_oca_not_closed(ticket)
        if alert3:
            log.info("Rule 3 fired: %s", ticket["key"])
            alerts.append(alert3)

    # Rule 4 — out of order (check both boards)
    order_alerts = rule4_out_of_order(a1a_in_progress, a1a_open)
    if order_alerts:
        log.info("Rule 4 fired %d out-of-order alert(s)", len(order_alerts))
    alerts.extend(order_alerts)

    return alerts

# ── Digest bucket builders ─────────────────────────────────────────────────────

def build_a1a_digest(a1a_tickets: list[dict]) -> dict[str, list[dict]]:
    """Bucket all non-closed A1A tickets (both workflows) into the 3 digest sections."""
    open_statuses    = (config.A1A_STATUS_OPEN, config.A1A_INC_STATUS_OPEN, config.A1A_INC_STATUS_REOPENED)
    active_statuses  = (config.A1A_STATUS_ACTIVE, config.A1A_INC_STATUS_PROGRESS)
    waiting_statuses = (
        config.A1A_STATUS_WAITING, config.A1A_STATUS_BLOCKED,
        config.A1A_INC_STATUS_WAITING, config.A1A_INC_STATUS_BLOCKED,
    )

    open_bucket = [
        t for t in a1a_tickets
        if t["status"] in open_statuses and _idle_minutes(t) > config.A1A_IDLE_MINUTES
    ]
    active_bucket = [
        t for t in a1a_tickets
        if t["status"] in active_statuses
        and config.A1A_ACTIVE_MIN_HOURS <= _idle_minutes(t) / 60 <= config.A1A_ACTIVE_MAX_HOURS
    ]
    waiting_bucket = [
        t for t in a1a_tickets
        if t["status"] in waiting_statuses
        and _idle_minutes(t) / 60 > config.A1A_WAITING_DAYS * 24
    ]
    return {"open": open_bucket, "active": active_bucket, "waiting": waiting_bucket}


def build_oca_digest(oca_tickets: list[dict]) -> dict[str, list[dict]]:
    """Bucket all non-closed OCA tickets (both workflows) into the 4 digest sections."""
    open_statuses     = (config.OCA_STATUS_OPEN, config.OCA_INC_STATUS_OPEN)
    progress_statuses = (config.OCA_STATUS_PROGRESS, config.OCA_INC_STATUS_PROGRESS)
    blocked_statuses  = (
        config.OCA_STATUS_WAITING, config.OCA_STATUS_BLOCKED,
        config.OCA_INC_STATUS_NEEDINFO, config.OCA_INC_STATUS_WAITING,
        config.OCA_INC_STATUS_WAITFB, config.OCA_INC_STATUS_BLOCKED,
    )

    open_fresh = [
        t for t in oca_tickets
        if t["status"] in open_statuses and _age_hours(t) < config.OCA_OPEN_FRESH_MAX_HOURS
    ]
    open_aging = [
        t for t in oca_tickets
        if t["status"] in open_statuses
        and config.OCA_OPEN_AGING_MIN_HOURS <= _age_hours(t) <= config.OCA_OPEN_AGING_MAX_HOURS
    ]
    in_progress = [
        t for t in oca_tickets
        if t["status"] in progress_statuses and _idle_minutes(t) / 60 >= config.OCA_PROGRESS_MIN_HOURS
    ]
    blocked = [
        t for t in oca_tickets
        if t["status"] in blocked_statuses and _idle_minutes(t) / 60 > config.OCA_WAITING_MIN_HOURS
    ]
    return {"open_fresh": open_fresh, "open_aging": open_aging, "in_progress": in_progress, "blocked": blocked}

def build_digest(a1a_tickets: list[dict], oca_tickets: list[dict]) -> dict:
    """Build the full two-board digest structure for Slack."""
    return {
        "a1a": build_a1a_digest(a1a_tickets),
        "oca": build_oca_digest(oca_tickets),
    }