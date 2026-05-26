import Link from "next/link";
import {
  fetchRunPairs,
  formatElapsed,
  formatTokens,
  formatUsd,
  type RunPair,
  type StoredRun,
} from "@/lib/api";

export const dynamic = "force-static";

export default async function ComparePage() {
  const pairs = await fetchRunPairs();
  const totals = aggregate(pairs);

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="mx-auto max-w-6xl px-6 py-10">
        <header className="mb-8">
          <p className="text-xs uppercase tracking-wider text-zinc-500">
            <Link href="/" className="hover:text-zinc-300 hover:underline">
              ← all runs
            </Link>
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">A/B comparison</h1>
          <p className="mt-2 text-sm text-zinc-400">
            Same 10 trivial issues, same executor model. The only difference between arms is
            whether the Planner / Verifier / Reflexion loop wraps the executor. Numbers are
            per-task; aggregate row at the bottom.
          </p>
        </header>

        <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Headline
            label="resolved@1"
            baseline={`${totals.baseline.solved}/${totals.baseline.total}`}
            orchestrator={`${totals.orchestrator.solved}/${totals.orchestrator.total}`}
            delta={`+${totals.deltaPp} pp`}
          />
          <Headline
            label="total tokens"
            baseline={formatTokens(totals.baseline.tokens)}
            orchestrator={formatTokens(totals.orchestrator.tokens)}
            delta={`×${ratio(totals.orchestrator.tokens, totals.baseline.tokens)}`}
            negative
          />
          <Headline
            label="wall-clock"
            baseline={formatElapsed(totals.baseline.elapsed)}
            orchestrator={formatElapsed(totals.orchestrator.elapsed)}
            delta={`×${ratio(totals.orchestrator.elapsed, totals.baseline.elapsed)}`}
            negative
          />
          <Headline
            label="est. cost"
            baseline={formatUsd(totals.baseline.cost)}
            orchestrator={formatUsd(totals.orchestrator.cost)}
            delta={`×${ratio(totals.orchestrator.cost, totals.baseline.cost)}`}
            negative
          />
        </section>

        <section className="mt-10">
          <h2 className="mb-3 text-lg font-medium text-zinc-200">Per-issue diff</h2>
          <div className="overflow-hidden rounded-lg border border-zinc-800">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900 text-xs uppercase tracking-wider text-zinc-400">
                <tr>
                  <th className="px-3 py-3 text-left" rowSpan={2}>
                    task
                  </th>
                  <th
                    className="border-l border-zinc-800 px-3 py-2 text-center text-zinc-300"
                    colSpan={4}
                  >
                    baseline (executor-only)
                  </th>
                  <th
                    className="border-l border-zinc-800 px-3 py-2 text-center text-emerald-300"
                    colSpan={5}
                  >
                    orchestrator (plan → exec → verify)
                  </th>
                  <th className="border-l border-zinc-800 px-3 py-3 text-center" rowSpan={2}>
                    Δ
                  </th>
                </tr>
                <tr>
                  <th className="border-l border-zinc-800 px-2 py-2 text-center">ok</th>
                  <th className="px-2 py-2 text-right">tokens</th>
                  <th className="px-2 py-2 text-right">cost</th>
                  <th className="px-2 py-2 text-right">time</th>
                  <th className="border-l border-zinc-800 px-2 py-2 text-center">ok</th>
                  <th className="px-2 py-2 text-right">refl</th>
                  <th className="px-2 py-2 text-right">tokens</th>
                  <th className="px-2 py-2 text-right">cost</th>
                  <th className="px-2 py-2 text-right">time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {pairs.map((p) => (
                  <Row key={p.task_id} pair={p} />
                ))}
              </tbody>
              <tfoot className="bg-zinc-900/60 text-xs tabular-nums text-zinc-300">
                <tr>
                  <td className="px-3 py-3 font-medium text-zinc-200">totals</td>
                  <td className="border-l border-zinc-800 px-2 py-3 text-center text-zinc-200">
                    {totals.baseline.solved}/{totals.baseline.total}
                  </td>
                  <td className="px-2 py-3 text-right">
                    {formatTokens(totals.baseline.tokens)}
                  </td>
                  <td className="px-2 py-3 text-right">{formatUsd(totals.baseline.cost)}</td>
                  <td className="px-2 py-3 text-right">
                    {formatElapsed(totals.baseline.elapsed)}
                  </td>
                  <td className="border-l border-zinc-800 px-2 py-3 text-center text-emerald-300">
                    {totals.orchestrator.solved}/{totals.orchestrator.total}
                  </td>
                  <td className="px-2 py-3 text-right">—</td>
                  <td className="px-2 py-3 text-right">
                    {formatTokens(totals.orchestrator.tokens)}
                  </td>
                  <td className="px-2 py-3 text-right">
                    {formatUsd(totals.orchestrator.cost)}
                  </td>
                  <td className="px-2 py-3 text-right">
                    {formatElapsed(totals.orchestrator.elapsed)}
                  </td>
                  <td className="border-l border-zinc-800 px-2 py-3 text-center text-emerald-300">
                    +{totals.deltaPp} pp
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </section>

        <section className="mt-10 rounded-lg border border-zinc-800 bg-zinc-900/40 p-5 text-sm leading-relaxed text-zinc-300">
          <h2 className="mb-2 text-base font-medium text-zinc-100">How to read this</h2>
          <ul className="list-disc space-y-1 pl-5 text-zinc-300">
            <li>
              <span className="text-emerald-300">Green ok</span> = verifier exit 0 + LLM-as-judge
              approved (orchestrator) or pytest exit 0 (baseline).
            </li>
            <li>
              <span className="text-zinc-200">refl</span> = how many Reflexion iterations were
              needed before the verifier approved. A value &gt; 1 means the verifier rejected
              at least one earlier attempt and fed the executor a correction.
            </li>
            <li>
              Token / cost / time ratios are deliberately worse for the orchestrator — that is
              the price paid for the +70 pp accuracy gain. Documented in{" "}
              <a
                href="https://github.com/alvarocanoo/issue-to-pr-agent/blob/main/docs/adr/002-planner-executor-verifier.md"
                target="_blank"
                rel="noreferrer"
                className="text-emerald-300 underline hover:text-emerald-200"
              >
                ADR-002
              </a>
              .
            </li>
          </ul>
        </section>
      </div>
    </main>
  );
}

