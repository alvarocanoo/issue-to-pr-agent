// Thin client over the FastAPI surface, with a build-time static fallback.
//
// In production on Vercel we don't host the FastAPI server, so we bake the most recent A/B
// measurement into the bundle as static JSON. Set NEXT_PUBLIC_USE_STATIC=true to use that
// embedded snapshot (the default for the public demo).
//
// For local dev, leave NEXT_PUBLIC_USE_STATIC unset and the client falls back to the live
// FastAPI server at NEXT_PUBLIC_API_BASE.

import staticRuns from "@/data/runs.json";
import staticStats from "@/data/stats.json";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765";
const USE_STATIC = process.env.NEXT_PUBLIC_USE_STATIC === "true";

export type HistoryEntry = {
  iteration: number;
  execution: {
    executor_iterations: number;
    exit_reason: string;
    tool_calls_count: number;
    prompt_tokens: number;
    completion_tokens: number;
    elapsed_seconds: number;
    verify_exit_code: number;
  };
  verdict: {
    approved: boolean;
    reasoning: string;
    feedback_for_executor: string | null;
  };
};

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
  estimated_cost_usd: number;
  elapsed_seconds: number;
  started_at: string;
  finished_at: string | null;
  plan: Record<string, unknown>;
  verdict: Record<string, unknown>;
  history: HistoryEntry[];
  langfuse_trace_url?: string | null;
};

export type Stats = {
  total_runs: number;
  solved: number;
  resolved_at_1: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_estimated_cost_usd: number;
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
  if (USE_STATIC) return staticStats as Stats;
  return jget<Stats>("/stats");
}

export async function fetchRuns(limit = 50): Promise<{ items: StoredRun[]; count: number }> {
  if (USE_STATIC) {
    const items = (staticRuns.items as StoredRun[]).slice(0, limit);
    return { items, count: staticRuns.count };
  }
  return jget<{ items: StoredRun[]; count: number }>(`/runs?limit=${limit}`);
}

export async function fetchRun(id: number): Promise<StoredRun> {
  if (USE_STATIC) {
    const found = (staticRuns.items as StoredRun[]).find((r) => r.id === id);
    if (!found) {
      throw new Error(`run ${id} not found in static data`);
    }
    return found;
  }
  return jget<StoredRun>(`/runs/${id}`);
}

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toString();
}

export function formatUsd(n: number): string {
  if (n >= 1) return `$${n.toFixed(2)}`;
  if (n >= 0.01) return `$${n.toFixed(3)}`;
  if (n >= 0.0001) return `$${n.toFixed(4)}`;
  return `$${n.toExponential(1)}`;
}

export function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const rem = (seconds - minutes * 60).toFixed(0);
  return `${minutes}m ${rem}s`;
}
