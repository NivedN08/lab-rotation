import type { Cell } from "../api/client";

export type Dataset = { columns: string[]; rows: Cell[][] };
export type Measure = "count" | "avg" | "sum";

export type Bar = { label: string; value: number };
export type Point = { x: number; y: number };

const num = (c: Cell): number | null => (typeof c === "number" && Number.isFinite(c) ? c : null);

/** Group rows by one column and count them, or average or sum another column. Largest groups first, capped. */
export function bars(d: Dataset, x: string, measure: Measure, y: string, cap = 12): Bar[] {
  const xi = d.columns.indexOf(x);
  const yi = d.columns.indexOf(y);
  if (xi < 0 || (measure !== "count" && yi < 0)) return [];
  const g = new Map<string, { n: number; sum: number }>();
  for (const r of d.rows) {
    const key = r[xi] === null ? "(missing)" : String(r[xi]);
    const e = g.get(key) ?? { n: 0, sum: 0 };
    if (measure === "count") e.n++;
    else {
      const v = num(r[yi]);
      if (v === null) continue;
      e.n++;
      e.sum += v;
    }
    g.set(key, e);
  }
  return [...g.entries()]
    .map(([label, e]) => ({ label, value: measure === "avg" ? e.sum / e.n : measure === "sum" ? e.sum : e.n }))
    .sort((a, b) => b.value - a.value)
    .slice(0, cap);
}

/** Pairs of numbers from two columns; rows where either is missing are left out. */
export function points(d: Dataset, x: string, y: string): { points: Point[]; skipped: number } {
  const xi = d.columns.indexOf(x);
  const yi = d.columns.indexOf(y);
  const out: Point[] = [];
  let skipped = 0;
  if (xi < 0 || yi < 0) return { points: out, skipped };
  for (const r of d.rows) {
    const a = num(r[xi]);
    const b = num(r[yi]);
    if (a === null || b === null) skipped++;
    else out.push({ x: a, y: b });
  }
  return { points: out, skipped };
}

export const numericColumns = (d: Dataset): string[] => d.columns.filter((_, i) => d.rows.some((r) => num(r[i]) !== null));
