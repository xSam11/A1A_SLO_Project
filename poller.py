"""
poller.py — Main orchestrator.

Run modes:
  1. python poller.py           → single poll run (ideal for cron / Lambda)
  2. python poller.py --loop   → continuous loop with POLL_INTERVAL_SECONDS sleep
  3. AWS Lambda: set handler = poller.lambda_handler

Flow:
  Jira fetch → rules engine → dedup filter → Slack notify → update dedup store
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import config
from src.dedup import make_store, DedupStore
from src.jira_client import JiraClient
from src.rules import evaluate_all, build_a1a_digest, build_oca_digest, rule1_a1a_idle, Alert
from src.slack_notifier import send_alert, send_digest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("poller")


def _cooldown_for(alert: Alert) -> float:
    """
    Return the appropriate cooldown (in hours) for a given alert rule.
    Rule 3 uses a very long cooldown if RULE3_ALERT_ONCE is True (effectively fires once).
    """
    if alert.rule_id == "rule3_oca_not_closed" and config.RULE3_ALERT_ONCE:
        return 9999.0      # one-shot: never re-alert
    if alert.rule_id.startswith("rule4_order"):
        return config.ALERT_COOLDOWN_HOURS
    return config.ALERT_COOLDOWN_HOURS


def _filter_with_dedup(alerts: list[Alert], store: DedupStore) -> list[Alert]:
    """Remove alerts that were already sent within their cooldown window."""
    to_send: list[Alert] = []
    for alert in alerts:
        cooldown = _cooldown_for(alert)
        if store.was_recently_alerted(alert.dedup_key, cooldown):
            log.debug("Suppressed (dedup): %s", alert.dedup_key)
        else:
            to_send.append(alert)
    return to_send


def poll_fast(jira: JiraClient, store: DedupStore) -> int:
    """A1A fast-path: Ready tickets idle > A1A_IDLE_MINUTES (30 min). Fires individual alerts."""
    log.info("── Fast-path poll (A1A '%s' > %.0f min) ──", config.A1A_STATUS_OPEN, config.A1A_IDLE_MINUTES)
    a1a_open = jira.get_open_a1a_tickets()
    log.info("Fetched %d A1A '%s' ticket(s)", len(a1a_open), config.A1A_STATUS_OPEN)

    candidates = [a for a in (rule1_a1a_idle(t) for t in a1a_open) if a]
    to_send = _filter_with_dedup(candidates, store)

    sent = 0
    for alert in to_send:
        if send_alert(alert):
            store.mark_alerted(alert.dedup_key)
            sent += 1

    log.info("── Fast-path done. Sent %d alert(s). ──", sent)
    return sent


def poll_digest_a1a(jira: JiraClient) -> bool:
    """A1A-only digest."""
    log.info("── A1A digest poll starting ──")
    a1a_tickets = jira.get_project_tickets(
        config.JIRA_A1A_PROJECT, exclude_statuses=["Done", "Closed"], issue_types=["Incident"],
    )
    log.info("Fetched %d A1A active incident(s) for digest", len(a1a_tickets))
    digest = {"a1a": build_a1a_digest(a1a_tickets)}
    ok = send_digest(digest)
    log.info("── A1A digest done. Sent: %s ──", ok)
    return ok


def poll_digest_oca(jira: JiraClient) -> bool:
    """OCA-only digest."""
    log.info("── OCA digest poll starting ──")
    oca_tickets = jira.get_project_tickets(config.JIRA_OCA_PROJECT, exclude_statuses=["Done", "Closed"])
    log.info("Fetched %d OCA active ticket(s) for digest", len(oca_tickets))
    digest = {"oca": build_oca_digest(oca_tickets)}
    ok = send_digest(digest)
    log.info("── OCA digest done. Sent: %s ──", ok)
    return ok

# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Jira SLO alert poller")
    parser.add_argument(
        "--mode", choices=["fast", "digest-a1a", "digest-oca"], required=True,
        help="fast = A1A instant check; digest-a1a/digest-oca = single board digest",
    )
    args = parser.parse_args()
    jira, store = JiraClient(), make_store()

    if args.mode == "fast":
        poll_fast(jira, store)
    elif args.mode == "digest-a1a":
        poll_digest_a1a(jira)
    elif args.mode == "digest-oca":
        poll_digest_oca(jira)


if __name__ == "__main__":
        main()