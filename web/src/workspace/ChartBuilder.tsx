import { useEffect, useState } from "react";
import { getRows, type TableInfo } from "../api/client";
import { bars, numericColumns, points, type Dataset, type Measure } from "./chartData";
import { useLastQuery } from "./lastQuery";

const MAX_ROWS = 500;
type Kind = "bar" | "scatter";

/** A column with a handful of different values makes the most readable bars. */
function groupColumn(d: Dataset): string {
  let best = d.columns[0] ?? "";
  let bestN = Infinity;
  d.columns.forEach((c, i) => {
    const n = new Set(d.rows.map((r) => r[i])).size;
    if (n > 1 && n <= 12 && n < bestN) {
      best = c;
      bestN = n;
    }
  });
  return best;
}

const fmt = (n: number) => (Math.abs(n) >= 100 ? String(Math.round(n)) : String(Math.round(n * 100) / 100));

export function ChartBuilder({ sessionId, taskId, tables }: { sessionId: string; taskId?: string; tables: TableInfo[] }) {
  const query = useLastQuery();
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState(tables[0]?.name ?? "");
  const [cache, setCache] = useState<Record<string, Dataset>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [kind, setKind] = useState<Kind>("bar");
  const [x, setX] = useState("");
  const [measure, setMeasure] = useState<Measure>("count");
  const [y, setY] = useState("");

  const useQuery = source === "query";
  const data: Dataset | null = useQuery ? (query ? { columns: query.columns, rows: query.rows } : null) : cache[source] ?? null;

  useEffect(() => {
    if (!open || useQuery || cache[source]) return;
    const t = tables.find((t) => t.name === source);
    if (!t) return;
    let live = true;
    setLoading(true);
    setError("");
    getRows(sessionId, t.name, 0, MAX_ROWS, taskId)
      .then((rows) => live && setCache((c) => ({ ...c, [source]: { columns: t.columns.map((c) => c.name), rows } })))
      .catch((e) => live && setError((e as Error).message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [open, source, useQuery]);

  // Pick sensible defaults whenever the data or chart type changes.
  useEffect(() => {
    if (!data) return;
    const nums = numericColumns(data);
    const xOptions = kind === "scatter" ? nums : data.columns;
    setX((cur) => (xOptions.includes(cur) ? cur : kind === "scatter" ? nums[0] ?? "" : groupColumn(data)));
    setY((cur) => (nums.includes(cur) ? cur : nums[1] ?? nums[0] ?? ""));
  }, [data, kind]);

  if (!open) {
    return (
      <button className="btn" onClick={() => setOpen(true)}>
        Open the chart builder
      </button>
    );
  }

  const nums = data ? numericColumns(data) : [];
  const b = data && kind === "bar" ? bars(data, x, measure, y) : [];
  const sc = data && kind === "scatter" ? points(data, x, y) : { points: [], skipped: 0 };
  const note = data && data.rows.length >= MAX_ROWS && !useQuery ? `Charting the first ${MAX_ROWS} rows.` : "";

  return (
    <section className="ws-chart box" aria-label="Chart builder">
      <div className="ws-tray-head">
        <h2 className="ws-title">Chart</h2>
        <button className="btn quiet" onClick={() => setOpen(false)}>
          Close
        </button>
      </div>

      <div className="ws-controls">
        <label className="ws-field">
          <span className="ws-legend">Data</span>
          <select className="ws-select" value={source} onChange={(e) => setSource(e.target.value)}>
            {tables.map((t) => (
              <option key={t.name} value={t.name}>
                {t.name}
              </option>
            ))}
            <option value="query">My last query</option>
          </select>
        </label>
        <label className="ws-field">
          <span className="ws-legend">Chart</span>
          <select className="ws-select" value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
            <option value="bar">Bars by group</option>
            <option value="scatter">Scatter of two numbers</option>
          </select>
        </label>
        {data && (
          <>
            <label className="ws-field">
              <span className="ws-legend">{kind === "bar" ? "Group by" : "Across (x)"}</span>
              <select className="ws-select" value={x} onChange={(e) => setX(e.target.value)}>
                {(kind === "scatter" ? nums : data.columns).map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            {kind === "bar" && (
              <label className="ws-field">
                <span className="ws-legend">Show</span>
                <select className="ws-select" value={measure} onChange={(e) => setMeasure(e.target.value as Measure)}>
                  <option value="count">Number of rows</option>
                  <option value="avg">Average of…</option>
                  <option value="sum">Total of…</option>
                </select>
              </label>
            )}
            {(kind === "scatter" || measure !== "count") && (
              <label className="ws-field">
                <span className="ws-legend">{kind === "scatter" ? "Up (y)" : "Column"}</span>
                <select className="ws-select" value={y} onChange={(e) => setY(e.target.value)}>
                  {nums.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
            )}
          </>
        )}
      </div>

      {loading && (
        <p className="empty" role="status">
          Loading rows…
        </p>
      )}
      {error && (
        <p className="ws-error" role="alert">
          {error}
        </p>
      )}
      {useQuery && !query && <p className="empty">Run a query in the SQL box first, then chart its result here.</p>}
      {data && data.rows.length === 0 && <p className="empty">There are no rows to chart.</p>}
      {data && kind === "scatter" && nums.length < 2 && <p className="empty">A scatter needs two columns of numbers, and this data has {nums.length}.</p>}

      {kind === "bar" && b.length > 0 && <BarChart bars={b} />}
      {kind === "scatter" && sc.points.length > 0 && <Scatter pts={sc.points} x={x} y={y} />}
      {(note || sc.skipped > 0) && (
        <p className="empty">
          {note} {sc.skipped > 0 ? `${sc.skipped} rows were left out because a number is missing.` : ""}
        </p>
      )}
    </section>
  );
}

function BarChart({ bars }: { bars: { label: string; value: number }[] }) {
  const max = Math.max(...bars.map((b) => b.value), 1e-9);
  return (
    <ul className="ws-bars" aria-label="Bar chart">
      {bars.map((b) => (
        <li key={b.label}>
          <span className="ws-bar-label" title={b.label}>
            {b.label}
          </span>
          <span className="ws-bar-track">
            <span className="ws-bar-fill" style={{ width: `${Math.max(0, (b.value / max) * 100)}%` }} />
          </span>
          <span className="ws-bar-n">{fmt(b.value)}</span>
        </li>
      ))}
    </ul>
  );
}

function Scatter({ pts, x, y }: { pts: { x: number; y: number }[]; x: string; y: string }) {
  const W = 360;
  const H = 220;
  const P = 34;
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  const sx = (v: number) => P + ((v - x0) / (x1 - x0 || 1)) * (W - P - 8);
  const sy = (v: number) => H - P - ((v - y0) / (y1 - y0 || 1)) * (H - P - 8);
  return (
    <svg className="ws-scatter" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Scatter of ${y} against ${x}`}>
      <path d={`M${P} 8V${H - P}H${W - 8}`} className="ws-axis" />
      {pts.map((p, i) => (
        <rect key={i} x={sx(p.x) - 1.5} y={sy(p.y) - 1.5} width="3" height="3" className="ws-dot" />
      ))}
      <text x={P} y={H - 8} className="ws-tick">
        {x} {fmt(x0)} to {fmt(x1)}
      </text>
      <text x={4} y={14} className="ws-tick">
        {y} {fmt(y1)}
      </text>
      <text x={4} y={H - P} className="ws-tick">
        {fmt(y0)}
      </text>
    </svg>
  );
}
