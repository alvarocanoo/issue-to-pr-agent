"""Unit tests for LLMClient: dataclasses, validation, response normalisation (mocked Groq SDK)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from issue_to_pr.llm import LLMClient, LLMMessage, LLMResponse, LLMToolCall


def _fake_groq_response(
    *,
    content: str = "ok",
    reasoning: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    finish_reason: str = "stop",
    model: str = "openai/gpt-oss-20b",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> MagicMock:
    """Build a MagicMock shaped like a Groq ChatCompletion response."""
    msg = MagicMock()
    msg.content = content
    msg.reasoning = reasoning
    msg.tool_calls = []
    for tc in tool_calls or []:
        tc_mock = MagicMock()
        tc_mock.id = tc["id"]
        tc_mock.function.name = tc["name"]
        tc_mock.function.arguments = tc["arguments_json"]
        msg.tool_calls.append(tc_mock)

    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = finish_reason

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    resp.model = model
    return resp


def _build_client(fake_resp: MagicMock) -> LLMClient:
    client = LLMClient(api_key="gsk_fake")
    client._groq = MagicMock()
    client._groq.chat.completions.create.return_value = fake_resp
    return client


def test_message_to_groq_drops_none_fields() -> None:
    m = LLMMessage(role="user", content="hi")
    assert m.to_groq() == {"role": "user", "content": "hi"}

    m2 = LLMMessage(role="tool", content="result", tool_call_id="call_1", name="read_file")
    assert m2.to_groq() == {
        "role": "tool",
        "content": "result",
        "tool_call_id": "call_1",
        "name": "read_file",
    }


def test_empty_api_key_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty api_key"):
        LLMClient(api_key="")


def test_empty_messages_rejected() -> None:
    client = _build_client(_fake_groq_response())
    with pytest.raises(ValueError, match="messages must not be empty"):
        client.chat(model="openai/gpt-oss-20b", messages=[])


def test_chat_normalises_plain_response() -> None:
    client = _build_client(_fake_groq_response(content="  hello  ", reasoning="thinking..."))
    resp = client.chat(
        model="openai/gpt-oss-20b",
        messages=[LLMMessage(role="user", content="hi")],
    )
    assert isinstance(resp, LLMResponse)
    assert resp.content == "hello"
    assert resp.reasoning == "thinking..."
    assert resp.tool_calls == []
    assert resp.finish_reason == "stop"
    assert resp.total_tokens == 15


def test_chat_extracts_tool_calls() -> None:
    client = _build_client(
        _fake_groq_response(
            content="",
            tool_calls=[
                {"id": "call_1", "name": "read_file", "arguments_json": '{"path":"a.py"}'},
                {"id": "call_2", "name": "bash", "arguments_json": '{"cmd":"ls"}'},
            ],
            finish_reason="tool_calls",
        )
    )
    resp = client.chat(
        model="openai/gpt-oss-20b",
        messages=[LLMMessage(role="user", content="do stuff")],
    )
    assert len(resp.tool_calls) == 2
    assert resp.tool_calls[0] == LLMToolCall(
        id="call_1", name="read_file", arguments_json='{"path":"a.py"}'
    )
    assert resp.finish_reason == "tool_calls"


def test_chat_passes_tools_and_choice_through() -> None:
    fake = _fake_groq_response()
    client = _build_client(fake)
    tools = [{"type": "function", "function": {"name": "x", "parameters": {}}}]
    client.chat(
        model="openai/gpt-oss-120b",
        messages=[LLMMessage(role="user", content="hi")],
        tools=tools,
        tool_choice="auto",
        max_tokens=2000,
        temperature=0.5,
    )
    kwargs = client._groq.chat.completions.create.call_args.kwargs  # type: ignore[attr-defined]
    assert kwargs["model"] == "openai/gpt-oss-120b"
    assert kwargs["max_tokens"] == 2000
    assert kwargs["temperature"] == 0.5
    assert kwargs["tools"] == tools
    assert kwargs["tool_choice"] == "auto"


def test_chat_omits_tools_when_none() -> None:
    fake = _fake_groq_response()
    client = _build_client(fake)
    client.chat(model="openai/gpt-oss-20b", messages=[LLMMessage(role="user", content="hi")])
    kwargs = client._groq.chat.completions.create.call_args.kwargs  # type: ignore[attr-defined]
    assert "tools" not in kwargs
    assert "tool_choice" not in kwargs


def test_handles_null_usage_gracefully() -> None:
    fake = _fake_groq_response()
    fake.usage = None
    client = _build_client(fake)
    resp = client.chat(model="openai/gpt-oss-20b", messages=[LLMMessage(role="user", content="hi")])
    assert resp.prompt_tokens == 0
    assert resp.completion_tokens == 0
    assert resp.total_tokens == 0
