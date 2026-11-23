// Runs come from the Python server when it is running (it also sees runs still in progress),
// otherwise from the files baked into public/runs.

import type { Run, RunIndexItem } from "./types";

export type Source = { server: boolean; runs: RunIndexItem[] };

export async function listRuns(): Promise<Source> {
  try {
    const res = await fetch("/api/runs", { headers: { accept: "application/json" } });
    if (res.ok && (res.headers.get("content-type") ?? "").includes("json")) {
      const runs = (await res.json()) as RunIndexItem[];
      if (Array.isArray(runs) && runs.length) return { server: true, runs: order(runs) };
    }
  } catch {
    /* no server: fall through to the baked files */
  }
  const res = await fetch("./runs/index.json");
  return { server: false, runs: order(await res.json()) };
}

export async function loadRun(name: string, server: boolean): Promise<Run> {
  const res = await fetch(server ? `/api/run/${encodeURIComponent(name)}` : `./runs/${encodeURIComponent(name)}.json`);
  if (!res.ok) throw new Error(`Could not load run ${name} (${res.status})`);
  return res.json();
}

/** The recorded demo clip (public/runs/demo.json, written by make_demo.py), or null when there is none. */
export type Demo = {
  run: string;
  label: string;
  start: number;
  end: number;
  minutes: number;
  speed: number;
  mode: "busiest" | "last";
  ends_with_results: boolean;
  score?: number;
  interactions?: Record<string, number>;
  chosen?: string;
};

export async function loadDemo(): Promise<Demo | null> {
  try {
    const res = await fetch("./runs/demo.json");
    if (!res.ok || !(res.headers.get("content-type") ?? "").includes("json")) return null;
    return (await res.json()) as Demo;
  } catch {
    return null;
  }
}

/** Live runs first, then the test run, then the rest by start time, newest first. */
function order(runs: RunIndexItem[]) {
  return [...runs].sort((a, b) => Number(!!b.live) - Number(!!a.live) || Number(b.run === "test-v2") - Number(a.run === "test-v2") || b.started.localeCompare(a.started));
}
