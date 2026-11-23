import { useSyncExternalStore } from "react";
import type { Cell, EvidenceRef } from "../api/client";

/** One thing the learner cites, plus a key to tell items apart. */
export type Evidence = EvidenceRef & { key: string };

const STORE = "lab-rotation.workspace.evidence";
const NONE: Evidence[] = [];

function read(): Record<string, Evidence[]> {
  try {
    return JSON.parse(sessionStorage.getItem(STORE) ?? "{}");
  } catch {
    return {};
  }
}

// Evidence is kept per task: each task has its own list.
let all = read();
let scope = "";
const subs = new Set<() => void>();
const current = () => all[scope] ?? NONE;

function set(next: Evidence[]) {
  all = { ...all, [scope]: next };
  try {
    sessionStorage.setItem(STORE, JSON.stringify(all));
  } catch {
    /* storage blocked: keep it in memory */
  }
  subs.forEach((f) => f());
}

export const evidence = {
  /** Which task's list the picker reads and writes. */
  setTask(id: string) {
    if (id === scope) return;
    scope = id;
    subs.forEach((f) => f());
  },
  has: (key: string) => current().some((e) => e.key === key),
  toggle(e: Evidence) {
    set(current().some((x) => x.key === e.key) ? current().filter((x) => x.key !== e.key) : [...current(), e]);
  },
  remove: (key: string) => set(current().filter((x) => x.key !== key)),
  clear: () => set([]),
};

export function useEvidence(): Evidence[] {
  return useSyncExternalStore(
    (f) => {
      subs.add(f);
      return () => subs.delete(f);
    },
    current,
  );
}

export const show = (c: Cell) => (c === null ? "null" : String(c));
