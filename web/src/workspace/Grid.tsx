import { evidence, show, useEvidence, type Evidence } from "./evidence";
import type { Cell } from "./types";

type Props = {
  /** Table name, or "query" for a SQL result. Cited evidence is tagged with it. */
  source: string;
  sql?: string;
  columns: { name: string; type?: string }[];
  rows: Cell[][];
  label: string;
};

/** A table whose rows, columns and cells can be clicked to cite them as evidence. */
export function Grid({ source, sql, columns, rows, label }: Props) {
  const cited = new Set(useEvidence().filter((e) => e.source === source && e.sql === sql).map((e) => e.key));
  const base = { source, sql };
  const k = (kind: string, row?: number, col?: string) => `${source}|${sql ?? ""}|${kind}|${row ?? ""}|${col ?? ""}`;

  const citeRow = (i: number): Evidence => ({
    ...base,
    key: k("row", i + 1),
    kind: "row",
    row: i + 1,
    label: `${source}, row ${i + 1} (${rows[i].slice(0, 3).map(show).join(", ")}${columns.length > 3 ? ", …" : ""})`,
  });
  const citeColumn = (name: string): Evidence => ({ ...base, key: k("column", undefined, name), kind: "column", column: name, label: `${source}, column ${name}` });
  const citeCell = (i: number, j: number): Evidence => ({
    ...base,
    key: k("cell", i + 1, columns[j].name),
    kind: "cell",
    row: i + 1,
    column: columns[j].name,
    value: rows[i][j],
    label: `${source}, row ${i + 1}, ${columns[j].name} = ${show(rows[i][j])}`,
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
                  title="Cite this column"
                  onClick={() => evidence.toggle(citeColumn(c.name))}
                >
                  {c.name}
                </button>
                {c.type && <span className="ws-type">{c.type}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const rowOn = cited.has(k("row", i + 1));
            return (
              <tr key={i} className={rowOn ? "ws-cited" : undefined}>
                <td className="ws-rownum">
                  <button className="ws-hit" aria-pressed={rowOn} title="Cite this row" aria-label={`Cite row ${i + 1}`} onClick={() => evidence.toggle(citeRow(i))}>
                    {i + 1}
                  </button>
                </td>
                {row.map((cell, j) => {
                  const on = cited.has(k("cell", i + 1, columns[j].name));
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
