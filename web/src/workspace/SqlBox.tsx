import { useState } from "react";
import { runSql, type SqlResult } from "./runSql";
import { ROW_CAP } from "./TableBrowser";

const START = "SELECT * FROM samples WHERE batch = 'C' LIMIT 20";

export function SqlBox() {
  const [sql, setSql] = useState(START);
  const [state, setState] = useState<"idle" | "running" | "done" | "error">("idle");
  const [result, setResult] = useState<SqlResult | null>(null);
  const [error, setError] = useState("");

  async function run() {
    if (!sql.trim() || state === "running") return;
    setState("running");
    try {
      setResult(await runSql(sql));
      setState("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setState("error");
    }
  }

  const rows = result?.rows.slice(0, ROW_CAP) ?? [];

  return (
    <section className="ws-sql" aria-label="SQL box">
      <h2 className="ws-title">SQL</h2>
      <textarea
        className="ws-editor"
        value={sql}
        spellCheck={false}
        rows={4}
        aria-label="SQL query"
        onChange={(e) => setSql(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") run();
        }}
      />
      <div className="ws-foot">
        <span>{state === "running" ? "Running…" : "Cmd or Ctrl + Enter runs it"}</span>
        <button className="btn gold" onClick={run} disabled={state === "running" || !sql.trim()}>
          Run
        </button>
      </div>
      {state === "error" && (
        <p className="ws-error" role="alert">
          {error}
        </p>
      )}
      {state === "done" && result && (
        <>
          {result.offline && <p className="empty">Practice mode: the server's SQL runner isn't connected yet, so this ran on sample data in your browser.</p>}
          {result.rows.length === 0 ? (
            <p className="empty">The query ran and returned no rows. ({result.ms} ms)</p>
          ) : (
            <>
              <div className="ws-grid-wrap" tabIndex={0} aria-label="Query results">
                <table className="ws-grid">
                  <thead>
                    <tr>
                      <th className="ws-rownum" scope="col">
                        #
                      </th>
                      {result.columns.map((c) => (
                        <th key={c} scope="col">
                          {c}
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
              <p className="empty">
                {result.rows.length} row{result.rows.length === 1 ? "" : "s"} in {result.ms} ms
                {result.rows.length > ROW_CAP ? `, showing the first ${ROW_CAP}` : ""}
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
