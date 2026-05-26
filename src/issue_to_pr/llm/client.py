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

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from groq import Groq, RateLimitError

from issue_to_pr.llm.pricing import estimate_cost_usd
from issue_to_pr.observability import get_tracer

logger = logging.getLogger(__name__)

Role = Literal["system", "user", "assistant", "tool"]

# Default retry-after when the API does not provide one in the 429 response (seconds).
_DEFAULT_RETRY_AFTER = 10.0
# Hard cap to avoid an unbounded back-off on misbehaving servers.
_MAX_RETRY_AFTER = 60.0


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
    estimated_cost_usd: float = 0.0  # pay-as-you-go list price; free tier actually billed $0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def _retry_after_from_error(exc: RateLimitError) -> float:
    """Best-effort extraction of the server-suggested retry delay (seconds)."""
    response = getattr(exc, "response", None)
    if response is not None:
        header = response.headers.get("retry-after") if response.headers else None
        if header:
            try:
                return min(float(header), _MAX_RETRY_AFTER)
            except ValueError:
                pass
    body = getattr(exc, "body", None) or {}
    message = ""
    if isinstance(body, dict):
        message = (
            str(body.get("error", {}).get("message", ""))
            if isinstance(body.get("error"), dict)
            else ""
        )
    if not message:
        message = str(exc)
    # Groq messages include "Please try again in 3.93s" — parse it.
    import re

    match = re.search(r"try again in ([\d.]+)s", message)
    if match:
        try:
            return min(float(match.group(1)) + 0.5, _MAX_RETRY_AFTER)
        except ValueError:
            pass
    return _DEFAULT_RETRY_AFTER


class LLMClient:
    """Groq SDK wrapper. One instance per process is enough."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        max_retries_on_rate_limit: int = 4,
    ) -> None:
        if not api_key:
            raise ValueError("LLMClient requires a non-empty api_key")
        if max_retries_on_rate_limit < 0:
            raise ValueError("max_retries_on_rate_limit must be >= 0")
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._groq = Groq(**kwargs)
        self._max_retries = max_retries_on_rate_limit
        self._tracer = get_tracer()

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

        with self._tracer.generation(name="chat", model=model) as observation:
            resp = self._chat_with_retries(request)
            choice = resp.choices[0]
            msg = choice.message
            # When tracing is enabled, attach the input/output/usage to the span.
            if hasattr(observation, "update"):
                observation.update(
                    input=[m.to_groq() for m in messages],
                    output=msg.content,
                    usage_details={
                        "input": resp.usage.prompt_tokens if resp.usage else 0,
                        "output": resp.usage.completion_tokens if resp.usage else 0,
                    },
                    metadata={"finish_reason": choice.finish_reason},
                )

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
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        return LLMResponse(
            content=(msg.content or "").strip(),
            reasoning=getattr(msg, "reasoning", None),
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            model=resp.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=estimate_cost_usd(resp.model, prompt_tokens, completion_tokens),
        )

    def _chat_with_retries(self, request: dict[str, Any]) -> Any:
        """Call chat.completions.create with retry+backoff on Groq RateLimitError.

        The Groq SDK has internal retries for 429 but they cap at a few seconds. On the
        free tier we hit TPM ceilings that need longer waits; this respects the server's
        own "try again in Xs" message.
        """
        attempts = 0
        while True:
            try:
                return self._groq.chat.completions.create(**request)
            except RateLimitError as exc:
                attempts += 1
                if attempts > self._max_retries:
                    raise
                delay = _retry_after_from_error(exc)
                logger.warning(
                    "groq rate limit (attempt %s/%s); sleeping %.1fs",
                    attempts,
                    self._max_retries,
                    delay,
                )
                time.sleep(delay)
