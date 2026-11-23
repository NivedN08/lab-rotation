import { useState } from "react";
import type { Table } from "./types";

export const ROW_CAP = 50;

export function TableBrowser({ tables }: { tables: Table[] }) {
  const [active, setActive] = useState(tables[0]?.name ?? "");
  const [shown, setShown] = useState<Record<string, number>>({});
  const table = tables.find((t) => t.name === active) ?? tables[0];
  if (!table) return <p className="empty">No tables to show.</p>;

  const cap = shown[table.name] ?? ROW_CAP;
  const rows = table.rows.slice(0, cap);

  return (
    <section className="ws-browser" aria-label="Table browser">
      <div className="tabs ws-tabs" role="tablist">
        {tables.map((t) => (
          <button key={t.name} className="tab" role="tab" aria-selected={t.name === table.name} onClick={() => setActive(t.name)}>
            {t.name}
            <span className="ws-count">{t.rows.length}</span>
          </button>
        ))}
      </div>
      <p className="empty ws-about">{table.about}</p>
      <div className="ws-grid-wrap" tabIndex={0} aria-label={`${table.name} rows`}>
        <table className="ws-grid">
          <thead>
            <tr>
              <th className="ws-rownum" scope="col">
                #
              </th>
              {table.columns.map((c) => (
                <th key={c.name} scope="col">
                  {c.name}
                  <span className="ws-type">{c.type}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                <td className="ws-rownum">{i + 1}</td>
                {row.map((cell, j) => (
                  <td key={j} className={cell === null ? "ws-null" : typeof cell === "number" ? "ws-num" : undefined}>
                    {cell === null ? "null" : String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="ws-foot">
        <span>
          Showing {rows.length} of {table.rows.length} rows
        </span>
        {cap < table.rows.length && (
          <button className="btn" onClick={() => setShown({ ...shown, [table.name]: cap + ROW_CAP })}>
            Show {Math.min(ROW_CAP, table.rows.length - cap)} more
          </button>
        )}
      </div>
    </section>
  );
}
