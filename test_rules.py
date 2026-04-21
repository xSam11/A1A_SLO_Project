"""
tests/test_rules.py — Unit tests for the rules engine.
Run with: pytest tests/
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

# Patch env before importing config/rules
os.environ.setdefault("JIRA_BASE_URL",    "https://test.atlassian.net")
os.environ.setdefault("JIRA_EMAIL",       "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN",   "fake-token")
os.environ.setdefault("SLACK_WEBHOOK_URL","https://hooks.slack.com/fake")

import config
from src.rules import (
    rule1_a1a_idle,
    rule2_oca_idle,
    rule3_oca_not_closed,
    rule4_out_of_order,
    evaluate_all,
)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _ticket(
    key: str = "A1A-1",
    status: str = "Open",
    idle_minutes: float = 0,
    age_hours: float = 0,
) -> dict:
    now = _now()
    return {
        "id":          "100",
        "key":         key,
        "ticket_num":  int(key.split("-")[1]),
        "summary":     f"Test ticket {key}",
        "status":      status,
        "assignee":    "Alice",
        "priority":    "Medium",
        "created_at":  now - timedelta(hours=age_hours),
        "updated_at":  now - timedelta(minutes=idle_minutes),
        "url":         f"https://test.atlassian.net/browse/{key}",
        "project":     key.split("-")[0],
    }


# ── Rule 1 ────────────────────────────────────────────────────────────────────

class TestRule1:
    def test_fires_when_idle_past_threshold(self):
        t = _ticket("A1A-1", status="Open", idle_minutes=config.A1A_IDLE_MINUTES + 1)
        assert rule1_a1a_idle(t) is not None

    def test_no_fire_when_within_threshold(self):
        t = _ticket("A1A-1", status="Open", idle_minutes=config.A1A_IDLE_MINUTES - 1)
        assert rule1_a1a_idle(t) is None

    def test_no_fire_when_not_open(self):
        t = _ticket("A1A-1", status="In Progress", idle_minutes=999)
        assert rule1_a1a_idle(t) is None

    def test_alert_contains_ticket_key(self):
        t = _ticket("A1A-42", status="Open", idle_minutes=config.A1A_IDLE_MINUTES + 5)
        alert = rule1_a1a_idle(t)
        assert alert is not None
        assert "A1A-42" in alert.ticket_key
        assert alert.rule_id == "rule1_a1a_idle"


# ── Rule 2 ────────────────────────────────────────────────────────────────────

class TestRule2:
    def test_fires_when_idle_past_threshold(self):
        idle_min = config.OCA_IDLE_HOURS * 60 + 10
        t = _ticket("OCA-1", status="Open", idle_minutes=idle_min)
        assert rule2_oca_idle(t) is not None

    def test_no_fire_within_threshold(self):
        idle_min = config.OCA_IDLE_HOURS * 60 - 30
        t = _ticket("OCA-1", status="Open", idle_minutes=idle_min)
        assert rule2_oca_idle(t) is None


# ── Rule 3 ────────────────────────────────────────────────────────────────────

class TestRule3:
    def test_fires_when_old_and_not_closed(self):
        t = _ticket("OCA-1", status="Open", age_hours=config.OCA_MAX_AGE_HOURS + 1)
        assert rule3_oca_not_closed(t) is not None

    def test_no_fire_when_young(self):
        t = _ticket("OCA-1", status="Open", age_hours=config.OCA_MAX_AGE_HOURS - 1)
        assert rule3_oca_not_closed(t) is None

    def test_fires_even_when_in_progress(self):
        """Ticket is old and still not closed, regardless of current status."""
        t = _ticket("OCA-1", status="In Progress", age_hours=config.OCA_MAX_AGE_HOURS + 2)
        assert rule3_oca_not_closed(t) is not None


# ── Rule 4 ────────────────────────────────────────────────────────────────────

class TestRule4:
    def test_fires_when_lower_number_skipped(self):
        in_progress = [_ticket("A1A-5", status="In Progress")]
        open_tickets = [_ticket("A1A-2", status="Open")]
        alerts = rule4_out_of_order(in_progress, open_tickets)
        assert len(alerts) == 1
        assert "A1A-5" in alerts[0].ticket_key
        assert "A1A-2" in alerts[0].fields["Skipped"]

    def test_no_fire_when_in_order(self):
        in_progress = [_ticket("A1A-1", status="In Progress")]
        open_tickets = [_ticket("A1A-5", status="Open")]
        alerts = rule4_out_of_order(in_progress, open_tickets)
        assert alerts == []

    def test_multiple_skipped_tickets(self):
        in_progress = [_ticket("A1A-10", status="In Progress")]
        open_tickets = [
            _ticket("A1A-2", status="Open"),
            _ticket("A1A-3", status="Open"),
        ]
        alerts = rule4_out_of_order(in_progress, open_tickets)
        assert len(alerts) == 2

    def test_no_fire_when_no_open_tickets(self):
        in_progress = [_ticket("A1A-5", status="In Progress")]
        alerts = rule4_out_of_order(in_progress, [])
        assert alerts == []


# ── evaluate_all ──────────────────────────────────────────────────────────────

class TestEvaluateAll:
    def test_returns_flat_list(self):
        a1a_open = [_ticket("A1A-1", status="Open", idle_minutes=config.A1A_IDLE_MINUTES + 5)]
        oca_open = []
        a1a_ip   = []
        alerts = evaluate_all(a1a_open, oca_open, a1a_ip)
        assert len(alerts) >= 1
        assert all(hasattr(a, "rule_id") for a in alerts)

    def test_no_alerts_for_healthy_tickets(self):
        a1a_open = [_ticket("A1A-1", status="Open", idle_minutes=1)]
        oca_open = [_ticket("OCA-1", status="Open", idle_minutes=1, age_hours=1)]
        a1a_ip   = []
        alerts = evaluate_all(a1a_open, oca_open, a1a_ip)
        assert alerts == []
