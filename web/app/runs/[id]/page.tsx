import Link from "next/link";
import { notFound } from "next/navigation";
import {
  fetchRun,
  formatElapsed,
  formatTokens,
  type HistoryEntry,
  type StoredRun,
} from "@/lib/api";
import staticRuns from "@/data/runs.json";

export const dynamic = "force-static";

// Pre-render every known run id so the static export can serve /runs/[id]/ pages directly.
// In live (non-static) dev mode the API is the source of truth; this list is harmless then.
export async function generateStaticParams() {
  return (staticRuns.items as { id: number }[]).map((r) => ({ id: r.id.toString() }));
}

type Params = { id: string };

export default async function RunPage({ params }: { params: Promise<Params> }) {
  const { id: idStr } = await params;
  const runId = Number.parseInt(idStr, 10);
  if (!Number.isFinite(runId)) notFound();

  let run: StoredRun;
  try {
    run = await fetchRun(runId);
  } catch {
    notFound();
  }

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="mx-auto max-w-5xl px-6 py-10">
        <header className="mb-6">
          <p className="text-xs uppercase tracking-wider text-zinc-500">
            <Link href="/" className="hover:text-zinc-300 hover:underline">
              ← all runs
            </Link>
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">
            <span className="text-zinc-500">run #</span>
            {run.id} <span className="text-zinc-500">·</span>{" "}
            <span className="font-mono">{run.task_id}</span>
          </h1>
          <p className="mt-1 text-sm text-zinc-400">
            {run.mode} · {run.success ? "✓ resolved" : "✗ failed"} · verify exit{" "}
            <span className="font-mono">{run.verify_exit_code}</span>
          </p>
        </header>

        <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <KV label="executor iter" value={run.executor_iterations.toString()} />
          <KV label="reflexion iter" value={(run.reflexion_iterations ?? 1).toString()} />
          <KV
            label="tokens"
            value={formatTokens(run.prompt_tokens + run.completion_tokens)}
            hint={`p ${formatTokens(run.prompt_tokens)} · c ${formatTokens(run.completion_tokens)}`}
          />
          <KV label="time" value={formatElapsed(run.elapsed_seconds)} />
        </section>

        {run.mode === "orchestrator" ? (
          <>
            <Section title="Plan (from the planner agent)">
              <PlanView plan={run.plan} />
            </Section>
            {run.history.length > 0 ? (
              <Section title={`Reflexion timeline (${run.history.length} iteration${run.history.length === 1 ? "" : "s"})`}>
                <Timeline history={run.history} />
              </Section>
            ) : null}
            <Section title="Final verdict (from the verifier agent)">
              <VerdictView verdict={run.verdict} />
            </Section>
          </>
        ) : (
          <Section title="Executor-only run">
            <p className="text-sm text-zinc-400">
              Baseline mode — no planner or verifier was used for this run.
            </p>
          </Section>
        )}

        <Section title="Raw">
          <pre className="overflow-auto rounded-md bg-zinc-900 p-3 text-xs leading-relaxed text-zinc-300">
            {JSON.stringify(run, null, 2)}
          </pre>
        </Section>
      </div>
    </main>
  );
}

function KV({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
      <p className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-zinc-100">{value}</p>
      {hint ? <p className="mt-0.5 text-[10px] text-zinc-500">{hint}</p> : null}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="mb-3 text-lg font-medium text-zinc-200">{title}</h2>
      {children}
    </section>
  );
}