function Row({ pair }: { pair: RunPair }) {
  const b = pair.baseline;
  const o = pair.orchestrator;
  const delta = computeDelta(b, o);
  return (
    <tr className="hover:bg-zinc-900/40">
      <td className="px-3 py-2 font-mono text-zinc-200">{pair.task_id}</td>
      <Side run={b} />
      <td className="border-l border-zinc-800 px-2 py-2 text-center">
        <Ok run={o} />
      </td>
      <td className="px-2 py-2 text-right tabular-nums text-zinc-400">
        {o ? (o.reflexion_iterations ?? "—") : "—"}
      </td>
      <td className="px-2 py-2 text-right tabular-nums text-zinc-300">
        {o ? (
          <Link
            href={`/runs/${o.id}`}
            className="underline-offset-2 hover:text-zinc-100 hover:underline"
          >
            {formatTokens(o.prompt_tokens + o.completion_tokens)}
          </Link>
        ) : (
          "—"
        )}
      </td>
      <td className="px-2 py-2 text-right tabular-nums text-zinc-400">
        {o ? formatUsd(o.estimated_cost_usd ?? 0) : "—"}
      </td>
      <td className="px-2 py-2 text-right tabular-nums text-zinc-400">
        {o ? formatElapsed(o.elapsed_seconds) : "—"}
      </td>
      <td className="border-l border-zinc-800 px-2 py-2 text-center">
        <DeltaCell delta={delta} />
      </td>
    </tr>
  );
}

function Side({ run }: { run: StoredRun | null }) {
  if (!run) {
    return (
      <>
        <td className="border-l border-zinc-800 px-2 py-2 text-center text-zinc-600">—</td>
        <td className="px-2 py-2 text-right text-zinc-600">—</td>
        <td className="px-2 py-2 text-right text-zinc-600">—</td>
        <td className="px-2 py-2 text-right text-zinc-600">—</td>
      </>
    );
  }
  return (
    <>
      <td className="border-l border-zinc-800 px-2 py-2 text-center">
        <Ok run={run} />
      </td>
      <td className="px-2 py-2 text-right tabular-nums text-zinc-300">
        <Link
          href={`/runs/${run.id}`}
          className="underline-offset-2 hover:text-zinc-100 hover:underline"
        >
          {formatTokens(run.prompt_tokens + run.completion_tokens)}
        </Link>
      </td>
      <td className="px-2 py-2 text-right tabular-nums text-zinc-400">
        {formatUsd(run.estimated_cost_usd ?? 0)}
      </td>
      <td className="px-2 py-2 text-right tabular-nums text-zinc-400">
        {formatElapsed(run.elapsed_seconds)}
      </td>
    </>
  );
}

