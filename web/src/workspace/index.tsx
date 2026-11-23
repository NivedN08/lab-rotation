import { useEffect, useLayoutEffect, useState } from "react";
import { getTables, rotation, useRotation, type TableInfo } from "../api/client";
import { AnswerForm } from "./AnswerForm";
import { EvidenceTray } from "./EvidenceTray";
import { evidence } from "./evidence";
import { SqlBox } from "./SqlBox";
import { TableBrowser } from "./TableBrowser";
import { Timer } from "./Timer";
import "./workspace.css";

type Props = { onTaskChange?: (running: boolean) => void };

/** Reads the one shared rotation state (session, current task, clock, poll) and shows the panel for it. */
export default function Workspace({ onTaskChange }: Props) {
  const { sessionId, current: task, startedAt, awaitingNext, error: startError } = useRotation();
  const [tables, setTables] = useState<TableInfo[] | null>(null);
  const [tablesError, setTablesError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!sessionId) return;
    let live = true;
    setTablesError("");
    getTables(sessionId)
      .then((t) => live && setTables(t))
      .catch((e) => live && setTablesError((e as Error).message));
    return () => {
      live = false;
    };
  }, [sessionId, attempt]);

  // The side panel widens while a task is running.
  useEffect(() => {
    onTaskChange?.(!!task);
    return () => onTaskChange?.(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [!!task]);

  // Each task has its own evidence list.
  useLayoutEffect(() => {
    evidence.setTask(task?.id ?? "");
  }, [task?.id]);

  const error = startError || tablesError;

  return (
    <div className="ws-root">
      {error ? (
        <div className="ws-state" role="alert">
          <p className="ws-error">{error}</p>
          <button className="btn" onClick={() => (startError ? rotation.retry() : setAttempt((n) => n + 1))}>
            Try again
          </button>
        </div>
      ) : !sessionId || !tables ? (
        <div className="ws-state" role="status" aria-label="Loading the workspace">
          <div className="ws-skel" style={{ width: "40%" }} />
          <div className="ws-skel" style={{ width: "90%" }} />
          <div className="ws-skel tall" />
          <p className="empty">Loading your task and the tables…</p>
        </div>
      ) : !task || !startedAt ? (
        <p className="ws-sent" role="status">
          That was the last task. Nice work.
        </p>
      ) : (
        <>
          <div className="ws-task" key={`brief-${task.id}`}>
            <div className="ws-task-head">
              <h2 className="ws-title">{task.title}</h2>
              <Timer startedAt={startedAt} seconds={task.seconds} />
            </div>
            <p className="ws-brief">{task.brief}</p>
          </div>
          <TableBrowser sessionId={sessionId} tables={tables} />
          <SqlBox key={`sql-${task.id}`} sessionId={sessionId} />
          <EvidenceTray />
          <AnswerForm key={task.id} sessionId={sessionId} task={task} onSent={rotation.answerSent} />
          {awaitingNext && (
            <p className="empty" role="status">
              Waiting for the next task…
            </p>
          )}
        </>
      )}
    </div>
  );
}

export { Workspace };
