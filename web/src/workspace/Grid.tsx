import { evidence, show, useEvidence, type Evidence } from "./evidence";
import type { Cell } from "../api/client";

type Props = {
  /** Table name, or "query" for a SQL result. Cited evidence is tagged with it. */
  source: string;
  sql?: string;
  columns: { name: string; type?: string; about?: string }[];
  rows: Cell[][];
  label: string;
  /**
   * How many table rows come before the first row given. Table rows are numbered from the table's first row
   * (1-based, absolute); a SQL result is numbered within itself, so leave this at 0 there.
   */
  rowOffset?: number;
  /** When given, each column header gets a button that opens that column's profile. */
  onProfile?: (column: string) => void;
  profiled?: string;
};

/** A table whose rows, columns and cells can be clicked to cite them as evidence. */
export function Grid({ source, sql, columns, rows, label, rowOffset = 0, onProfile, profiled }: Props) {
  const rowNo = (i: number) => i + 1 + rowOffset;
  const cited = new Set(useEvidence().filter((e) => e.source === source && e.sql === sql).map((e) => e.key));
  const base = { source, sql };
  const k = (kind: string, row?: number, col?: string) => `${source}|${sql ?? ""}|${kind}|${row ?? ""}|${col ?? ""}`;

  const citeRow = (i: number): Evidence => ({
    ...base,
    key: k("row", rowNo(i)),
    kind: "row",
    row: rowNo(i),
    label: `${source}, row ${rowNo(i)} (${rows[i].slice(0, 3).map(show).join(", ")}${columns.length > 3 ? ", …" : ""})`,
  });
  const citeColumn = (name: string): Evidence => ({ ...base, key: k("column", undefined, name), kind: "column", column: name, label: `${source}, column ${name}` });
  const citeCell = (i: number, j: number): Evidence => ({
    ...base,
    key: k("cell", rowNo(i), columns[j].name),
    kind: "cell",
    row: rowNo(i),
    column: columns[j].name,
    value: rows[i][j],
    label: `${source}, row ${rowNo(i)}, ${columns[j].name} = ${show(rows[i][j])}`,
  });

  return (
    <div className="ws-grid-wrap" tabIndex={0} aria-label={label}>
      <table className="ws-grid ws-pick">
        <thead>
          <tr>
            <th className="ws-rownum" scope="col">
              #
            </th>
            {columns.map((c) => (
              <th key={c.name} scope="col" className={cited.has(k("column", undefined, c.name)) ? "ws-cited" : undefined}>
                <button
                  className="ws-hit"
                  aria-pressed={cited.has(k("column", undefined, c.name))}
                  title={c.about ? `${c.about}. Click to cite this column.` : "Cite this column"}
                  onClick={() => evidence.toggle(citeColumn(c.name))}
                >
                  {c.name}
                </button>
                {c.type && <span className="ws-type">{c.type}</span>}
                {onProfile && (
                  <button
                    className="ws-prof"
                    aria-pressed={profiled === c.name}
                    aria-label={`Profile of ${c.name}`}
                    title="Profile this column"
                    onClick={() => onProfile(c.name)}
                  >
                    <svg width="12" height="12" viewBox="0 0 6 6" shapeRendering="crispEdges" aria-hidden="true">
                      <path d="M0 3h1v3H0zM2 1h1v5H2zM4 2h1v4H4z" fill="currentColor" />
                    </svg>
                  </button>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const rowOn = cited.has(k("row", rowNo(i)));
            return (
              <tr key={i} className={rowOn ? "ws-cited" : undefined}>
                <td className="ws-rownum">
                  <button className="ws-hit" aria-pressed={rowOn} title="Cite this row" aria-label={`Cite row ${rowNo(i)}`} onClick={() => evidence.toggle(citeRow(i))}>
                    {rowNo(i)}
                  </button>
                </td>
                {row.map((cell, j) => {
                  const on = cited.has(k("cell", rowNo(i), columns[j].name));
                  const cls = [cell === null ? "ws-null" : typeof cell === "number" ? "ws-num" : "", on ? "ws-cited" : "", "ws-cell"].filter(Boolean).join(" ");
                  return (
                    <td
                      key={j}
                      className={cls}
                      tabIndex={0}
                      aria-selected={on}
                      title="Cite this cell"
                      onClick={() => evidence.toggle(citeCell(i, j))}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          evidence.toggle(citeCell(i, j));
                        }
                      }}
                    >
                      {show(cell)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
