import { useEffect, useState } from "react";
import { getRows, type Cell, type TableInfo } from "../api/client";
import { Grid } from "./Grid";

export const ROW_CAP = 50;

type Loaded = { rows: Cell[][]; loading: boolean; error: string };

export function TableBrowser({ sessionId, tables }: { sessionId: string; tables: TableInfo[] }) {
  const [active, setActive] = useState(tables[0]?.name ?? "");
  const [loaded, setLoaded] = useState<Record<string, Loaded>>({});
  const table = tables.find((t) => t.name === active) ?? tables[0];
  const cur = table ? loaded[table.name] : undefined;

  async function more(t: TableInfo) {
    const have = loaded[t.name]?.rows ?? [];
    setLoaded((l) => ({ ...l, [t.name]: { rows: have, loading: true, error: "" } }));
    try {
      const rows = await getRows(sessionId, t.name, have.length, ROW_CAP);
      setLoaded((l) => ({ ...l, [t.name]: { rows: [...have, ...rows], loading: false, error: "" } }));
    } catch (e) {
      setLoaded((l) => ({ ...l, [t.name]: { rows: have, loading: false, error: (e as Error).message } }));
    }
  }

  useEffect(() => {
    if (table && !loaded[table.name]) more(table);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [table?.name]);

  if (!table) return <p className="empty">No tables to show.</p>;
  const rows = cur?.rows ?? [];

  return (
    <section className="ws-browser" aria-label="Table browser">
      <div className="tabs ws-tabs" role="tablist">
        {tables.map((t) => (
          <button key={t.name} className="tab" role="tab" aria-selected={t.name === table.name} onClick={() => setActive(t.name)}>
            {t.name}
            <span className="ws-count">{t.rowCount}</span>
          </button>
        ))}
      </div>
      <p className="empty ws-about">{table.about}</p>
      {rows.length > 0 && <Grid source={table.name} columns={table.columns} rows={rows} label={`${table.name} rows`} />}
      {cur?.error && (
        <p className="ws-error" role="alert">
          {cur.error}
        </p>
      )}
      <div className="ws-foot">
        <span>{cur?.loading && rows.length === 0 ? "Loading rows…" : `Showing ${rows.length} of ${table.rowCount} rows`}</span>
        {rows.length < table.rowCount && rows.length > 0 && (
          <button className="btn" disabled={cur?.loading} onClick={() => more(table)}>
            {cur?.loading ? "Loading…" : `Show ${Math.min(ROW_CAP, table.rowCount - rows.length)} more`}
          </button>
        )}
        {cur?.error && rows.length === 0 && (
          <button className="btn" onClick={() => more(table)}>
            Try again
          </button>
        )}
      </div>
    </section>
  );
}
