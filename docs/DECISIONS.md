# Architecture Decision Records

Each ADR captures a non-obvious technical decision with the alternatives considered, the choice
made, and the reasoning. Written *after* implementing the component when possible, so the
rationale is real and not aspirational.

| # | Title | Status | Implemented in |
|---|---|---|---|
| 000 | [Template](adr/000-template.md) | — | — |
| 001 | [Hand-rolled tool loop over an agent framework](adr/001-hand-rolled-tool-loop.md) | accepted | Week 1: `executor/` + `llm/client.py` |
| 002 | [Planner / Executor / Verifier split (ReAct + Reflexion + LLM-as-judge)](adr/002-planner-executor-verifier.md) | accepted (impl; A/B numbers Week 2) | Week 2: `planner/`, `verifier/`, `orchestrator.py` |
| 003 | [Pluggable sandbox (Local default, Container opt-in)](adr/003-pluggable-sandbox.md) | accepted (Local impl.; Container planned) | Week 1: `sandbox/` |
| 004 | [Multi-model routing on Groq Cloud](adr/004-multi-model-routing.md) | accepted (executor live; planner/verifier wire-up Week 2) | Week 1: `settings.py` |
| 005 | Langfuse self-hosted over Helicone / Phoenix / OpenTelemetry-only | planned | Week 3 |
| 006 | [Postgres + JSONB over SQLite or a document DB](adr/006-postgres-jsonb.md) | accepted | Week 3.1: `storage/`, `api/` |
| 007 | [SWE-bench Lite over Verified / full SWE-bench](adr/007-swe-bench-lite.md) | planned (50-subset Week 4) | Week 4 |
| 008 | [No fine-tuning — prompt + routing is the contract](adr/008-no-fine-tuning.md) | accepted | always (negative decision) |
| 009 | [Groq Cloud + open-source models over Anthropic / OpenAI APIs](adr/009-groq-over-anthropic-openai.md) | accepted | Week 1: pivot in commit `725e7db` |
| 010 | [Run persistence + read-only dashboard observability](adr/010-run-persistence-and-observability.md) | accepted | Week 3.1-3.2: `storage/`, `api/`, `web/` |

## How to use this index

- "accepted" = decision lived through at least one implementation cycle without being reversed.
- "planned" = decision will be written when the corresponding code lands; placeholder row here
  so reviewers know the gap is deliberate.
- Each ADR file is ~200 lines, self-contained, follows the template in
  [adr/000-template.md](adr/000-template.md): Context → Alternatives → Decision →
  Consequences → Verification.
- When code violates an ADR, the fix is either reverting the code or writing a superseding ADR
  (status `superseded by NNN`). Silently ignoring an ADR is a project-level bug.
