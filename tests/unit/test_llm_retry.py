"""Unit tests for LLMClient retry/backoff on Groq RateLimitError."""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from groq import RateLimitError

from issue_to_pr.llm import LLMClient, LLMMessage
from issue_to_pr.llm.client import _retry_after_from_error


def _build_rate_limit_error(message: str = "Please try again in 4.2s") -> RateLimitError:
    """Construct a Groq RateLimitError with a body that includes a retry hint."""
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(
        status_code=429,
        request=request,
        headers={"content-type": "application/json"},
    )
    body = {
        "error": {
            "message": message,
            "type": "tokens",
            "code": "rate_limit_exceeded",
        }
    }
    return RateLimitError(message, response=response, body=body)


def _fake_ok_response() -> MagicMock:
    msg = MagicMock()
    msg.content = "ok"
    msg.reasoning = None
    msg.tool_calls = []
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "stop"
    usage = MagicMock()
    usage.prompt_tokens = 1
    usage.completion_tokens = 1
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    resp.model = "openai/gpt-oss-20b"
    return resp


def test_retry_after_parses_groq_message() -> None:
    exc = _build_rate_limit_error("Rate limit reached. Please try again in 3.14s. Need more?")
    delay = _retry_after_from_error(exc)
    # Slight margin added by implementation; cap at 60.
    assert 3.14 <= delay <= 60.0
    assert delay < 5.0  # 3.14 + 0.5 margin


def test_retry_after_uses_default_when_no_hint() -> None:
    exc = _build_rate_limit_error("no time hint here")
    delay = _retry_after_from_error(exc)
    # Default is 10s; check it's reasonable, not the cap.
    assert 5.0 <= delay <= 30.0


def test_retry_after_caps_at_60s() -> None:
    exc = _build_rate_limit_error("Please try again in 9999.0s")
    delay = _retry_after_from_error(exc)
    assert delay <= 60.0


def test_retry_after_respects_retry_after_header() -> None:
    request = httpx.Request("POST", "https://api.groq.com/x")
    response = httpx.Response(
        status_code=429,
        request=request,
        headers={"retry-after": "7"},
    )
    exc = RateLimitError("rate limited", response=response, body={})
    delay = _retry_after_from_error(exc)
    assert delay == 7.0


def test_invalid_max_retries_rejected() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        LLMClient(api_key="gsk_x", max_retries_on_rate_limit=-1)


def test_chat_retries_on_rate_limit_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two 429s followed by a success returns the success response and sleeps twice."""
    sleeps: list[float] = []
    monkeypatch.setattr("issue_to_pr.llm.client.time.sleep", lambda s: sleeps.append(s))

    client = LLMClient(api_key="gsk_x", max_retries_on_rate_limit=3)
    client._groq = MagicMock()
    client._groq.chat.completions.create.side_effect = [
        _build_rate_limit_error("Please try again in 1.0s"),
        _build_rate_limit_error("Please try again in 1.0s"),
        _fake_ok_response(),
    ]

    resp = client.chat(model="m", messages=[LLMMessage(role="user", content="hi")])
    assert resp.content == "ok"
    assert client._groq.chat.completions.create.call_count == 3
    assert len(sleeps) == 2
    assert all(re.match(r".*", str(s)) and s > 0 for s in sleeps)


def test_chat_gives_up_after_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("issue_to_pr.llm.client.time.sleep", lambda _s: None)
    client = LLMClient(api_key="gsk_x", max_retries_on_rate_limit=2)
    client._groq = MagicMock()
    client._groq.chat.completions.create.side_effect = [
        _build_rate_limit_error(),
        _build_rate_limit_error(),
        _build_rate_limit_error(),
    ]
    with pytest.raises(RateLimitError):
        client.chat(model="m", messages=[LLMMessage(role="user", content="hi")])
    assert client._groq.chat.completions.create.call_count == 3


def test_chat_no_retry_on_other_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-RateLimit errors propagate without retry."""
    monkeypatch.setattr("issue_to_pr.llm.client.time.sleep", lambda _s: None)
    client = LLMClient(api_key="gsk_x")
    client._groq = MagicMock()
    client._groq.chat.completions.create.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError, match="boom"):
        client.chat(model="m", messages=[LLMMessage(role="user", content="hi")])
    assert client._groq.chat.completions.create.call_count == 1


def _unused() -> Any:  # keep Any import alive even if unused above
    return None
