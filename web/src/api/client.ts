// The only code in the front end that talks to the backend. Everything else calls these functions.
// The backend does all the real work (agents, grading, SQL, checks, voices); this file only sends and fetches.
//
// Mock mode is on by default for now. Add ?mock=0 to the URL to call the real /api routes.

import { getDemoState } from "./demo";
import { DEMO_SESSION, mock } from "./mock";
import type { Health, DemoInfo, AgentInfo, AnswerSubmission, AskReply, AskRequest, Cell, CurrentTask, SponsorTotals, StartOptions, TableProfile, EventsPage, LabEvent, Mastery, SessionInfo, SqlResult, TableInfo } from "./types";

export * from "./types";
export * from "./traps";
export * from "./session";
export * from "./clock";
export * from "./demo";
export * from "./sponsors";

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

/** `task` picks which task's tables to read (a slot id), so a replay can show any task of a finished session. Without it the server uses the current one. */
const taskQuery = (taskId: string | undefined, lead: "?" | "&") => (taskId ? `${lead}task=${enc(taskId)}` : "");

/** True for the fake demo session (mock mode, or the backend had no demo to offer), which the server does not know. */
const fake = (sessionId: string): boolean => useMock() || sessionId === DEMO_SESSION;

/** Start (or resume) a session. Comes back with the whole rotation and the current task. Sending nothing means rotation mode. */
export const startSession = (options?: StartOptions): Promise<SessionInfo> =>
  useMock() ? mock.startSession(options) : call("POST", "/api/session/start", options);

/** The task the learner is on now, or null when all are done. Poll this after submitting to get the next one. */
export const getCurrentTask = (sessionId: string): Promise<CurrentTask> =>
  fake(sessionId) ? mock.getCurrentTask() : call("GET", `/api/session/${enc(sessionId)}/task`);

/** Table names, descriptions, columns and row counts. */
export const getTables = (sessionId: string, taskId?: string): Promise<TableInfo[]> =>
  fake(sessionId) ? mock.getTables() : call("GET", `/api/session/${enc(sessionId)}/tables${taskQuery(taskId, "?")}`);

/** A slice of one table's rows. */
export const getRows = async (sessionId: string, table: string, offset: number, limit: number, taskId?: string): Promise<Cell[][]> => {
  const r: { rows: Cell[][] } = useMock()
    ? await mock.getRows(table, offset, limit)
    : await call("GET", `/api/session/${enc(sessionId)}/tables/${enc(table)}/rows?offset=${offset}&limit=${limit}${taskQuery(taskId, "&")}`);
  return r.rows;
};

/** Events after `since` (pass the previous page's `next`). */
export const getEvents = (sessionId: string, since: number): Promise<EventsPage> =>
  fake(sessionId) ? mock.getEvents(since, sessionId) : call("GET", `/api/session/${enc(sessionId)}/events?since=${since}`);

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
  fake(sessionId) ? mock.runSql(sessionId, sql) : call("POST", `/api/session/${enc(sessionId)}/sql`, { sql });

/** Submit the answer with its cited evidence. The verdict comes back later as an event. */
export const submitAnswer = (sessionId: string, answer: AnswerSubmission): Promise<{ accepted: boolean }> =>
  fake(sessionId) ? mock.submitAnswer(sessionId, answer) : call("POST", `/api/session/${enc(sessionId)}/answer`, answer);

export const openAppeal = (sessionId: string, taskId: string, reason: string): Promise<{ appealId: string }> =>
  fake(sessionId) ? mock.openAppeal(sessionId, taskId, reason) : call("POST", `/api/session/${enc(sessionId)}/appeal`, { taskId, reason });

export const sendAppealMessage = (sessionId: string, appealId: string, text: string): Promise<{ ok: boolean }> =>
  fake(sessionId) ? mock.sendAppealMessage(sessionId, appealId, text) : call("POST", `/api/session/${enc(sessionId)}/appeal/${enc(appealId)}/message`, { text });

/** The learner's mastery, one score per trap type. */
export const getMastery = (sessionId: string): Promise<Mastery> =>
  fake(sessionId) ? mock.getMastery(sessionId) : call("GET", `/api/session/${enc(sessionId)}/mastery`);

/** Column profiles for one table: counts, nulls, distinct values, min, max, mean and the most common values. */
export const getProfile = (sessionId: string, table: string, taskId?: string): Promise<TableProfile> =>
  fake(sessionId) ? mock.getProfile(table) : call("GET", `/api/session/${enc(sessionId)}/tables/${enc(table)}/profile${taskQuery(taskId, "?")}`);

/** Ask one agent a question. The agent answers only from what it could see. */
export const askAgent = (sessionId: string, q: AskRequest): Promise<AskReply> =>
  fake(sessionId) ? mock.ask(sessionId, q) : call("POST", `/api/session/${enc(sessionId)}/ask`, q);

/** Names, floor roles, what each can read, and portrait URLs. Not tied to a session. */
export const getAgents = (): Promise<AgentInfo[]> => (useMock() ? mock.getAgents() : call("GET", "/api/agents"));

/** URL to play a voice line from (the `file` in a voice.line event's data). Use it as an audio element's src. */
export const audioUrl = (file: string): string => (useMock() || getDemoState().sample ? mock.audioUrl(file) : `/api/audio/${enc(file)}`);

/** Totals for the sponsor strip. */
export const getSponsors = (sessionId: string): Promise<SponsorTotals> =>
  fake(sessionId) ? mock.getSponsors() : call("GET", `/api/session/${enc(sessionId)}/sponsors`);

/**
 * The recorded session the backend picked for the demo. `session` is null when there is none: the demo then
 * falls back to the fake session and says "Sample data". In mock mode the fake session stands in directly.
 */
export const getDemo = (): Promise<DemoInfo> => (useMock() ? mock.getDemo() : call("GET", "/api/demo"));

/** Is the server up, is it in mock mode, and is BAND live or local. */
export const getHealth = (): Promise<Health> => (useMock() ? Promise.resolve({ ok: true, mock: true, band: "local" as const }) : call("GET", "/api/health"));
