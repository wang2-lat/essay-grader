"""Shared fixtures for the offline test suite.

Rules this suite enforces:
  * No network. Every socket connection attempt raises, so a test that forgets
    to mock the model fails loudly instead of quietly calling a real API.
  * No real model key. GRADER_* env vars are set to dummy values for each test.
  * Every model call goes through ``fake_llm``, which replaces
    ``app.core.grader._client`` (the single place all model calls come from).
"""
from __future__ import annotations

import json
import socket
from types import SimpleNamespace

import pytest

from app.core import grader, limiter


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise RuntimeError("tests must not touch the network; use the fake_llm fixture")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    yield


@pytest.fixture(autouse=True)
def _dummy_config(monkeypatch):
    monkeypatch.setenv("GRADER_API_KEY", "test-key-not-real")
    monkeypatch.setenv("GRADER_BASE_URL", "http://model.invalid/v1")
    monkeypatch.setenv("GRADER_MODEL", "fake-model")
    monkeypatch.delenv("GRADER_API_TOKEN", raising=False)
    for name in ("GRADER_MAX_CHARS", "GRADER_RATE_PER_MIN", "GRADER_DAILY_LIMIT"):
        monkeypatch.delenv(name, raising=False)
    grader._client_cache.clear()
    yield
    grader._client_cache.clear()


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter._state.update({"day": None, "day_count": 0, "recent": []})
    yield
    limiter._state.update({"day": None, "day_count": 0, "recent": []})


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """The scorer/annotator retry with time.sleep(3)/(8); don't wait in tests."""
    from app.ap import annotator, scorer

    monkeypatch.setattr(scorer.time, "sleep", lambda s: None)
    monkeypatch.setattr(annotator.time, "sleep", lambda s: None)
    yield


class FakeLLM:
    """Stand-in for the OpenAI client. Replies are consumed in order.

    Each reply is a dict (sent back as JSON), a str (sent back verbatim) or an
    Exception instance (raised from ``create``).
    """

    def __init__(self):
        self.replies: list = []
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def queue(self, *replies):
        self.replies.extend(replies)
        return self

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.replies:
            raise AssertionError("FakeLLM: unexpected extra model call")
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(grader, "_client", lambda: fake)
    return fake
