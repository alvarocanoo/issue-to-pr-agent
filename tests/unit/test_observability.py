"""Unit tests for the Langfuse tracing wrapper.

Goal: confirm the agent is unaffected when Langfuse is disabled. We never test against the
real Langfuse Cloud here — that's a smoke check the developer runs manually after setting
keys in .env.
"""

from __future__ import annotations

import pytest

from issue_to_pr.observability import LangfuseTracer, get_tracer, is_enabled
from issue_to_pr.observability.tracing import _NoopSpan


def test_disabled_when_no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert is_enabled() is False


def test_disabled_when_only_one_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-only")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert is_enabled() is False


def test_tracer_no_op_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    tracer = LangfuseTracer()
    assert tracer.enabled is False
    # Spans must behave like context managers and accept any kwargs without crashing.
    with tracer.span(name="x"):
        pass
    with tracer.generation(name="y", model="m"):
        pass
    tracer.update_current(input="a", output="b", usage_details={"input": 1, "output": 2})
    assert tracer.trace_url() is None
    tracer.flush()


def test_noop_span_returns_self_and_swallows_update() -> None:
    span = _NoopSpan()
    with span as inner:
        assert inner is span
        inner.update(input="x", output="y", whatever=True)


def test_get_tracer_returns_fresh_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    a = get_tracer()
    b = get_tracer()
    assert a is not b  # cheap to build; tests can monkeypatch isolated instances
