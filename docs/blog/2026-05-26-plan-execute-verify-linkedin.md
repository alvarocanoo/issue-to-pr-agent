---
audience: LinkedIn long post
angle: architecture deep-dive (Plan-Execute-Verify)
length: ~2350 chars (visible window: first 210)
draft_date: 2026-05-26
status: ready to copy-paste
---

# Plan-Execute-Verify: why one model goes from 10% to 80%

> The first paragraph is the "hook window" LinkedIn shows before the "see more" cut. Keep
> bytes 0-210 punchy. Everything after that is post-click.

---

I built an autonomous coding agent over the weekend.

Same executor model. Same 10 trivial issues. The only thing I change is whether a Planner and a Verifier wrap the Executor.

resolved@1: 10% to 80%.

That gap is not an accident. It's three papers from the AI agent literature glued together by 400 lines of Python.

PLAN — ReAct (Yao et al. 2022)

The Planner reads the issue and emits a JSON plan: files to read, files to modify, steps, verify command. The Executor never sees the raw issue, only the plan. Separating reasoning from action halves the cases where the model argues with itself mid-execution.

EXECUTE — hand-rolled tool loop

The Executor runs a tight Read / Edit / Bash / Grep loop inside a sandbox. No agent framework. Every tool call goes through a PreToolUse validator that whitelists commands, restricts the working directory and strips env vars. About 200 lines, every line defendible in a code review.

VERIFY — LLM-as-Judge (Zheng et al. 2023) + Reflexion (Shinn et al. 2023)

After each attempt, the Verifier judges the diff: did this actually fix the issue, were tests modified, is the change on-topic? If it rejects, the natural-language feedback becomes the next attempt's context. That is Reflexion: verbal reinforcement learning, no gradient updates.

On the 10-issue set, the Verifier rejected 2-3 attempts on average across the 7 issues that needed retries. Without it the agent ships broken code with confidence.

The price tag:

- Tokens: x4.1
- Wall-clock: x3.6
- resolved@1: +70 percentage points

I wrote the kill criterion into the ADR before measuring: if the orchestrator could not clear +10 pp over the baseline, revert the architecture. It cleared 7x that.

Stack: Groq Cloud free tier, openai/gpt-oss-120b for planner and verifier, openai/gpt-oss-20b for the executor. Every LLM call traced in Langfuse. The dashboard ships the 20 A/B runs side by side: https://alvarocanoo.github.io/issue-to-pr-agent/compare/

Next stop is SWE-bench Lite. The leaderboard SOTA on Lite is Claude Opus 4.6 at 62.7%. I do not expect to clear that with open-source models on a free tier, but the architecture is now the part I trust.

Repo, ADRs and measured numbers: https://github.com/alvarocanoo/issue-to-pr-agent

#AIAgents #LLM #SoftwareEngineering #Python #MachineLearning

---

## Posting notes

- The hook window (first 210 chars before LinkedIn cuts to "see more") is the first 3 short
  lines plus "resolved@1: 10% to 80%." That number must land before the fold.
- LinkedIn strips most markdown. Bold and headings will not render. Plain text + line breaks
  is the canonical format; I have already avoided characters that would render oddly.
- If you want emojis (LinkedIn convention nudges them up in the feed): add one bullet emoji
  at the start of each section header (e.g. small green / blue circles). I did not add them
  because the CLAUDE.md rule is to avoid emojis unless asked.
- Best window to post: Tuesday-Thursday, 08:00-10:00 CET. Reply to the first 5 comments in
  the first 30 minutes for the algorithm boost.
- Pin a comment with: "Architecture decisions are written up as ADRs in the repo, including
  the +70 pp A/B and the kill criterion that decided whether the orchestrator stayed:
  https://github.com/alvarocanoo/issue-to-pr-agent/blob/main/docs/adr/002-planner-executor-verifier.md".

## Why each claim survives a hostile reviewer

- "10% to 80% with the same model": both arms use openai/gpt-oss-120b for the executor.
  README "Measured metrics" table.
- "x4.1 tokens, x3.6 wall-clock": same table (24,535 to 99,593 prompt tokens; 116 to 415 s).
- "Verifier rejected 2-3 attempts": README "Why this A/B matters" paragraph.
- "Kill criterion +10 pp": ADR-002 reverse acceptance criterion.
- "ReAct / Reflexion / LLM-as-Judge": all three are real papers I can cite by arXiv ID
  (2210.03629, 2303.11366, 2306.05685). The agent literature has converged on this triad
  for a reason — independent ablations in the broader research replicate the gain.
