# ADR-002: Planner / Executor / Verifier split with Reflexion-style retries

**Status**: accepted — A/B measured 2026-05-26 on the trivial set; orchestrator lifts resolved@1 from 10 % to 80 % (+70 pp), well above the +10 pp kill criterion. Stays.
**Date**: 2026-05-26
**Deciders**: Álvaro

## Context

The Week-1 agent is one `Executor` running a tool loop until the model emits no further tool
calls or the inner cap is reached, then a sandboxed verify command decides success
(see [ADR-001](001-hand-rolled-tool-loop.md)). It hits 10/10 on the trivial issue set, but it
has three weaknesses that show up on harder benchmarks:

1. **No upfront plan.** The model figures out what to read and what to change inside the loop,
   which works on trivial issues but burns tokens on exploration when the bug is non-obvious.
2. **No second opinion.** When tests pass, we trust the model: but tests passing does not mean
   the diff is minimal, on-topic, or that the model didn't sneak through by modifying the test
   file. There is no defence against an agent that "succeeds" by cheating.
3. **No retry with reflection.** If the executor terminates without success, the harness
   accepts the failure. SWE-agent and similar systems get substantial lift from trying again
   with the previous failure summarised back into the prompt.

## Alternatives considered

1. **Keep Executor-only.** Simplest. Cheapest in tokens. Loses to (1)–(3) above.
2. **Planner + Executor only** (no Verifier). Adds upfront planning. Still no second opinion
   on the diff; no Reflexion loop possible because there is nobody to reject and re-issue.
3. **Executor + Verifier only**, no planner. Adds the gate but loses the structured upfront
   plan; relies on the executor's first tool call to figure out the workspace.
4. **Planner + Executor + Verifier with Reflexion loop** — full architecture. Most code, most
   token cost, closest to the papers below.
5. **Multi-agent debate** (multiple planners + voting) — overkill for trivial-fix tasks; pure
   token burn for marginal accuracy.

## Decision

Implement the full Planner → Executor → Verifier architecture with a Reflexion-style outer
loop. Behaviour:

1. **Planner** (one LLM call, `openai/gpt-oss-120b`): reads the task + a depth-first listing
   of the workspace, emits a JSON plan with three keys (`files_to_read`, `files_to_modify`,
   `steps`). See [`src/issue_to_pr/planner/`](../../src/issue_to_pr/planner/).
2. **Executor** (unchanged from ADR-001, `openai/gpt-oss-20b`): the plan is appended to the
   executor's task description as advisory context. The executor still runs the same tool
   loop and produces an `ExecutionResult`.
3. **Verifier** (one LLM call, `openai/gpt-oss-120b`): receives task + executor result +
   the current content of every file the executor wrote. Decides `approved` + `reasoning`
   + `feedback_for_executor`. Implementation short-circuits with `approved=False` when
   `verify_exit_code != 0` to avoid burning a judge call on a failure we already know about.
   See [`src/issue_to_pr/verifier/`](../../src/issue_to_pr/verifier/).
4. **Orchestrator** (one outer loop, capped at `max_reflexion_iterations=3` by default):
   plan once, then iterate `Execute → Verify → (if rejected) prepend feedback → re-execute`.
   See [`src/issue_to_pr/orchestrator.py`](../../src/issue_to_pr/orchestrator.py).

## Theoretical basis (M7 citations)

- **ReAct** — Yao et al., 2022, "ReAct: Synergizing Reasoning and Acting in Language Models".
  The inner tool loop already follows ReAct (interleaved thought + action).
- **Reflexion** — Shinn et al., 2023, "Reflexion: Language Agents with Verbal Reinforcement
  Learning". The outer Plan → Execute → Verify loop with feedback prepended to the next
  attempt is the verbal-RL idea applied at the agent-task level, not at the token level.
- **LLM-as-Judge** — Zheng et al., 2023, "Judging LLM-as-a-Judge with MT-Bench and Chatbot
  Arena". The Verifier is a constrained LLM-as-judge with a JSON output schema and a hard
  exit-code-zero precondition.

## Why each role gets the model it gets

