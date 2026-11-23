import { useSyncExternalStore } from "react";
import type { Cell } from "../api/client";

/** The most recent successful SQL result, so the chart builder can use it. */
export type QueryData = { sql: string; columns: string[]; rows: Cell[][] };

let last: QueryData | null = null;
const subs = new Set<() => void>();

export const lastQuery = {
  set(q: QueryData | null) {
    last = q;
    subs.forEach((f) => f());
  },
};

export const useLastQuery = (): QueryData | null =>
  useSyncExternalStore(
    (f) => {
      subs.add(f);
      return () => subs.delete(f);
    },
    () => last,
  );
