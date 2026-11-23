import { useEffect, useState } from "react";
import { getTables, startSession, type SessionInfo, type TableInfo } from "../api/client";
import { EvidenceTray } from "./EvidenceTray";
import { SqlBox } from "./SqlBox";
import { TableBrowser } from "./TableBrowser";
import "./workspace.css";

type Props = { onTaskChange?: (running: boolean) => void };

export default function Workspace(_props: Props) {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [tables, setTables] = useState<TableInfo[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const s = await startSession();
        const t = await getTables(s.sessionId);
        if (live) {
          setSession(s);
          setTables(t);
        }
      } catch (e) {
        if (live) setError((e as Error).message);
      }
    })();
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="ws-root">
      <h2 className="ws-title">Tables</h2>
      {error ? (
        <p className="ws-error" role="alert">
          {error}
        </p>
      ) : session && tables ? (
        <>
          <TableBrowser sessionId={session.sessionId} tables={tables} />
          <SqlBox sessionId={session.sessionId} />
          <EvidenceTray />
        </>
      ) : (
        <p className="empty">Loading tables…</p>
      )}
    </div>
  );
}

export { Workspace };
