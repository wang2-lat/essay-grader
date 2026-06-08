"""Lightweight in-process abuse guard for the local grading API.

Protects the operator's own model key from runaway cost: a stuck loop, a spammy
page, an over-eager extension, or simply heavy use can otherwise drain/throttle
the key (as happens in practice). Three independent caps, all env-configurable:

  GRADER_MAX_CHARS     reject essays longer than this           (default 15000)
  GRADER_RATE_PER_MIN  max gradings per rolling 60s             (default 12)
  GRADER_DAILY_LIMIT   max gradings per local calendar day      (default 200)

Set any to 0 to disable that particular cap. Counters are per-process and reset
on restart; this is a guard rail, not billing. Because the server binds to
127.0.0.1, this only ever meters the operator's own usage.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import date

_LOCK = threading.Lock()
_state: dict = {"day": None, "day_count": 0, "recent": []}


def _cfg() -> tuple[int, int, int]:
    def _int(name: str, default: int) -> int:
        try:
            return int(os.environ.get(name, str(default)))
        except ValueError:
            return default
    return (
        _int("GRADER_MAX_CHARS", 15000),
        _int("GRADER_RATE_PER_MIN", 12),
        _int("GRADER_DAILY_LIMIT", 200),
    )


def check(text_len: int) -> str | None:
    """Return a human-readable reason to BLOCK the request, or None to allow it.

    On allow, the request is counted against the rate/daily budgets.
    """
    max_chars, per_min, daily = _cfg()

    if max_chars and text_len > max_chars:
        return (f"Essay is too long ({text_len} characters; limit {max_chars}). "
                f"Trim it and try again.")

    now = time.time()
    today = date.today().isoformat()
    with _LOCK:
        if _state["day"] != today:
            _state["day"], _state["day_count"], _state["recent"] = today, 0, []
        _state["recent"] = [t for t in _state["recent"] if now - t < 60]

        if per_min and len(_state["recent"]) >= per_min:
            return (f"Rate limit: max {per_min} gradings per minute. "
                    f"Wait a few seconds and retry.")
        if daily and _state["day_count"] >= daily:
            return (f"Daily limit reached ({daily} gradings today). This protects "
                    f"your API key from runaway cost. It resets tomorrow — or raise "
                    f"GRADER_DAILY_LIMIT in .env.")

        _state["recent"].append(now)
        _state["day_count"] += 1
        return None


def status() -> dict:
    max_chars, per_min, daily = _cfg()
    with _LOCK:
        used = _state["day_count"] if _state["day"] == date.today().isoformat() else 0
    return {"used_today": used, "daily_limit": daily,
            "rate_per_min": per_min, "max_chars": max_chars}
