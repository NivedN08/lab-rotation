import { useEffect, useState } from "react";
import { getTables, startSession, type SessionInfo, type TableInfo } from "../api/client";
import { AnswerForm } from "./AnswerForm";
import { EvidenceTray } from "./EvidenceTray";
import { SqlBox } from "./SqlBox";
import { TableBrowser } from "./TableBrowser";
import "./workspace.css";

type Props = { onTaskChange?: (running: boolean) => void };

export default function Workspace(_props: Props) {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [tables, setTables] = useState<TableInfo[] | null>(null);
  const [error, setError] = useState("");
  const [taskId, setTaskId] = useState("");

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

  const task = session?.tasks.find((t) => t.id === taskId) ?? session?.tasks[0];

  return (
    <div className="ws-root">
      <h2 className="ws-title">Tables</h2>
      {error ? (
        <p className="ws-error" role="alert">
          {error}
        </p>
      ) : session && tables ? (
        <>
          {task && (
            <>
              <div className="ws-tasks" role="group" aria-label="Task">
                {session.tasks.map((t) => (
                  <button key={t.id} className="chip" aria-pressed={t.id === task.id} onClick={() => setTaskId(t.id)}>
                    {t.title}
                  </button>
                ))}
              </div>
              <p className="empty ws-brief">{task.brief}</p>
            </>
          )}
          <TableBrowser sessionId={session.sessionId} tables={tables} />
          <SqlBox sessionId={session.sessionId} />
          <EvidenceTray />
          {task && <AnswerForm key={task.id} sessionId={session.sessionId} task={task} />}
        </>
      ) : (
        <p className="empty">Loading tables…</p>
      )}
    </div>
  );
}

export { Workspace };
