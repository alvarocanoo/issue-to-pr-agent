# ADR-004: Multi-model routing on Groq Cloud

**Status**: accepted (executor model in use; planner/verifier wired but Semana 2 implements the split)
**Date**: 2026-05-26
**Deciders**: Álvaro

## Context

[ADR-009](009-groq-over-anthropic-openai.md) commits the project to Groq Cloud. Groq exposes
several open-source models. The question is which one(s) to use, and whether to route
different agent roles (planner, executor, verifier) to different models.

What matters in this project:
- **Throughput (tokens / second)**: the agent loop reads back tool results and re-decides each
  turn. A 5× faster model is roughly 5× faster wall-clock per issue.
- **Reasoning quality**: harder issues (and the verifier judging diffs) benefit from a model
  that thinks before answering.
- **Cost**: zero on Groq free tier — uniform across models. So **cost is not a routing signal
  on the free tier**; throughput × quality is.

## Alternatives considered

1. **Single model for everything** — simplest. Either pick the smartest (smaller throughput) or
   the fastest (worse on judgment-heavy steps).
2. **Cost-tiered routing across providers** (e.g., Haiku/Sonnet on Anthropic, gpt-4o/mini on
   OpenAI) — discarded by ADR-009.
3. **Capability-tiered routing on Groq** — separate model IDs per role: planner, executor,
   verifier. Free tier cost is uniform, so the optimisation is throughput-vs-quality.

## Decision

Three roles, two models (verified available on Groq Cloud, May 2026):

| Role | Model | Why |
|---|---|---|
| **Planner** | `openai/gpt-oss-120b` | One LLM call per task; reasoning-heavy ("what files to read, what to change"). ~10% of total tokens. Better model is worth the throughput hit. |
| **Executor** | `openai/gpt-oss-20b` | Burns ~80% of total tokens in the tool loop (Read/Edit/Bash/Grep). Throughput dominates wall-clock; gpt-oss-20b at 1000 tok/s is the highest-throughput reasoning model on Groq. Reasoning is short-context per turn. |
| **Verifier** | `openai/gpt-oss-120b` | One LLM-as-Judge call (Zheng et al., 2023, "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena"): better model judges diffs more reliably. ~10% of total tokens. |

Model IDs live in [`settings.py`](../../src/issue_to_pr/settings.py) and are overridable via
`.env`. The split is not yet behavioural — the current `Executor` uses the
`executor_model` only; the Planner/Verifier wiring lands in Semana 2 along with
[ADR-002](002-planner-executor-verifier.md).

## Consequences

**Easier**:
- Throughput-first executor keeps the wall-clock per issue under the 15-minute target
  (measured today: 24.3 s/issue on trivial set).
- Verifier upgrade later is changing one env var, not refactoring the loop.

**Harder**:
- Need to validate empirically that `gpt-oss-20b` is "good enough" for the executor role. If
  SWE-bench Lite shows the bottleneck is executor reasoning (not throughput), we have to
  trade speed for capability and re-measure.
- Two models in flight increases the surface of "did this run use the same models as last
  week?" — token usage per role is logged but not yet broken out per role in the JSON report.

**Accepted**:
- We do not split planner/executor/verifier today. The executor solves trivial issues alone
  (10/10). Semana 2 introduces the formal split; ADR-004 is written now so the routing
  rationale exists before the split code.

## Numbers we owe (Week 4)

| Variable | Currently | Plan |
|---|---|---|
| Tokens per role (planner / executor / verifier) | not split | log per-call role in Week 2; aggregate in eval JSON |
| Executor model: `gpt-oss-20b` vs `llama-3.3-70b-versatile` | gpt-oss-20b only | A/B over the same 50-issue SWE-bench Lite subset; pick whichever wins resolved@1 with equal time budget |
| Verifier model: `gpt-oss-120b` vs `gpt-oss-20b` | 120b only | A/B; if 20b judges as well at 2× speed, downgrade |

The ADR will be updated with measured numbers once those A/Bs run. Until then, the routing
above is a hypothesis backed by per-model throughput specs and the LLM-as-Judge paper, not by
this project's measurements.

## Verification

- Models in `settings.py` are loaded and the trivial eval set runs with them: 10/10 resolved
  on `gpt-oss-20b`, 24.3 s mean wall-clock (within 15-minute target).
- ADR-002 (Semana 2) will record the planner/verifier ablation when implemented.
