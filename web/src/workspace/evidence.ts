import { useSyncExternalStore } from "react";
import type { Cell, EvidenceRef } from "../api/client";

/** One thing the learner cites, plus a key to tell items apart. */
export type Evidence = EvidenceRef & { key: string };

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