function PlanView({ plan }: { plan: Record<string, unknown> }) {
  const steps = Array.isArray(plan["steps"]) ? (plan["steps"] as string[]) : [];
  const filesToRead = Array.isArray(plan["files_to_read"]) ? (plan["files_to_read"] as string[]) : [];
  const filesToModify = Array.isArray(plan["files_to_modify"]) ? (plan["files_to_modify"] as string[]) : [];

  if (steps.length === 0 && filesToRead.length === 0 && filesToModify.length === 0) {
    return <p className="text-sm text-zinc-500">(empty plan)</p>;
  }
  return (
    <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 text-sm">
      {filesToRead.length > 0 ? (
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-500">files to read</p>
          <ul className="mt-1 list-disc pl-5 text-zinc-300">
            {filesToRead.map((f, i) => (
              <li key={i} className="font-mono">
                {f}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {filesToModify.length > 0 ? (
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-500">files to modify</p>
          <ul className="mt-1 list-disc pl-5 text-zinc-300">
            {filesToModify.map((f, i) => (
              <li key={i} className="font-mono">
                {f}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {steps.length > 0 ? (
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-500">steps</p>
          <ol className="mt-1 list-decimal pl-5 text-zinc-300">
            {steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  );
}

function Timeline({ history }: { history: HistoryEntry[] }) {
  return (
    <ol className="relative border-l border-zinc-800 pl-6">
      {history.map((entry, idx) => {
        const approved = entry.verdict.approved;
        const isLast = idx === history.length - 1;
        return (
          <li key={entry.iteration} className="mb-6 last:mb-0">
            <span
              className={`absolute -left-[7px] flex h-3 w-3 rounded-full border-2 border-zinc-950 ${
                approved ? "bg-emerald-500" : "bg-amber-500"
              }`}
            />
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
              <div className="flex items-center justify-between text-xs uppercase tracking-wider text-zinc-500">
                <span>iteration {entry.iteration}</span>
                <span>
                  {approved ? (
                    <span className="rounded bg-emerald-900/40 px-2 py-0.5 text-emerald-300">
                      verifier approved
                    </span>
                  ) : (
                    <span className="rounded bg-amber-900/40 px-2 py-0.5 text-amber-300">
                      retry — verifier rejected
                    </span>
                  )}
                </span>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                <Metric label="executor iter" value={entry.execution.executor_iterations.toString()} />
                <Metric label="tool calls" value={entry.execution.tool_calls_count.toString()} />
                <Metric
                  label="tokens"
                  value={formatTokens(entry.execution.prompt_tokens + entry.execution.completion_tokens)}
                />
                <Metric label="verify" value={entry.execution.verify_exit_code === 0 ? "exit 0" : `exit ${entry.execution.verify_exit_code}`} />
              </div>
              <p className="mt-3 text-sm text-zinc-300">
                <span className="text-zinc-500">verdict:</span> {entry.verdict.reasoning}
              </p>
              {!approved && entry.verdict.feedback_for_executor && !isLast ? (
                <p className="mt-2 rounded border border-amber-900/50 bg-amber-950/20 p-2 text-xs text-amber-200">
                  <span className="font-medium text-amber-300">↳ feedback to next attempt:</span>{" "}
                  {entry.verdict.feedback_for_executor}
                </p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded bg-zinc-950/40 px-2 py-1">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="font-mono text-zinc-200">{value}</div>
    </div>
  );
}

function VerdictView({ verdict }: { verdict: Record<string, unknown> }) {
  const approved = Boolean(verdict["approved"]);
  const reasoning = typeof verdict["reasoning"] === "string" ? (verdict["reasoning"] as string) : "";
  const feedback = typeof verdict["feedback_for_executor"] === "string" ? (verdict["feedback_for_executor"] as string) : "";

  return (
    <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 text-sm">
      <div>
        <p className="text-xs uppercase tracking-wider text-zinc-500">approved</p>
        <p className="mt-1">
          {approved ? (
            <span className="rounded-md bg-emerald-900/40 px-2 py-0.5 text-xs font-medium text-emerald-300">
              YES
            </span>
          ) : (
            <span className="rounded-md bg-red-900/40 px-2 py-0.5 text-xs font-medium text-red-300">
              NO
            </span>
          )}
        </p>
      </div>
      {reasoning ? (
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-500">reasoning</p>
          <p className="mt-1 text-zinc-300">{reasoning}</p>
        </div>
      ) : null}
      {!approved && feedback ? (
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-500">
            feedback for next executor attempt
          </p>
          <p className="mt-1 text-zinc-300">{feedback}</p>
        </div>
      ) : null}
    </div>
  );
}