function Ok({ run }: { run: StoredRun | null }) {
  if (!run) return <span className="text-zinc-600">—</span>;
  return run.success ? (
    <span className="rounded bg-emerald-900/40 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300">
      ✓
    </span>
  ) : (
    <span className="rounded bg-red-900/40 px-1.5 py-0.5 text-[10px] font-medium text-red-300">
      ✗
    </span>
  );
}

type DeltaKind = "fixed" | "kept" | "regressed" | "still-failed" | "missing";

function computeDelta(b: StoredRun | null, o: StoredRun | null): DeltaKind {
  if (!b || !o) return "missing";
  if (!b.success && o.success) return "fixed";
  if (b.success && o.success) return "kept";
  if (b.success && !o.success) return "regressed";
  return "still-failed";
}

function DeltaCell({ delta }: { delta: DeltaKind }) {
  switch (delta) {
    case "fixed":
      return (
        <span
          className="rounded bg-emerald-900/40 px-2 py-0.5 text-[10px] font-medium text-emerald-300"
          title="baseline failed, orchestrator resolved"
        >
          fixed
        </span>
      );
    case "kept":
      return (
        <span
          className="rounded bg-zinc-800 px-2 py-0.5 text-[10px] font-medium text-zinc-300"
          title="both arms resolved"
        >
          tie
        </span>
      );
    case "regressed":
      return (
        <span
          className="rounded bg-red-900/40 px-2 py-0.5 text-[10px] font-medium text-red-300"
          title="baseline resolved but orchestrator failed"
        >
          regressed
        </span>
      );
    case "still-failed":
      return (
        <span
          className="rounded bg-amber-900/40 px-2 py-0.5 text-[10px] font-medium text-amber-300"
          title="both arms failed"
        >
          both ✗
        </span>
      );
    default:
      return <span className="text-zinc-600">—</span>;
  }
}

type SideTotals = { solved: number; total: number; tokens: number; cost: number; elapsed: number };

function aggregate(pairs: RunPair[]): {
  baseline: SideTotals;
  orchestrator: SideTotals;
  deltaPp: string;
} {
  const baseline = sumSide(pairs.map((p) => p.baseline));
  const orchestrator = sumSide(pairs.map((p) => p.orchestrator));
  const baselinePct = baseline.total ? (baseline.solved / baseline.total) * 100 : 0;
  const orchPct = orchestrator.total ? (orchestrator.solved / orchestrator.total) * 100 : 0;
  return {
    baseline,
    orchestrator,
    deltaPp: (orchPct - baselinePct).toFixed(0),
  };
}

function sumSide(runs: (StoredRun | null)[]): SideTotals {
  const present = runs.filter((r): r is StoredRun => r !== null);
  return {
    solved: present.filter((r) => r.success).length,
    total: present.length,
    tokens: present.reduce((acc, r) => acc + r.prompt_tokens + r.completion_tokens, 0),
    cost: present.reduce((acc, r) => acc + (r.estimated_cost_usd ?? 0), 0),
    elapsed: present.reduce((acc, r) => acc + r.elapsed_seconds, 0),
  };
}

function ratio(num: number, denom: number): string {
  if (denom === 0) return "∞";
  return (num / denom).toFixed(1);
}

function Headline({
  label,
  baseline,
  orchestrator,
  delta,
  negative,
}: {
  label: string;
  baseline: string;
  orchestrator: string;
  delta: string;
  negative?: boolean;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <p className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</p>
      <div className="mt-2 flex items-baseline justify-between gap-2">
        <span className="text-sm tabular-nums text-zinc-400">{baseline}</span>
        <span className="text-zinc-600">→</span>
        <span className="text-base font-semibold tabular-nums text-zinc-100">
          {orchestrator}
        </span>
      </div>
      <p
        className={`mt-2 text-xs font-medium ${
          negative ? "text-amber-300" : "text-emerald-300"
        }`}
      >
        {delta}
      </p>
    </div>
  );
}
