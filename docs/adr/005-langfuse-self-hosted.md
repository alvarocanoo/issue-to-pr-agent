# ADR-005: Per-tool-call traces via Langfuse (planned)

**Status**: planned — wiring lands in Week 3.3, after the Postgres/dashboard layer
([ADR-006](006-postgres-jsonb.md), [ADR-010](010-run-persistence-and-observability.md))
is stable.
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

## Implementation sketch

```python
# src/issue_to_pr/llm/client.py (sketch)
from langfuse.decorators import langfuse_context, observe

class LLMClient:
    @observe(as_type="generation")
    def chat(self, *, model, messages, tools, max_tokens, temperature, ...):
        # existing body
        langfuse_context.update_current_observation(
            model=model,
            usage={"input": prompt_tokens, "output": completion_tokens},
            metadata={"finish_reason": resp.finish_reason},
        )
        return ...

# src/issue_to_pr/orchestrator.py (sketch)
@observe()
def run(self, task: Task) -> OrchestratorResult:
    langfuse_context.update_current_trace(name=f"orchestrator/{task.id}", session_id=task.id)
    # ...
    langfuse_context.flush()
```

The dashboard adds a `langfuse_trace_url` field on `runs` (nullable), populated by the
orchestrator from `langfuse_context.get_current_trace_url()`. The detail page renders it
as a button: "Open trace in Langfuse →".

## Verification

When ADR-005 lands as `accepted`:
- Smoke: one orchestrator run produces a visible trace in the Langfuse Cloud UI at the
  expected `trace_url`.
- Failure mode: `LANGFUSE_PUBLIC_KEY=""` (no creds) → agent runs unchanged, no traces,
  no exceptions, no warnings beyond a single `logger.info("Langfuse disabled")`.
- Dashboard regression: detail page shows the deep-link button when `langfuse_trace_url`
  is set on the run, hides it when null.

Until then this ADR is `planned`; no Langfuse code is in the tree.
