# ADR-009: Groq Cloud + open-source models over Anthropic / OpenAI APIs

**Status**: accepted
**Date**: 2026-05-26
**Deciders**: Álvaro

## Context

The project began with the Claude Agent SDK and Anthropic models (Sonnet 4.6 + Haiku 4.5).
That was reversed mid-Week 1 in favour of Groq Cloud with open-source models. This ADR
captures the reasoning so the trade-off is auditable instead of "why isn't this Claude?"

What we need from the inference provider:
1. **Tool use / function calling** — non-negotiable for an agent.
2. **A free tier large enough to iterate**, since this is a solo, unpaid build.
3. **Throughput high enough that a 10–15 iteration agent loop finishes in seconds, not
   minutes** — otherwise development is painful.
4. **An exit path**: if the provider goes away or prices rise, swapping out should be
   one file, not the whole codebase.

## Alternatives considered

1. **Anthropic Direct API** (Claude models). Pros: best-in-class tool use; the original plan.
   Cons: ~$5 of free credits per new account, then a credit card. Development burn for a
   solo project is real even at Haiku prices.
2. **OpenAI API**. Pros: large ecosystem. Cons: same pricing structure; not free for an
   iteration-heavy agent loop.
3. **Together AI, Anyscale, Fireworks, etc.** Pros: open-source models, OpenAI-compatible
   API. Cons: free tiers are smaller than Groq's; throughput lower.
4. **Local inference (vLLM, Ollama)**. Pros: zero cost after hardware. Cons: no GPU on the
   dev machine; gpt-oss-120b alone needs 80+ GB VRAM; not realistic.
5. **Groq Cloud**. Pros: 200 k tokens/day free tier without a credit card; throughput
   500–1000 tok/s on the gpt-oss family thanks to LPU silicon; OpenAI-compatible API +
   first-party Python SDK. Cons: only the open-source models Groq chooses to host; no
   custom fine-tunes (also see [ADR-008](008-no-fine-tuning.md)); rate limits cap evals.

## Decision

Use Groq Cloud as the only inference provider, via the official `groq` Python SDK wrapped in
[`LLMClient`](../../src/issue_to_pr/llm/client.py). Models picked:
- `openai/gpt-oss-120b` for the planner and verifier roles.
- `openai/gpt-oss-20b` for the executor role.

Routing rationale is in [ADR-004](004-multi-model-routing.md). The wrapper exposes one
method (`chat`) and one retry policy (`_chat_with_retries`); swapping to a different
OpenAI-compatible provider is a `base_url` change in `LLMClient.__init__` + verifying the
provider's chat-completions response shape matches what `LLMClient` parses.

## Reframing the portfolio narrative

The original Claude SDK pitch was "production-grade RAG/agent on the best frontier model".
The Groq + open-source pitch is **different and not worse**:

> A hand-rolled agent loop on open-source models served at >5× the throughput of typical
> hosted LLMs, with the LLM provider behind a one-file abstraction. $0 per run on the
> free tier, vendor-independent by design.

This positions the project for employers who **avoid vendor lock-in** (most enterprise
buyers), care about **inference cost** (almost all production ops teams), or run **regulated
workloads** where Anthropic / OpenAI cloud is off the table.

## Consequences

**Easier**:
- Cost is $0 during development and small evals. No card, no surprise bill.
- 500–1000 tok/s on the executor means a 10-iteration agent loop finishes in under 30 s,
  not minutes. Iteration latency is interview-demoable.
- The pitch "vendor-independent agent loop" is a real one and resonates with a slice of the
  market that the original Claude pitch did not address.

**Harder**:
- Free tier has **TPD = 200 000 tokens/day** and **TPM = 8 000 tokens/min** on
  `openai/gpt-oss-20b`. The trivial eval set burns ~90 k tokens per run. We can run it
  twice a day before hitting TPD. CI workflow design accounts for this
  ([`.github/workflows/evals.yml`](../../.github/workflows/evals.yml) is `workflow_dispatch`
  + `pull_request`-only, not `push`).
- Open-source models score below frontier Anthropic/OpenAI on SWE-bench Lite. We expect
  resolved@1 substantially below the 62.7% leaderboard SOTA of Claude Opus 4.6.
- Reasoning models (gpt-oss-\*) emit a separate `message.reasoning` field that must be
  budgeted in `max_tokens` (we observed empty `content` at `max_tokens=10` because the
  reasoning ate the budget). `LLMClient` captures both fields explicitly.

**Accepted**:
- Lower resolved@1 ceiling. The narrative around throughput and vendor independence carries
  the project; the absolute number on SWE-bench Lite will be honest but not best-in-class.
- We chose this trade-off knowingly. If, on the SWE-bench Lite numbers (Semana 4), the
  open-source ceiling is more than ~30 pp below SOTA, we re-evaluate against the original
  Anthropic plan + $5 free credits + topup.

## Verification

- `LLMClient` works against the real Groq API: smoke tests in
  [`tests/integration/test_llm_client_groq.py`](../../tests/integration/test_llm_client_groq.py)
  call `openai/gpt-oss-20b` (reasoning model) and `llama-3.3-70b-versatile` (non-reasoning)
  and verify both `content` and `reasoning` fields populate as expected.
- The trivial eval set runs at 10/10 resolved with Groq on the free tier, end-to-end,
  measured at 242.93 s total and 90 417 tokens. See README "Measured metrics".
- Retry/backoff (`_chat_with_retries`) parses Groq's "try again in Xs" message and is
  covered by 8 unit tests in
  [`tests/unit/test_llm_retry.py`](../../tests/unit/test_llm_retry.py).
