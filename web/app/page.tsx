import Link from "next/link";
import { fetchRuns, fetchStats, formatElapsed, formatTokens, type StoredRun } from "@/lib/api";

// Static so the GitHub Pages export works; in `npm run dev` Next.js ignores this and
// re-renders on every request anyway, so the live mode keeps working locally.
export const dynamic = "force-static";

export default async function Home() {
  let runs: StoredRun[] = [];
  let stats: Awaited<ReturnType<typeof fetchStats>> | null = null;
  let error: string | null = null;
  try {
    const [statsRes, runsRes] = await Promise.all([fetchStats(), fetchRuns(50)]);
    stats = statsRes;
    runs = runsRes.items;
  } catch (e) {
    error = e instanceof Error ? e.message : "unknown error";
  }

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="mx-auto max-w-6xl px-6 py-10">
        <header className="mb-8">
          <h1 className="text-3xl font-semibold tracking-tight">issue-to-pr-agent</h1>
          <p className="mt-2 text-sm text-zinc-400">
            Autonomous coding agent over Groq Cloud. Hand-rolled tool loop, sandboxed
            execution, Planner / Executor / Verifier with Reflexion-style retries.
          </p>
          <p className="mt-1 text-xs text-zinc-500">
            <a
              className="underline hover:text-zinc-300"
              href="https://github.com/alvarocanoo/issue-to-pr-agent"
              target="_blank"
              rel="noreferrer"
            >
              source on GitHub
            </a>
          </p>
        </header>

        {error ? (
          <div className="rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm text-red-200">
            <p className="font-medium">Could not reach the agent API.</p>
            <p className="mt-1 text-red-300/80">{error}</p>
            <p className="mt-2 text-xs text-red-300/60">
              Start it locally:{" "}
              <code>uv run uvicorn issue_to_pr.api.server:app --port 8765</code>
            </p>
          </div>
        ) : null}

        {stats ? <StatsBar stats={stats} /> : null}

        <section className="mt-10">
          <h2 className="mb-3 text-lg font-medium text-zinc-200">Recent runs</h2>
          {runs.length === 0 ? <EmptyState /> : <RunsTable runs={runs} />}
        </section>
      </div>
    </main>
  );
}

function StatsBar({ stats }: { stats: Awaited<ReturnType<typeof fetchStats>> }) {
  const resolvedPct = (stats.resolved_at_1 * 100).toFixed(1);
  return (
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Stat
        label="resolved@1"
        value={`${resolvedPct}%`}
        hint={`${stats.solved} / ${stats.total_runs}`}
      />
      <Stat
        label="total runs"
        value={stats.total_runs.toString()}
        hint={Object.entries(stats.by_mode)
          .map(([k, v]) => `${k}:${v}`)
          .join(" · ")}
      />
      <Stat
        label="tokens"
        value={formatTokens(stats.total_prompt_tokens + stats.total_completion_tokens)}
        hint={`prompt ${formatTokens(stats.total_prompt_tokens)} · completion ${formatTokens(stats.total_completion_tokens)}`}
      />
      <Stat
        label="time"
        value={formatElapsed(stats.total_elapsed_seconds)}
        hint="cumulative"
      />
    </section>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <p className="text-xs uppercase tracking-wider text-zinc-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-zinc-100">{value}</p>
      {hint ? <p className="mt-1 text-xs text-zinc-500">{hint}</p> : null}
    </div>
  );
}

function RunsTable({ runs }: { runs: StoredRun[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-zinc-800">
      <table className="w-full text-sm">
        <thead className="bg-zinc-900 text-xs uppercase tracking-wider text-zinc-400">
          <tr>
            <th className="px-4 py-3 text-left">id</th>
            <th className="px-4 py-3 text-left">task</th>
            <th className="px-4 py-3 text-left">mode</th>
            <th className="px-4 py-3 text-left">success</th>
            <th className="px-4 py-3 text-right">iter</th>
            <th className="px-4 py-3 text-right">refl</th>
            <th className="px-4 py-3 text-right">tokens</th>
            <th className="px-4 py-3 text-right">time</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800">
          {runs.map((r) => (
            <tr key={r.id} className="hover:bg-zinc-900/50">
              <td className="px-4 py-2 text-zinc-500">
                <Link
                  href={`/runs/${r.id}`}
                  className="underline-offset-2 hover:text-zinc-100 hover:underline"
                >
                  #{r.id}
                </Link>
              </td>
              <td className="px-4 py-2 font-mono text-zinc-200">{r.task_id}</td>
              <td className="px-4 py-2 text-zinc-400">{r.mode}</td>
              <td className="px-4 py-2">
                <SuccessBadge ok={r.success} />
              </td>
              <td className="px-4 py-2 text-right tabular-nums text-zinc-300">
                {r.executor_iterations}
              </td>
              <td className="px-4 py-2 text-right tabular-nums text-zinc-400">
                {r.reflexion_iterations ?? "—"}
              </td>
              <td className="px-4 py-2 text-right tabular-nums text-zinc-300">
                {formatTokens(r.prompt_tokens + r.completion_tokens)}
              </td>
              <td className="px-4 py-2 text-right tabular-nums text-zinc-400">
                {formatElapsed(r.elapsed_seconds)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SuccessBadge({ ok }: { ok: boolean }) {
  if (ok) {
    return (
      <span className="rounded-md bg-emerald-900/40 px-2 py-0.5 text-xs font-medium text-emerald-300">
        resolved
      </span>
    );
  }
  return (
    <span className="rounded-md bg-red-900/40 px-2 py-0.5 text-xs font-medium text-red-300">
      failed
    </span>
  );
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-zinc-800 bg-zinc-900/30 p-10 text-center">
      <p className="text-zinc-400">No runs in the database yet.</p>
      <p className="mt-2 text-xs text-zinc-500">
        Persist a run with{" "}
        <code className="rounded bg-zinc-800 px-1.5 py-0.5">
          uv run python -m evals.runner --set trivial --persist
        </code>
      </p>
    </div>
  );
}
