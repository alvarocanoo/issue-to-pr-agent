# ADR-007: SWE-bench Lite over Verified and full SWE-bench

**Status**: planned (50-instance subset lands in Semana 4)
**Date**: 2026-05-26
**Deciders**: Álvaro

## Context

A coding agent demo without a recognised benchmark is unfalsifiable. The standard published
benchmark for "fix a real GitHub issue in a real Python project" is SWE-bench (Jimenez et al.,
2023, "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?"). It has three
public variants:

- **SWE-bench full** — 2 294 instances from 12 popular Python repositories.
- **SWE-bench Verified** — 500 instances, hand-curated by OpenAI as "definitely solvable by a
  competent human engineer", launched 2024.
- **SWE-bench Lite** — 300 instances filtered to easy-to-medium difficulty, no multi-file
  edits, smaller patch sizes.
- **SWE-bench Multimodal** — out of scope (needs screenshots).

Constraints in this project:
- Solo 4–6 week build. The benchmark must be runnable end-to-end in <6 h of CI time and
  fit within Groq free-tier daily token quota (200 k TPD).
- The result must be comparable against published numbers, not against our own synthetic eval.

## Alternatives considered

1. **SWE-bench full (2 294)** — most comprehensive. ~10–20 h compute per run on a budget
   model. With Groq free tier (200 k TPD), full eval would take >1 month to complete on
   quota alone. Discarded for solo budget.
2. **SWE-bench Verified (500)** — gold standard. Used by Anthropic/OpenAI/Cognition in their
   coding-agent papers. Still expensive: even at $0/run on Groq, 500 × ~15 k tokens ≈
   7.5 M tokens — many days of free tier, or a paid tier upgrade. Realistic only if we
   chunk the run across days.
3. **SWE-bench Lite (300)** — easy-to-medium subset, runs in 4–6 h on a single workflow,
   comparable to ~50% of published agent leaderboards (mini-SWE-agent, OpenHands, etc.).
   Fits our budget. Loses some discriminating power vs Verified.
4. **Build our own benchmark** — risky and unfalsifiable. Reviewers cannot compare numbers.
   Discarded.

## Decision

Run **a 50-instance subset of SWE-bench Lite** for the published number in the README, and
publish the full 300-instance run as an artifact once we've validated the harness on the
subset without burning the whole TPD quota in one day.

Subset selection rationale:
- 50 instances × ~15 k tokens ≈ 750 k tokens → fits across ~4 days of free tier.
- Picked to span the repos in Lite (django, flask, requests, sympy, ...) so the result is not
  one-project-skewed.
- Same `evals/runner.py` harness as the trivial set — only the YAML loader is replaced by a
  SWE-bench instance loader that materialises the buggy repo at the correct commit and runs
  the official `swe_bench` evaluation harness for verification.

The reference number to compare against (verified May 2026 on
[pricepertoken.com SWE-bench Lite leaderboard](https://pricepertoken.com/leaderboards/benchmark/swe-bench-lite)):
**Claude Opus 4.6 leads at 62.7%**. Open-source models on Groq are expected substantially
below — exact target lands when measured.

## Consequences

**Easier**:
- Subset fits in the daily quota and in CI's 6-hour budget.
- One harness handles trivial + Lite; SWE-bench's official Docker-based evaluator runs only
  on the verify step.
- The 50-instance subset is large enough that resolved@1 is not a coin flip but small enough
  to iterate on (re-run a single instance in <2 min).

**Harder**:
- 50 instances is small for statistical claims. We will report point estimates only, not
  confidence intervals.
- SWE-bench's official harness requires Docker for verification (each instance has a test
  Docker image). Our local dev without admin can't run it; CI on Ubuntu can. So SWE-bench
  evals are CI-only, not local — unlike the trivial set.

**Accepted**:
- We will likely score well below the leaderboard SOTA. The README will be honest about it
  ("resolved@1 X% with open-source gpt-oss-20b on a 50-subset, versus 62.7% SOTA Claude Opus
  4.6 on the full 300 — design trade-off documented in ADR-009").

## Verification

- Semana 4 implements the SWE-bench loader + run. The output is `eval-report-swe-lite.json`
  with the same shape as the trivial report.
- The published number replaces the "TBD" row in the README "Measured metrics" table.
- The 50-instance run also doubles as a regression gate for any Planner/Verifier changes
  (ADR-002): if a refactor drops resolved@1 by more than 5 pp on the same subset, the PR is
  rejected.
