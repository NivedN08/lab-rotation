import { FAKE_TABLES } from "./fakeData";
import type { Cell } from "./types";

export type SqlResult = { columns: string[]; rows: Cell[][]; ms: number; offline: boolean; sql: string };

/**
 * Sends the query to the server's runner (POST /api/sql -> {columns, rows} or {error}).
 * Until that endpoint exists it falls back to a tiny in-browser stand-in over the fake tables,
 * and says so (offline: true). Throws Error with the message to show the user.
 */
export async function runSql(sql: string): Promise<SqlResult> {
  const t0 = performance.now();
  try {
    const res = await fetch("/api/sql", {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({ sql }),
    });
    if (res.status !== 404 && res.status !== 503 && (res.headers.get("content-type") ?? "").includes("json")) {
      const body = await res.json();
      if (!res.ok || body.error) throw new Error(body.error ?? `The runner returned ${res.status}.`);
      return { columns: body.columns, rows: body.rows, ms: Math.round(performance.now() - t0), offline: false, sql };
    }
  } catch (e) {
    if (e instanceof Error && !(e instanceof TypeError)) throw e;
  }
  const r = standIn(sql);
  return { ...r, ms: Math.round(performance.now() - t0), offline: true, sql };
}

function standIn(sql: string): { columns: string[]; rows: Cell[][] } {
  const m = sql
    .trim()
    .replace(/;\s*$/, "")
    .match(/^select\s+(.+?)\s+from\s+(\w+)(?:\s+where\s+(\w+)\s*(=|!=|>|<)\s*('?[^']*'?))?(?:\s+limit\s+(\d+))?$/is);
  if (!m) throw new Error('Practice mode understands only: SELECT <columns or *> FROM <table> [WHERE col = value] [LIMIT n].');
  const [, sel, tname, wcol, op, wval, lim] = m;
  const table = FAKE_TABLES.find((t) => t.name.toLowerCase() === tname.toLowerCase());
  if (!table) throw new Error(`No such table: ${tname}. Tables are ${FAKE_TABLES.map((t) => t.name).join(", ")}.`);
  const names = table.columns.map((c) => c.name);
  let rows = table.rows;
  if (wcol) {
    const i = names.indexOf(wcol);
    if (i < 0) throw new Error(`No such column: ${wcol} in ${table.name}.`);
    const v = wval.replace(/^'|'$/g, "");
    rows = rows.filter((r) => {
      const c = r[i];
      if (c === null) return false;
      if (op === "=") return String(c) === v;
      if (op === "!=") return String(c) !== v;
      return op === ">" ? Number(c) > Number(v) : Number(c) < Number(v);
    });
  }
  if (/^count\(\*\)$/i.test(sel.trim())) return { columns: ["count"], rows: [[rows.length]] };
  const cols = sel.trim() === "*" ? names : sel.split(",").map((s) => s.trim());
  const idx = cols.map((c) => {
    const i = names.indexOf(c);
    if (i < 0) throw new Error(`No such column: ${c} in ${table.name}.`);
    return i;
  });
  return { columns: cols, rows: rows.slice(0, lim ? Number(lim) : 200).map((r) => idx.map((i) => r[i])) };
}
