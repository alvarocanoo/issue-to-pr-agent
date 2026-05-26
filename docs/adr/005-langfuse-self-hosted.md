# ADR-005: Per-tool-call traces via Langfuse (planned)

**Status**: accepted — wired via context-manager spans in `LLMClient` and `Orchestrator`, gated by `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`. Silent no-op when keys are missing, so CI and the public Pages deploy run unchanged.
**Date**: 2026-05-26
**Deciders**: Álvaro

## Context

The Postgres-backed runs table stores per-iteration *summaries* (executor token counts,
verdict reasoning, tool-call **count**), but not the individual tool calls themselves. A
reviewer who wants to know "exactly which `read_file` calls did the agent make, in what
order, with what arguments and which outputs" cannot get that from the dashboard today.

This is the gap an LLM trace tool fills: one span per LLM call + nested spans per tool
invocation, with prompts, completions, latency and cost per span, queryable by run id.

The agent already routes every LLM call through `LLMClient.chat()` and every tool through
the registry in `executor/tools.py`, so wiring a tracer is a single-file change in each.

## Alternatives considered

1. **Langfuse self-hosted (Docker Compose)** — open-source, full feature set, no per-event
   pricing. Cons: requires Docker locally (we don't have Docker on the dev machine,
   [ADR-003](003-pluggable-sandbox.md)). Hostable on a tiny VPS later.
2. **Langfuse Cloud (managed SaaS)** — same UI/feature parity, no infra to run, free tier
   = 50 000 events/month + 30-day retention. Setup is one API key + one env var.
3. **Phoenix / Arize Phoenix** — open-source, ecosystem-friendly with LlamaIndex/LangChain.
   Less mature for raw chat-completions + tool-use traces than Langfuse.
4. **Helicone** — proxy-based (replace `api.groq.com` with a Helicone gateway). Pros: no
   SDK change. Cons: pulls a third party into every request path; we lose the option to
   move to a non-OpenAI-shaped provider without a separate Helicone integration.
5. **OpenTelemetry only** — most generic. Cons: there's no good "view per LLM trace" UI
   for raw OTel without wiring something like Jaeger; not worth the boilerplate at this
   project size.

## Decision

**Langfuse Cloud (option 2) for the project demo, with the option to swap to Langfuse
Self-hosted (option 1) if cost or compliance ever becomes an issue.**

Reasons:
- The wrapper layer (`LLMClient`) is already a single chokepoint; instrumenting it is
  one `@observe` decorator + a `langfuse.flush()` at the end of `Orchestrator.run()`.
- 50 k events/month free is plenty for the trivial set (each orchestrator run produces
  ~10-15 LLM calls, so 50 k events ≈ 3 000-5 000 runs/month — far above what the demo
  needs).
- The dashboard can deep-link to a Langfuse trace by `task_id` (`/traces?search=...`) so
  reviewers see "open in Langfuse" buttons on the detail page.

## Consequences

**Easier**:
- Reviewers can step through the agent's actual prompts and tool outputs without
  cloning the repo.
- Per-tool-call cost and latency become visible without us computing them.
- Easy to A/B prompts: tag traces and filter in the Langfuse UI.

**Harder**:
- Each LLM call now incurs a tiny network call to Langfuse Cloud. Failure of Langfuse
  must not crash the agent; wrap with `try/except` and continue. Already the pattern we
  use for storage persistence.
- One more secret to manage (`LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`,
  `LANGFUSE_HOST=https://cloud.langfuse.com`). They go in `.env`, with the same
  no-commit rule as `GROQ_API_KEY`.

**Accepted**:
- Vendor lock-in to Langfuse for the trace UI. Mitigated because every trace is also
  duplicated in our Postgres `runs.history` JSON (summarised), and the SDK can export
  to OTel if we ever switch. Not a permanent dependency.

## Implementation (shipped 2026-05-26)

Langfuse SDK v4 changed its public surface: decorators are deprecated in favour of context
managers. The wiring uses `Langfuse.start_as_current_observation(as_type=..., name=...)`
inside small `LangfuseTracer.span()` / `LangfuseTracer.generation()` helpers
(`src/issue_to_pr/observability/tracing.py`) that fall back to a `_NoopSpan` when the
keys are not set. Every LLM call in `LLMClient.chat()` opens a `generation` span; the
orchestrator wraps each run in a root span with nested `plan`, `reflexion-iteration-N`,
`executor` and `verifier` spans.

```python
# src/issue_to_pr/llm/client.py (shipped)
with self._tracer.generation(name="chat", model=model) as observation:
    resp = self._chat_with_retries(request)
    ...
    observation.update(input=..., output=..., usage_details={...}, metadata={...})

# src/issue_to_pr/orchestrator.py (shipped)
with tracer.span(name=f"orchestrator/{task.id}") as root_span:
    root_span.update(input=..., metadata=...)
    with tracer.span(name="plan"):
        plan = self._planner.plan(task)
    for iteration in range(1, self._max_iter + 1):
        with tracer.span(name=f"reflexion-iteration-{iteration}"):
            with tracer.span(name="executor"):
                execution = self._executor.run(iter_task)
            with tracer.span(name="verifier"):
                verdict = self._verifier.judge(task, execution)
    trace_url = tracer.trace_url()
tracer.flush()
```

`OrchestratorResult.langfuse_trace_url` carries the URL up to the runner, which persists
it in `runs.langfuse_trace_url` (nullable TEXT column). The Next.js detail page renders
"Open trace in Langfuse →" as a button when the URL is present.

## Verification

- Unit tests (`tests/unit/test_observability.py`, 5 tests): tracer no-op when keys are
  missing, span contexts swallow attribute updates, `trace_url()` is `None` when disabled.
  Run on every CI push.
- Disabled path (default in CI + public Pages deploy): `is_enabled()` is False ⇒ tracer
  returns `_NoopSpan` ⇒ agent runs unchanged ⇒ no network calls to Langfuse.
- Enabled path (developer adds keys to `.env`): a single orchestrator run produces a
  hierarchical trace in Langfuse Cloud with the spans listed above; the URL is persisted
  to `runs.langfuse_trace_url`; the dashboard detail page renders the deep-link button.

See the README "Enable Langfuse traces" subsection for the exact setup steps.
