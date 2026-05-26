"""Thin wrapper over the Groq Python SDK.

Every LLM call in the agent flows through `LLMClient.chat()`. That keeps:
- A single place to add retry / timeout / circuit breaking later.
- A single place to wire Langfuse traces (Week 3).
- A single place to track token usage and (when relevant) cost.

Why a wrapper instead of using `groq.Groq()` directly everywhere:
- gpt-oss-* models return reasoning tokens in `message.reasoning`, separate from
  `message.content`. The agent often needs both (content drives tool calls, reasoning
  is logged for debug). Centralising the extraction keeps callers from forgetting.
- Provider switch (Groq -> OpenAI -> local) becomes a one-file change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from groq import Groq

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class LLMMessage:
    """One turn in a chat completion request."""

    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None

    def to_groq(self) -> dict[str, Any]:
        out: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name is not None:
            out["name"] = self.name
        if self.tool_call_id is not None:
            out["tool_call_id"] = self.tool_call_id
        return out


@dataclass(frozen=True)
class LLMToolCall:
    """One tool call requested by the model."""

    id: str
    name: str
    arguments_json: str


@dataclass(frozen=True)
class LLMResponse:
    """Normalised chat completion. Fields are always populated; lists default empty."""

    content: str
    reasoning: str | None
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMClient:
    """Groq SDK wrapper. One instance per process is enough."""

    def __init__(self, api_key: str, *, base_url: str | None = None) -> None:
        if not api_key:
            raise ValueError("LLMClient requires a non-empty api_key")
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._groq = Groq(**kwargs)

    def chat(
        self,
        *,
        model: str,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        """Run one chat completion. Returns a normalised `LLMResponse`.

        `max_tokens=4096` default leaves room for reasoning models (gpt-oss-*).
        Callers can drop it for non-reasoning models.
        """
        if not messages:
            raise ValueError("messages must not be empty")

        request: dict[str, Any] = {
            "model": model,
            "messages": [m.to_groq() for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            request["tools"] = tools
        if tool_choice:
            request["tool_choice"] = tool_choice

        resp = self._groq.chat.completions.create(**request)
        choice = resp.choices[0]
        msg = choice.message

        tool_calls: list[LLMToolCall] = []
        raw_tool_calls = getattr(msg, "tool_calls", None) or []
        for tc in raw_tool_calls:
            tool_calls.append(
                LLMToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments_json=tc.function.arguments,
                )
            )

        usage = resp.usage
        return LLMResponse(
            content=(msg.content or "").strip(),
            reasoning=getattr(msg, "reasoning", None),
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            model=resp.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )
