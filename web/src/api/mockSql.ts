import type { Cell, Column } from "./types";

// A small stand-in for the server's SQL runner, used only in sample mode. It reads:
//   SELECT <columns | * | COUNT/AVG/SUM/MIN/MAX(col) [AS name]> FROM t [JOIN t2 USING (col)]
//   [WHERE col <op> value [AND ...]] [GROUP BY col] [ORDER BY col [DESC]] [LIMIT n]
// Anything else is refused with a plain message. The real server runs full SQL.

export type SqlTable = { name: string; columns: Pick<Column, "name">[]; rows: Cell[][] };
export type SqlOut = { columns: string[]; rows: Cell[][]; truncated: boolean };

const REFUSAL =
  "Sample mode can't run that one. It reads SELECT columns or COUNT, AVG, SUM, MIN, MAX of a column, FROM one table with an optional JOIN other USING (column), WHERE col = value, GROUP BY, ORDER BY and LIMIT. The real server runs full SQL.";

const SHAPE =
  /^select\s+(.+?)\s+from\s+(\w+)(?:\s+join\s+(\w+)\s+using\s*\(\s*(\w+)\s*\))?(?:\s+where\s+(.+?))?(?:\s+group\s+by\s+(\w+))?(?:\s+order\s+by\s+(\w+)(?:\s+(asc|desc))?)?(?:\s+limit\s+(\d+))?$/is;

const AGG = /^(count|avg|sum|min|max)\(\s*(\*|\w+)\s*\)$/i;
const round = (n: number) => Math.round(n * 100) / 100;

const cmp = (a: Cell, b: Cell) => (a === b ? 0 : a === null ? -1 : b === null ? 1 : a < b ? -1 : 1);

export function runMockSql(tables: SqlTable[], sql: string): SqlOut {
  const m = sql.trim().replace(/;\s*$/, "").match(SHAPE);
  if (!m) throw new Error(REFUSAL);
  const [, sel, tname, jname, jcol, where, groupBy, orderBy, dir, limit] = m;

  const find = (n: string) => {
    const t = tables.find((x) => x.name.toLowerCase() === n.toLowerCase());
    if (!t) throw new Error(`No such table: ${n}. Tables are ${tables.map((x) => x.name).join(", ")}.`);
    return t;
  };

  // FROM, with an optional inner JOIN ... USING (col).
  const left = find(tname);
  let names = left.columns.map((c) => c.name);
  let rows = left.rows;
  if (jname) {
    const right = find(jname);
    const li = names.indexOf(jcol);
    const rnames = right.columns.map((c) => c.name);
    const ri = rnames.indexOf(jcol);
    if (li < 0 || ri < 0) throw new Error(`No such column: ${jcol} (it must be in both ${left.name} and ${right.name}).`);
    const byKey = new Map<Cell, Cell[]>(right.rows.map((r) => [r[ri], r]));
    const extra = rnames.filter((_, i) => i !== ri);
    rows = rows.flatMap((r) => {
      const hit = byKey.get(r[li]);
      return hit ? [[...r, ...hit.filter((_, i) => i !== ri)]] : [];
    });
    names = [...names, ...extra];
  }
  const col = (n: string) => {
    const i = names.indexOf(n);
    if (i < 0) throw new Error(`No such column: ${n}.`);
    return i;
  };

  // WHERE: one or more `col op value` joined by AND.
  if (where) {
    const tests = where.split(/\s+and\s+/i).map((c) => {
      const w = c.trim().match(/^(\w+)\s*(=|!=|<>|>=|<=|>|<)\s*('?[^']*'?)$/);
      if (!w) throw new Error(REFUSAL);
      const i = col(w[1]);
      const v = w[3].replace(/^'|'$/g, "");
      return (r: Cell[]) => {
        const x = r[i];
        if (x === null) return false;
        switch (w[2]) {
          case "=": return String(x) === v;
          case "!=":
          case "<>": return String(x) !== v;
          case ">": return Number(x) > Number(v);
          case "<": return Number(x) < Number(v);
          case ">=": return Number(x) >= Number(v);
          default: return Number(x) <= Number(v);
        }
      };
    });
    rows = rows.filter((r) => tests.every((t) => t(r)));
  }

  // SELECT items.
  type Item = { name: string; agg?: { fn: string; col: number | "*" }; col?: number };
  const items: Item[] =
    sel.trim() === "*"
      ? names.map((n, i) => ({ name: n, col: i }))
      : sel.split(",").map((raw) => {
          const [expr, alias] = raw.trim().split(/\s+as\s+/i);
          const a = expr.trim().match(AGG);
          if (a) return { name: alias ?? `${a[1].toLowerCase()}(${a[2]})`, agg: { fn: a[1].toLowerCase(), col: a[2] === "*" ? "*" : col(a[2]) } } as Item;
          if (!/^\w+$/.test(expr.trim())) throw new Error(REFUSAL);
          return { name: alias ?? expr.trim(), col: col(expr.trim()) };
        });

  const hasAgg = items.some((i) => i.agg);
  const gcol = groupBy ? (groupBy === "1" ? (items[0].col ?? 0) : col(groupBy)) : null;
  if (!hasAgg && gcol !== null) throw new Error("GROUP BY needs a COUNT, AVG, SUM, MIN or MAX in the SELECT.");
  if (hasAgg && gcol === null && items.some((i) => !i.agg)) throw new Error("Mixing columns and totals needs a GROUP BY on that column.");

  const aggregate = (it: Item, g: Cell[][]): Cell => {
    const { fn, col: c } = it.agg!;
    if (c === "*") {
      if (fn !== "count") throw new Error(`${fn}(*) is not valid. Use a column name.`);
      return g.length;
    }
    const vals = g.map((r) => r[c]).filter((v): v is string | number | boolean => v !== null);
    const nums = vals.filter((v): v is number => typeof v === "number");
    if (fn === "count") return vals.length;
    if (!nums.length) return null;
    if (fn === "sum") return round(nums.reduce((x, y) => x + y, 0));
    if (fn === "avg") return round(nums.reduce((x, y) => x + y, 0) / nums.length);
    return fn === "min" ? Math.min(...nums) : Math.max(...nums);
  };

  let out: Cell[][];
  if (hasAgg) {
    const groups = new Map<Cell, Cell[][]>();
    for (const r of rows) {
      const k = gcol === null ? null : r[gcol];
      groups.set(k, [...(groups.get(k) ?? []), r]);
    }
    if (gcol === null && !groups.size) groups.set(null, []);
    out = [...groups.values()].map((g) => items.map((it) => (it.agg ? aggregate(it, g) : g[0]?.[it.col!] ?? null)));
    if (gcol !== null) out.sort((a, b) => cmp(a[items.findIndex((i) => !i.agg)] ?? null, b[items.findIndex((i) => !i.agg)] ?? null));
  } else {
    out = rows.map((r) => items.map((it) => r[it.col!]));
  }

  if (orderBy) {
    const oi = /^\d+$/.test(orderBy) ? Number(orderBy) - 1 : items.findIndex((i) => i.name === orderBy || names[i.col ?? -1] === orderBy);
    if (oi < 0 || oi >= items.length) throw new Error(`No such column to order by: ${orderBy}.`);
    out.sort((a, b) => cmp(a[oi], b[oi]) * (dir?.toLowerCase() === "desc" ? -1 : 1));
  }
  const cap = Math.min(limit ? Number(limit) : 500, 500);
  return { columns: items.map((i) => i.name), rows: out.slice(0, cap), truncated: !limit && out.length > 500 };
}
