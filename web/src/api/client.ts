// The only code in the front end that talks to the backend. Everything else calls these functions.
// The backend does all the real work (agents, grading, SQL, checks, voices); this file only sends and fetches.
//
// Mock mode is on by default for now. Add ?mock=0 to the URL to call the real /api routes.

import { mock } from "./mock";
import type { AnswerSubmission, Cell, CurrentTask, EventsPage, LabEvent, Mastery, SessionInfo, SqlResult, TableInfo } from "./types";

export * from "./types";
export * from "./traps";
export * from "./session";

export const useMock = (): boolean => {
  try {
    return new URLSearchParams(window.location.search).get("mock") !== "0";
  } catch {
    return true;
  }
};

async function call<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: { accept: "application/json", ...(body ? { "content-type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Can't reach the lab server.");
  }
  const isJson = (res.headers.get("content-type") ?? "").includes("json");
  const data = isJson ? await res.json() : null;
  if (res.status === 404 || res.status === 503) throw new Error("The lab server isn't ready for this yet. Try again in a moment.");
  if (!res.ok || data?.error) throw new Error(data?.error ?? `The server answered ${res.status}.`);
  if (!isJson) throw new Error("The server sent something unexpected.");
  return data as T;
}

const enc = encodeURIComponent;

/** Start (or resume) a rotation session. Comes back with the current task. */
export const startSession = (): Promise<SessionInfo> => (useMock() ? mock.startSession() : call("POST", "/api/session/start"));

/** The task the learner is on now, or null when all are done. Poll this after submitting to get the next one. */
export const getCurrentTask = (sessionId: string): Promise<CurrentTask> =>
  useMock() ? mock.getCurrentTask() : call("GET", `/api/session/${enc(sessionId)}/task`);

/** Table names, descriptions, columns and row counts. */
export const getTables = (sessionId: string): Promise<TableInfo[]> =>
  useMock() ? mock.getTables() : call("GET", `/api/session/${enc(sessionId)}/tables`);

/** A slice of one table's rows. */
export const getRows = async (sessionId: string, table: string, offset: number, limit: number): Promise<Cell[][]> => {
  const r: { rows: Cell[][] } = useMock()
    ? await mock.getRows(table, offset, limit)
    : await call("GET", `/api/session/${enc(sessionId)}/tables/${enc(table)}/rows?offset=${offset}&limit=${limit}`);
  return r.rows;
};

/** Events after `since` (pass the previous page's `next`). */
export const getEvents = (sessionId: string, since: number): Promise<EventsPage> =>
  useMock() ? mock.getEvents(since) : call("GET", `/api/session/${enc(sessionId)}/events?since=${since}`);

/** Polls getEvents every second until the returned function is called. */
export function pollEvents(sessionId: string, onEvents: (events: LabEvent[]) => void, onError?: (e: Error) => void, ms = 1000): () => void {
  let since = 0;
  let stopped = false;
  const tick = async () => {
    if (stopped) return;
    try {
      const page = await getEvents(sessionId, since);
      since = page.next;
      if (page.events.length) onEvents(page.events);
    } catch (e) {
      onError?.(e as Error);
    }
    if (!stopped) setTimeout(tick, ms);
  };
  tick();
  return () => {
    stopped = true;
  };
};

/** Send a query to the server's SQL runner. Rejects with the server's error message. */
export const runSql = (sessionId: string, sql: string): Promise<SqlResult> =>
  useMock() ? mock.runSql(sql) : call("POST", `/api/session/${enc(sessionId)}/sql`, { sql });

/** Submit the answer with its cited evidence. The verdict comes back later as an event. */
export const submitAnswer = (sessionId: string, answer: AnswerSubmission): Promise<{ accepted: boolean }> =>
  useMock() ? mock.submitAnswer(answer) : call("POST", `/api/session/${enc(sessionId)}/answer`, answer);

export const openAppeal = (sessionId: string, taskId: string, reason: string): Promise<{ appealId: string }> =>
  useMock() ? mock.openAppeal(taskId, reason) : call("POST", `/api/session/${enc(sessionId)}/appeal`, { taskId, reason });

export const sendAppealMessage = (sessionId: string, appealId: string, text: string): Promise<{ ok: boolean }> =>
  useMock() ? mock.sendAppealMessage(appealId, text) : call("POST", `/api/session/${enc(sessionId)}/appeal/${enc(appealId)}/message`, { text });

/** The learner's mastery, one score per trap type. */
export const getMastery = (sessionId: string): Promise<Mastery> =>
  useMock() ? mock.getMastery() : call("GET", `/api/session/${enc(sessionId)}/mastery`);