See [ADR-004](004-multi-model-routing.md). Briefly: planner and verifier are 1-shot
reasoning calls where capability dominates throughput (gpt-oss-120b). Executor burns most of
the tokens in the tool loop, throughput dominates (gpt-oss-20b at 1000 tok/s).

## Consequences

**Easier**:
- Defendible in interview: every paper-named pattern (ReAct, Reflexion, LLM-as-Judge) is a
  separate file with a single responsibility, not buried inside a 500-line god-class.
- Adversarial defence: a verifier that re-reads the actual file contents (not the executor's
  arguments_json) catches "tests pass because I modified the test" cheating.
- Reflexion gives free retries that turn near-misses into wins on SWE-bench Lite without
  fine-tuning.

**Harder**:
- ~3× the LLM calls per task (planner once + executor N times + verifier N times). On the
  trivial set the baseline was ~9 k tokens / issue; orchestrator will be ~25–35 k / issue.
  Free tier daily quota (200 k) holds 5–8 orchestrated runs per day.
- More moving parts to debug. The orchestrator logs each iteration's `verify_exit_code`,
  `approved`, and `reasoning` to surface what's happening.
- The JSON contract for Planner / Verifier outputs is fragile. We picked permissive parsers
  (malformed JSON → empty plan / not-approved with retry) instead of crashing, but this is a
  source of silent failure modes that we will keep an eye on with logs.

**Accepted**:
- Token cost increase is real and documented. The expected lift in `resolved@1` on harder
  benchmarks (SWE-bench Lite) is what justifies it. If, at Week 4 measurement, the
  orchestrator does not improve `resolved@1` by at least 10 pp over Executor-only on the
  same SWE-bench Lite 50-subset, we revert this ADR — the complexity is not paying.

## Verification

- **Unit tests** (no API):
  - [`tests/unit/test_planner.py`](../../tests/unit/test_planner.py): JSON parsing, malformed
    JSON fallback, workspace listing, executor brief format.
  - [`tests/unit/test_verifier.py`](../../tests/unit/test_verifier.py): short-circuit on
    verify failure, JSON judging, file content surfaced to the judge.
  - [`tests/unit/test_orchestrator.py`](../../tests/unit/test_orchestrator.py): happy path
    (1 iter), Reflexion retry with feedback in the second executor call, cap at
    `max_reflexion_iterations`, token aggregation across retries.

- **End-to-end on Groq** (Week 2 eval gate, runs from `evals/runner.py`): the trivial set
  must hold `resolved@1 ≥ 0.70` with the orchestrator. CLI is the same:
  `uv run python -m evals.runner --set trivial` runs the orchestrator by default;
  `--executor-only` runs the Week-1 baseline.

- **A/B comparison** (Week 2, completed 2026-05-26): ran the trivial 10-issue set with
  `--executor-only` and with the default orchestrator. Same model in both arms
  (`openai/gpt-oss-120b` for executor + planner + verifier — the `gpt-oss-20b` TPD was
  saturated). Measured deltas:

| Metric | Baseline | Orchestrator | Δ |
|---|---|---|---|
| `resolved@1` | 1 / 10 (10 %) | 8 / 10 (80 %) | **+70 pp** |
| Prompt tokens | 24 535 | 99 593 | ×4.1 |
| Completion tokens | 1 580 | 5 763 | ×3.6 |
| Wall-clock | 116 s | 415 s | ×3.6 |

  Reflexion iteration distribution in the orchestrator's 8 successful runs:
  `reflexion=1` (planner-only assist) on 2 runs, `reflexion=2` on 5 runs (verifier
  rejected the first attempt, executor consumed the feedback, second attempt approved),
  `reflexion=3` on 1 run. The 2 unresolved cases (`007-mutable-default`,
  `008-division-by-zero`) hit `max_reflexion_iterations`: the verifier kept rejecting and
  the executor never produced a fix the verifier judged complete. Persisted as
  `eval_reports.id=1` (baseline) and `eval_reports.id=2` (orchestrator) in Postgres.

  **Decision**: the kill criterion was `Δresolved@1 < +10 pp`. The measured Δ is +70 pp,
  which clears it by a wide margin. The orchestrator stays in main and becomes the default
  path of the CLI runner and the runner.
