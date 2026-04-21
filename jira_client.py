"""
jira_client.py — Thin wrapper around the Jira REST API v3.
Fetches open tickets for A1A and OCA projects with all fields needed by the rules engine.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

import config

log = logging.getLogger(__name__)

# Jira datetime format
_JIRA_DT_FMT = "%Y-%m-%dT%H:%M:%S.%f%z"


def _parse_jira_dt(dt_str: str) -> datetime:
    """Parse a Jira timestamp string into a timezone-aware datetime."""
    try:
        return datetime.strptime(dt_str, _JIRA_DT_FMT)
    except ValueError:
        # Jira sometimes emits +0000 instead of +00:00 — handle both
        return datetime.fromisoformat(dt_str)


class JiraClient:
    def __init__(self) -> None:
        self._auth = HTTPBasicAuth(config.JIRA_EMAIL, config.JIRA_API_TOKEN)
        self._base = config.JIRA_BASE_URL.rstrip("/")
        self._session = requests.Session()
        self._session.auth = self._auth
        self._session.headers.update({"Accept": "application/json"})

    def _search(self, jql: str, fields: list[str], max_results: int = 200) -> list[dict]:
        """Run a JQL search and return all issues (handles pagination)."""
        url = f"{self._base}/rest/api/3/search"
        issues: list[dict] = []
        start_at = 0

        while True:
            resp = self._session.get(url, params={
                "jql": jql,
                "fields": ",".join(fields),
                "maxResults": max_results,
                "startAt": start_at,
            })
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("issues", [])
            issues.extend(batch)

            if start_at + len(batch) >= data.get("total", 0):
                break
            start_at += len(batch)

        log.debug("JQL '%s' returned %d issues", jql, len(issues))
        return issues

    def _normalize(self, issue: dict[str, Any]) -> dict:
        """Flatten a raw Jira issue into a clean dict for the rules engine."""
        fields = issue.get("fields", {})

        assignee = fields.get("assignee")
        assignee_name = assignee.get("displayName", "Unassigned") if assignee else "Unassigned"

        return {
            "id":           issue["id"],
            "key":          issue["key"],                           # e.g. "A1A-42"
            "ticket_num":   int(issue["key"].split("-")[1]),        # numeric part for ordering
            "summary":      fields.get("summary", ""),
            "status":       fields.get("status", {}).get("name", ""),
            "assignee":     assignee_name,
            "priority":     fields.get("priority", {}).get("name", ""),
            "created_at":   _parse_jira_dt(fields["created"]),
            "updated_at":   _parse_jira_dt(fields["updated"]),
            "url":          f"{self._base}/browse/{issue['key']}",
            "project":      fields.get("project", {}).get("key", ""),
        }

    # ── Public methods ────────────────────────────────────────────────────────

    def get_open_a1a_tickets(self) -> list[dict]:
        """Return all tickets in the A1A project with status = Open."""
        jql = (
            f'project = "{config.JIRA_A1A_PROJECT}" '
            f'AND status = "Open" '
            f'ORDER BY created ASC'
        )
        fields = ["summary", "status", "assignee", "priority", "created", "updated", "project"]
        issues = self._search(jql, fields)
        return [self._normalize(i) for i in issues]

    def get_open_oca_tickets(self) -> list[dict]:
        """Return all OCA tickets that are NOT closed (covers Rules 2 + 3)."""
        jql = (
            f'project = "{config.JIRA_OCA_PROJECT}" '
            f'AND status != "Closed" '
            f'ORDER BY created ASC'
        )
        fields = ["summary", "status", "assignee", "priority", "created", "updated", "project"]
        issues = self._search(jql, fields)
        return [self._normalize(i) for i in issues]

    def get_in_progress_tickets(self, project: str) -> list[dict]:
        """Return tickets currently In Progress for out-of-order detection (Rule 4)."""
        jql = (
            f'project = "{project}" '
            f'AND status = "In Progress" '
            f'ORDER BY created ASC'
        )
        fields = ["summary", "status", "assignee", "priority", "created", "updated", "project"]
        issues = self._search(jql, fields)
        return [self._normalize(i) for i in issues]
