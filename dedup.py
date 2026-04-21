"""
dedup.py — Alert deduplication state store.

Prevents the same ticket+rule from firing repeatedly every poll cycle.
Default backend: a local JSON file (zero dependencies, works in Lambda too).
Set REDIS_URL in your environment to switch to Redis automatically.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import config

log = logging.getLogger(__name__)

# ── Key format: "{ticket_key}:{rule_id}"  e.g. "A1A-42:rule1_idle"
# ── Value: unix timestamp when the alert was last sent


class DedupStore:
    """Abstract interface — use JsonDedupStore or RedisDedupStore."""

    def was_recently_alerted(self, key: str, cooldown_hours: float) -> bool:
        raise NotImplementedError

    def mark_alerted(self, key: str) -> None:
        raise NotImplementedError

    def clear(self, key: str) -> None:
        """Call this when a ticket is resolved, so it can re-alert if it regresses."""
        raise NotImplementedError


class JsonDedupStore(DedupStore):
    """
    Stores alert state as a JSON file.
    Good for: local dev, single-instance Lambda, small teams.
    Not good for: multiple concurrent workers (use Redis instead).
    """

    def __init__(self, path: str = config.DEDUP_STORE_PATH) -> None:
        self._path = Path(path)
        self._data: dict[str, float] = self._load()

    def _load(self) -> dict[str, float]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError):
                log.warning("Dedup store corrupted, starting fresh: %s", self._path)
        return {}

    def _save(self) -> None:
        self._path.write_text(json.dumps(self._data, indent=2))

    def was_recently_alerted(self, key: str, cooldown_hours: float) -> bool:
        last_sent = self._data.get(key)
        if last_sent is None:
            return False
        elapsed_hours = (time.time() - last_sent) / 3600
        return elapsed_hours < cooldown_hours

    def mark_alerted(self, key: str) -> None:
        self._data[key] = time.time()
        self._save()

    def clear(self, key: str) -> None:
        self._data.pop(key, None)
        self._save()


class RedisDedupStore(DedupStore):
    """
    Redis-backed dedup store. Thread-safe, works across multiple workers.
    Activate by setting REDIS_URL env var (e.g. redis://localhost:6379/0).
    """

    def __init__(self, redis_url: str) -> None:
        try:
            import redis
            self._r = redis.from_url(redis_url)
            self._r.ping()
            log.info("Connected to Redis dedup store at %s", redis_url)
        except ImportError:
            raise RuntimeError("Install redis: pip install redis")
        except Exception as e:
            raise RuntimeError(f"Cannot connect to Redis at {redis_url}: {e}")

    def _redis_key(self, key: str) -> str:
        return f"jira_slo_alert:{key}"

    def was_recently_alerted(self, key: str, cooldown_hours: float) -> bool:
        return self._r.exists(self._redis_key(key)) == 1

    def mark_alerted(self, key: str, cooldown_hours: Optional[float] = None) -> None:
        rkey = self._redis_key(key)
        self._r.set(rkey, int(time.time()))
        if cooldown_hours:
            self._r.expire(rkey, int(cooldown_hours * 3600))

    def clear(self, key: str) -> None:
        self._r.delete(self._redis_key(key))


def make_store() -> DedupStore:
    """Factory — returns Redis store if REDIS_URL is set, else JSON file store."""
    if config.REDIS_URL:
        return RedisDedupStore(config.REDIS_URL)
    return JsonDedupStore()
