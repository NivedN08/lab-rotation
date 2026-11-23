import { useState } from "react";
import { Grid } from "./Grid";
import { runSql, useMock, type SqlResult } from "../api/client";
import { ROW_CAP } from "./TableBrowser";

const START = "SELECT * FROM samples WHERE batch = 'C' LIMIT 20";

export function SqlBox({ sessionId }: { sessionId: string }) {
  const [sql, setSql] = useState(START);
  const [state, setState] = useState<"idle" | "running" | "done" | "error">("idle");
  const [result, setResult] = useState<(SqlResult & { sql: string }) | null>(null);
  const [error, setError] = useState("");

  async function run() {
    if (!sql.trim() || state === "running") return;
    setState("running");
    try {
      setResult({ ...(await runSql(sessionId, sql)), sql });
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
          {useMock() && <p className="empty">Sample mode: the lab server isn't connected yet, so this answer is made up.</p>}
          {result.rows.length === 0 ? (
            <p className="empty">The query ran and returned no rows. ({result.ms} ms)</p>
          ) : (
            <>
              <Grid source="query" sql={result.sql} columns={result.columns.map((name) => ({ name }))} rows={rows} label="Query results" />
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
