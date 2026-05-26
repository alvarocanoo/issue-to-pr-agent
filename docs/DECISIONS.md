# Architecture Decision Records

Each ADR captures a non-obvious technical decision with the alternatives considered, the choice
made, and the reasoning. Written *after* implementing the component, so the rationale is real
and not aspirational.

| # | Title | Status | Lands in week |
|---|---|---|---|
| 000 | [Template](adr/000-template.md) | — | — |
| 001 | Hand-rolled tool loop over agent frameworks (LangChain / Agent SDK) | planned | 1 |
| 002 | Planner / Executor / Verifier split (ReAct + Reflexion + LLM-as-judge) | planned | 2 |
| 003 | Pluggable sandbox (LocalSubprocessRunner default, ContainerRunner opt-in) | planned | 1 |
| 004 | Multi-model routing on Groq (`gpt-oss-120b` planner+verifier, `gpt-oss-20b` executor) | planned | 4 |
| 005 | Langfuse self-hosted over Helicone / Phoenix / OpenTelemetry-only | planned | 3 |
| 006 | Postgres + JSONB over SQLite or a document DB | planned | 3 |
| 007 | SWE-bench Lite over Verified / full SWE-bench | planned | 4 |
| 008 | No fine-tuning: prompt + routing is the contract | planned | 5 |
| 009 | Groq Cloud + open-source models over Anthropic / OpenAI APIs | planned | 1 |
