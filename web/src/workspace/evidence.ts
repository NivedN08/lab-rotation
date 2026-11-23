import { useSyncExternalStore } from "react";
import type { Cell } from "./types";

/** One thing the learner cites: a whole row, a whole column, or a single cell. */
export type Evidence = {
  key: string;
  kind: "row" | "column" | "cell";
  /** Table name, or "query" for a SQL result. */
  source: string;
  /** The SQL that produced it, for query results. */
  sql?: string;
  row?: number; // 1-based
  column?: string;
  value?: Cell;
  /** Short plain-words description for the tray and the answer form. */
  label: string;
};

const STORE = "lab-rotation.workspace.evidence";

function read(): Evidence[] {
  try {
    return JSON.parse(sessionStorage.getItem(STORE) ?? "[]");
  } catch {
    return [];
  }
}

let items: Evidence[] = read();
const subs = new Set<() => void>();

function set(next: Evidence[]) {
  items = next;
  try {
    sessionStorage.setItem(STORE, JSON.stringify(items));
  } catch {
    /* storage blocked: keep it in memory */
  }
  subs.forEach((f) => f());
}

export const evidence = {
  has: (key: string) => items.some((e) => e.key === key),
  toggle(e: Evidence) {
    set(items.some((x) => x.key === e.key) ? items.filter((x) => x.key !== e.key) : [...items, e]);
  },
  remove: (key: string) => set(items.filter((x) => x.key !== key)),
  clear: () => set([]),
};

export function useEvidence(): Evidence[] {
  return useSyncExternalStore(
    (f) => {
      subs.add(f);
      return () => subs.delete(f);
    },
    () => items,
  );
}

export const show = (c: Cell) => (c === null ? "null" : String(c));
