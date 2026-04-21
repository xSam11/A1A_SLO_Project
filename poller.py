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
from src.rules import evaluate_all, Alert
from src.slack_notifier import send_alert

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


def poll_once(jira: JiraClient, store: DedupStore) -> int:
    """
    Execute one full poll cycle.
    Returns the number of alerts actually sent to Slack.
    """
    log.info("── Poll cycle starting ──────────────────────────────────")

    # 1. Fetch
    log.info("Fetching tickets from Jira...")
    a1a_open        = jira.get_open_a1a_tickets()
    oca_open        = jira.get_open_oca_tickets()
    a1a_in_progress = jira.get_in_progress_tickets(config.JIRA_A1A_PROJECT)

    log.info(
        "Fetched: %d A1A open, %d OCA open/unclosed, %d A1A in-progress",
        len(a1a_open), len(oca_open), len(a1a_in_progress),
    )

    # 2. Evaluate rules
    candidate_alerts = evaluate_all(a1a_open, oca_open, a1a_in_progress)
    log.info("%d rule(s) fired before dedup", len(candidate_alerts))

    # 3. Dedup filter
    alerts_to_send = _filter_with_dedup(candidate_alerts, store)
    log.info("%d alert(s) will be sent after dedup", len(alerts_to_send))

    # 4. Send + mark
    sent = 0
    for alert in alerts_to_send:
        if send_alert(alert):
            store.mark_alerted(alert.dedup_key)
            sent += 1

    log.info("── Poll cycle done. Sent %d alert(s). ──────────────────", sent)
    return sent


def run_loop(jira: JiraClient, store: DedupStore) -> None:
    """Continuous polling loop (for running as a long-lived process)."""
    log.info(
        "Starting continuous loop with %ds interval. Ctrl-C to stop.",
        config.POLL_INTERVAL_SECONDS,
    )
    while True:
        try:
            poll_once(jira, store)
        except Exception:
            log.exception("Unexpected error during poll — will retry next cycle")
        time.sleep(config.POLL_INTERVAL_SECONDS)


# ── Lambda entry point ────────────────────────────────────────────────────────

def lambda_handler(event: dict, context: object) -> dict:
    """AWS Lambda handler. Set REDIS_URL for state persistence between invocations."""
    jira  = JiraClient()
    store = make_store()
    sent  = poll_once(jira, store)
    return {"statusCode": 200, "sent": sent}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Jira SLO alert poller")
    parser.add_argument(
        "--loop", action="store_true",
        help="Run continuously instead of a single poll"
    )
    args = parser.parse_args()

    jira  = JiraClient()
    store = make_store()

    if args.loop:
        run_loop(jira, store)
    else:
        poll_once(jira, store)


if __name__ == "__main__":
    main()
