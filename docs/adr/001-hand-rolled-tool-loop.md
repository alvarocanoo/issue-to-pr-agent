# ADR-001: Hand-rolled tool loop over an agent framework

**Status**: accepted
**Date**: 2026-05-26
**Deciders**: Álvaro

## Context

The agent needs a tool-use loop: send messages + tool schemas to an LLM, execute the tool
calls it returns, append the results, repeat until the model stops requesting tools or a
verification step decides success. There are mature libraries that do this already; the
question is whether to use one.

Constraints:
- This project is part of a portfolio aimed at AI Engineer hiring. The agent must be defendible
  line by line in a code review — "I imported X and called it" is the opposite of the signal we want.
- Vendor independence matters: the model behind the loop should be swappable.
- Time budget: 4-6 weeks. The loop itself is ~200 lines; the right framework saves ~150 of those.

## Alternatives considered

1. **LangChain / LangGraph** — most popular agent ecosystem; LangGraph in particular models the
   loop as an explicit state machine. Pros: batteries included, large community. Cons: heavy
   abstractions (`Runnable`, `Chain`, callbacks) that obscure the actual prompt and tool
   semantics; opinionated state shape; provider lock-in via integrations even when "abstracted";
   well-known criticism in the agent community of pulling in transitive deps for trivial logic.
2. **Claude Agent SDK** — first-class tool loop, hooks, subagents, MCP. Pros: best-in-class for
   Anthropic. Cons: Anthropic-only by design (Bedrock/Vertex/Azure aside) — incompatible with
   the Groq pivot (see [ADR-009](009-groq-over-anthropic-openai.md)).
3. **OpenAI Agents SDK** — newer, OpenAI-first. Similar lock-in to (2) but for OpenAI.
4. **Hand-rolled** — write the loop directly against the provider SDK's chat-completions
   primitive. ~200 LOC for executor + tools + prompts + retry. No abstractions between the
   model and the reader of the code.

## Decision

Hand-roll. The loop lives in [`src/issue_to_pr/executor/executor.py`](../../src/issue_to_pr/executor/executor.py)
and calls [`LLMClient`](../../src/issue_to_pr/llm/client.py), which is the only place that
imports the Groq SDK. Tools are plain Python functions registered in a dict +
JSON-schema entries that the LLM sees.

The loop follows the **ReAct** pattern (Yao et al., 2022 — "Reasoning and Acting in Language
Models"): each turn the model emits a thought (via `content`) and/or tool calls; tool results
are fed back as `role=tool` messages; loop terminates when the model stops requesting tools
or `task.max_iterations` is exceeded. Success is decided by a verification command in the
sandbox, **not** by the model's self-report (see [ADR-002](002-planner-executor-verifier.md),
planned).

## Consequences

**Easier**:
- Every prompt, tool schema, and termination rule is visible in <300 lines of code.
- Switching providers = rewriting `llm/client.py` (one file, ~200 LOC).
- No transitive dependencies (groq + pydantic + typer + rich, nothing else for the loop).
- Reviewer / interviewer can challenge any line; we can answer without "the framework does that".

**Harder**:
- We re-implement features that frameworks ship for free: retry/backoff (ADR-009 + `_chat_with_retries`),
  session resume (not implemented yet), structured tracing (Week 3 via Langfuse).
- Bugs we introduce here are our own; no community fixes.

**Accepted**:
- ~200 extra lines of maintenance vs picking LangGraph. We trade them for full ownership of
  the agent loop's semantics.

## Verification

The hand-rolled loop is what makes the trivial eval suite work: 10/10 resolved@1 on
`evals/trivial_issues/` with `openai/gpt-oss-20b` (see [README "Measured metrics"](../../README.md)).
If this decision were wrong, we would either see (a) low resolved@1 because we missed a loop
detail a framework would have caught, or (b) a maintenance ratio (LOC executor / LOC adding a
new tool) higher than what a framework would give us. Today, neither is happening.

When SWE-bench Lite numbers land (Week 4), we revisit: if our resolved@1 is more than ~15pp
below comparable open-source agents (e.g., mini-SWE-agent on the same model), the framework
choice is the first thing to re-examine.
