"""Abuse guard: length cap, per-minute rate, daily cap, and the API wiring."""
from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.core import limiter


class _Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(limiter.time, "time", c)
    return c


def test_too_long_text_is_blocked_and_not_counted(monkeypatch):
    monkeypatch.setenv("GRADER_MAX_CHARS", "100")
    assert limiter.check(100) is None
    reason = limiter.check(101)
    assert reason and "too long" in reason
    assert limiter.status()["used_today"] == 1


def test_default_caps_when_env_unset():
    assert limiter.status() == {"used_today": 0, "daily_limit": 200,
                                "rate_per_min": 12, "max_chars": 15000}


def test_invalid_env_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("GRADER_RATE_PER_MIN", "lots")
    assert limiter.status()["rate_per_min"] == 12


def test_rate_limit_per_rolling_minute(monkeypatch, clock):
    monkeypatch.setenv("GRADER_RATE_PER_MIN", "3")
    assert [limiter.check(10) for _ in range(3)] == [None, None, None]
    reason = limiter.check(10)
    assert reason and "Rate limit" in reason
    clock.t += 61                      # window has rolled over
    assert limiter.check(10) is None


def test_daily_limit(monkeypatch, clock):
    monkeypatch.setenv("GRADER_RATE_PER_MIN", "0")   # 0 disables the rate cap
    monkeypatch.setenv("GRADER_DAILY_LIMIT", "2")
    assert limiter.check(10) is None
    assert limiter.check(10) is None
    reason = limiter.check(10)
    assert reason and "Daily limit" in reason


def test_daily_counter_resets_on_new_day(monkeypatch, clock):
    monkeypatch.setenv("GRADER_DAILY_LIMIT", "1")

    class _Day(dt.date):
        current = dt.date(2026, 1, 1)

        @classmethod
        def today(cls):
            return cls.current

    monkeypatch.setattr(limiter, "date", _Day)
    assert limiter.check(10) is None
    assert limiter.check(10) is not None
    _Day.current = dt.date(2026, 1, 2)
    assert limiter.check(10) is None


def test_zero_disables_every_cap(monkeypatch, clock):
    for name in ("GRADER_MAX_CHARS", "GRADER_RATE_PER_MIN", "GRADER_DAILY_LIMIT"):
        monkeypatch.setenv(name, "0")
    assert all(limiter.check(10 ** 6) is None for _ in range(50))


# ------------------------------------------------------------------ API wiring

@pytest.fixture
def client(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "API_TOKEN", "")
    # No `with` block: startup (init_db) is not run, so no database file is created.
    return TestClient(main.app)


def test_api_ap_grade_blocks_long_text_before_calling_model(client, fake_llm, monkeypatch):
    monkeypatch.setenv("GRADER_MAX_CHARS", "20")
    r = client.post("/api/ap_grade", json={"text": "x" * 21, "frq_type": "argument"})
    assert r.status_code == 429
    assert "too long" in r.json()["error"]
    assert fake_llm.calls == []


def test_api_grade_rate_limit_returns_429_without_model_call(client, fake_llm, monkeypatch, clock):
    monkeypatch.setenv("GRADER_RATE_PER_MIN", "1")
    fake_llm.queue({"scores": {"overall": 3}})
    first = client.post("/api/grade", json={"text": "A short essay."})
    assert first.status_code == 200
    second = client.post("/api/grade", json={"text": "A short essay."})
    assert second.status_code == 429
    assert len(fake_llm.calls) == 1


def test_api_requires_token_when_configured(client, fake_llm, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "API_TOKEN", "secret-token")
    r = client.post("/api/grade", json={"text": "hi"})
    assert r.status_code == 401
    r = client.post("/api/grade", json={"text": "hi"}, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401
    assert fake_llm.calls == []


def test_api_rejects_bad_frq_type_and_empty_text(client, fake_llm):
    assert client.post("/api/ap_grade", json={"text": "hi", "frq_type": "poem"}).status_code == 400
    assert client.post("/api/grade", json={"text": "   "}).status_code == 400
    assert fake_llm.calls == []


def test_health_endpoint_needs_no_model(client, fake_llm):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["model"] == "fake-model"
    assert fake_llm.calls == []
