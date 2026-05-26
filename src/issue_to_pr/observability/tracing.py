"""Langfuse v4 tracing wrapper with a silent no-op fallback.

Design:
- `is_enabled()` returns True only when both LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY
  are set. The agent never crashes when they are not — the wrapper just returns dummy
  context managers that do nothing.
- `LangfuseTracer.span(name=...)` and `LangfuseTracer.generation(name=..., model=..., ...)`
  are context managers. Use them with `with ...:` blocks; nesting is automatic.
- `LangfuseTracer.flush()` should be called once per run (e.g. at the end of
  `Orchestrator.run()`) so events ship before the process exits.
- `LangfuseTracer.trace_url()` returns the URL of the *current* trace, useful to persist
  alongside the run so the dashboard can deep-link into Langfuse.

The wrapper is intentionally not a singleton: `get_tracer()` rebuilds a small object that
either wraps the Langfuse client or is a no-op shim. This makes testing trivial.
"""

from __future__ import annotations

import contextlib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    """True when both Langfuse keys are present in the environment."""
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY")) and bool(
        os.environ.get("LANGFUSE_SECRET_KEY")
    )


class _NoopSpan:
    """Stand-in for a Langfuse span when tracing is disabled."""

    def update(self, **_: Any) -> None:
        return None

    def __enter__(self) -> _NoopSpan:
        return self

    def __exit__(self, *_: Any) -> None:
        return None


class LangfuseTracer:
    """Small façade over the Langfuse v4 client. Falls back to no-op when disabled."""

    def __init__(self) -> None:
        self._client: Any = None
        if is_enabled():
            try:
                from langfuse import Langfuse

                self._client = Langfuse(
                    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
                    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
                    host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                )
                logger.info(
                    "Langfuse tracing enabled (host=%s)",
                    os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                )
            except Exception as exc:  # noqa: BLE001  # never crash the agent because Langfuse is broken
                logger.warning("Langfuse init failed; tracing disabled: %s", exc)
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def span(self, name: str, **kwargs: Any) -> Any:
        if self._client is None:
            return _NoopSpan()
        return self._client.start_as_current_observation(as_type="span", name=name, **kwargs)

    def generation(self, *, name: str, model: str, **kwargs: Any) -> Any:
        if self._client is None:
            return _NoopSpan()
        return self._client.start_as_current_observation(
            as_type="generation", name=name, model=model, **kwargs
        )

    def update_current(self, **kwargs: Any) -> None:
        """Update the active observation's attributes (input/output/usage/metadata)."""
        if self._client is None:
            return
        with contextlib.suppress(Exception):
            # No-op safely if there's no current span — Langfuse logs a warning we don't need.
            self._client.update_current_span(**kwargs)

    def trace_url(self) -> str | None:
        """URL of the current trace, if one is open. None when disabled / no trace."""
        if self._client is None:
            return None
        try:
            return self._client.get_trace_url()  # type: ignore[no-any-return]
        except Exception as exc:  # noqa: BLE001
            logger.debug("could not compute trace_url: %s", exc)
            return None

    def flush(self) -> None:
        if self._client is None:
            return
        with contextlib.suppress(Exception):
            self._client.flush()


def get_tracer() -> LangfuseTracer:
    """Build a fresh tracer. Cheap; the underlying client is itself cached internally."""
    return LangfuseTracer()
