"""Integration test: real call to Groq with a tiny prompt.

Skipped automatically when GROQ_API_KEY is missing (e.g. CI without secret).
Runs on every local `pytest` invocation when the key is set.
"""

from __future__ import annotations

import os

import pytest

from issue_to_pr.llm import LLMClient, LLMMessage
from issue_to_pr.settings import get_settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("GROQ_API_KEY") and not get_settings().groq_api_key,
        reason="GROQ_API_KEY not set; skipping live Groq integration",
    ),
]


def test_real_groq_chat_returns_content() -> None:
    s = get_settings()
    client = LLMClient(api_key=s.groq_api_key)
    resp = client.chat(
        model="llama-3.3-70b-versatile",
        messages=[LLMMessage(role="user", content="Reply with exactly: SMOKE_OK")],
        max_tokens=20,
    )
    assert "SMOKE_OK" in resp.content
    assert resp.prompt_tokens > 0
    assert resp.completion_tokens > 0
    assert resp.finish_reason in {"stop", "length"}


def test_real_groq_reasoning_model_populates_both_fields() -> None:
    """gpt-oss-* returns reasoning separately from content. Wrapper must surface both."""
    s = get_settings()
    client = LLMClient(api_key=s.groq_api_key)
    resp = client.chat(
        model="openai/gpt-oss-20b",
        messages=[LLMMessage(role="user", content="Reply with exactly: SMOKE_OK")],
        max_tokens=500,
    )
    assert "SMOKE_OK" in resp.content
    assert resp.reasoning is not None
    assert len(resp.reasoning) > 0
