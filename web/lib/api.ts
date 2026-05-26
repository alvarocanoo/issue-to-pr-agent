// Thin client over the FastAPI surface. Server- and client-callable.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765";

export type StoredRun = {
  id: number;
  task_id: string;
  mode: "executor" | "orchestrator";
  success: boolean;
  reflexion_iterations: number | null;
  executor_iterations: number;
  verify_exit_code: number;
  prompt_tokens: number;
  completion_tokens: number;
  elapsed_seconds: number;
  started_at: string;
  finished_at: string | null;
  plan: Record<string, unknown>;
  verdict: Record<string, unknown>;
};

export type Stats = {
  total_runs: number;
  solved: number;
  resolved_at_1: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_elapsed_seconds: number;
  by_mode: Record<string, number>;
};

async function jget<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${path} -> ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function fetchStats(): Promise<Stats> {
  return jget<Stats>("/stats");
}

export async function fetchRuns(limit = 50): Promise<{ items: StoredRun[]; count: number }> {
  return jget<{ items: StoredRun[]; count: number }>(`/runs?limit=${limit}`);
}

export async function fetchRun(id: number): Promise<StoredRun> {
  return jget<StoredRun>(`/runs/${id}`);
}

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toString();
}

export function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const rem = (seconds - minutes * 60).toFixed(0);
  return `${minutes}m ${rem}s`;
}
