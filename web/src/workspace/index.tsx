import { useEffect, useLayoutEffect, useState } from "react";
import { getCurrentTask, getTables, startSession, type TableInfo, type TaskInfo } from "../api/client";
import { AnswerForm } from "./AnswerForm";
import { EvidenceTray } from "./EvidenceTray";
import { evidence } from "./evidence";
import { SqlBox } from "./SqlBox";
import { Timer } from "./Timer";
import { TableBrowser } from "./TableBrowser";
import "./workspace.css";

type Props = { onTaskChange?: (running: boolean) => void };

export default function Workspace({ onTaskChange }: Props) {
  const [sessionId, setSessionId] = useState("");
  const [task, setTask] = useState<TaskInfo | null>(null);
  const [tables, setTables] = useState<TableInfo[] | null>(null);
  const [error, setError] = useState("");
  const [waiting, setWaiting] = useState(false);

  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    setError("");
    (async () => {
      try {
        const s = await startSession();
        const t = await getTables(s.sessionId);
        if (live) {
          setSessionId(s.sessionId);
          setTask(s.task);
          setTables(t);
        }
      } catch (e) {
        if (live) setError((e as Error).message);
      }
    })();
    return () => {
      live = false;
    };
  }, [attempt]);

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

  // After an answer is sent, ask the server once a second for the next task.
  useEffect(() => {
    if (!waiting || !sessionId) return;
    const id = setInterval(async () => {
      try {
        const { task: next } = await getCurrentTask(sessionId);
        if (next?.id !== task?.id) {
          setTask(next);
          setWaiting(false);
        }
      } catch {
        /* keep trying */
      }
    }, 1000);
    return () => clearInterval(id);
  }, [waiting, sessionId, task?.id]);

  return (
    <div className="ws-root">
      {error ? (
        <div className="ws-state" role="alert">
          <p className="ws-error">{error}</p>
          <button className="btn" onClick={() => setAttempt((n) => n + 1)}>
            Try again
          </button>
        </div>
      ) : !tables ? (
        <div className="ws-state" role="status" aria-label="Loading the workspace">
          <div className="ws-skel" style={{ width: "40%" }} />
          <div className="ws-skel" style={{ width: "90%" }} />
          <div className="ws-skel tall" />
          <p className="empty">Loading your task and the tables…</p>
        </div>
      ) : !task ? (
        <p className="ws-sent" role="status">
          That was the last task. Nice work.
        </p>
      ) : (
        <>
          <div className="ws-task" key={`brief-${task.id}`}>
            <div className="ws-task-head">
              <h2 className="ws-title">{task.title}</h2>
              <Timer taskId={task.id} seconds={task.seconds} />
            </div>
            <p className="ws-brief">{task.brief}</p>
          </div>
          <TableBrowser sessionId={sessionId} tables={tables} />
          <SqlBox key={`sql-${task.id}`} sessionId={sessionId} />
          <EvidenceTray />
          <AnswerForm key={task.id} sessionId={sessionId} task={task} onSent={() => setWaiting(true)} />
          {waiting && <p className="empty" role="status">Waiting for the next task…</p>}
        </>
      )}
    </div>
  );
}

export { Workspace };
