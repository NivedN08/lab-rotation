// The only code in the front end that talks to the backend. Everything else calls these functions.
// The backend does all the real work (agents, grading, SQL, checks, voices); this file only sends and fetches.
//
// Which backend the app talks to:
// - Served by the real server (a production build): the real backend on the same origin, with no setting needed.
// - Under the Vite dev server (`npm run dev`): sample data by default. ?mock=0 calls the real /api routes, ?mock=1 forces sample data.
// - Static replay (build setting VITE_STATIC=1, for the hosted link): a recorded session read from JSON files, not /api.

import { getDemoState } from "./demo";
import { isDevServer, isStatic } from "./mode";
import { DEMO_SESSION, mock } from "./mock";
import { staticReplay } from "./staticReplay";
import { STATIC_FILES } from "./staticFiles";
import type { Health, DemoInfo, AgentInfo, AnswerSubmission, AskReply, AskRequest, Cell, CurrentTask, SponsorTotals, StartOptions, TableProfile, EventsPage, LabEvent, Mastery, SessionInfo, SqlResult, TableInfo } from "./types";

export * from "./types";
export * from "./traps";
export * from "./session";
export * from "./clock";
export * from "./demo";
export * from "./sponsors";
export { isStatic } from "./mode";
export { REPLAY_ONLY } from "./staticReplay";

/** Sample data instead of a backend. ?mock=1 forces it and ?mock=0 refuses it; otherwise it is the default only under `npm run dev`. */
export const useMock = (): boolean => {
  try {
    const asked = new URLSearchParams(window.location.search).get("mock");
    if (asked === "1") return true;
    if (asked === "0") return false;
  } catch {
    /* no window */
  }
  return isDevServer() && !isStatic();
};

/** Reading a recorded session from files (static replay mode), unless sample data was asked for. */
const replaying = (): boolean => isStatic() && !useMock();

/** A session read from files: static replay mode, and not the fake demo session. */
const fromFiles = (sessionId: string): boolean => replaying() && sessionId !== DEMO_SESSION;

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
  replaying() ? staticReplay.refuse() : useMock() ? mock.startSession(options) : call("POST", "/api/session/start", options);

/** The task the learner is on now, or null when all are done. Poll this after submitting to get the next one. */
export const getCurrentTask = (sessionId: string): Promise<CurrentTask> =>
  fromFiles(sessionId) ? staticReplay.getCurrentTask(sessionId) : fake(sessionId) ? mock.getCurrentTask() : call("GET", `/api/session/${enc(sessionId)}/task`);

/** Table names, descriptions, columns and row counts. */
export const getTables = (sessionId: string, taskId?: string): Promise<TableInfo[]> =>
  fromFiles(sessionId) ? staticReplay.getTables(sessionId, taskId) : fake(sessionId) ? mock.getTables() : call("GET", `/api/session/${enc(sessionId)}/tables${taskQuery(taskId, "?")}`);

/** A slice of one table's rows. */
export const getRows = async (sessionId: string, table: string, offset: number, limit: number, taskId?: string): Promise<Cell[][]> => {
  if (fromFiles(sessionId)) return staticReplay.getRows(sessionId, table, offset, limit, taskId);
  const r: { rows: Cell[][] } = fake(sessionId)
    ? await mock.getRows(table, offset, limit)
    : await call("GET", `/api/session/${enc(sessionId)}/tables/${enc(table)}/rows?offset=${offset}&limit=${limit}${taskQuery(taskId, "&")}`);
  return r.rows;
};

/** Events after `since` (pass the previous page's `next`). */
export const getEvents = (sessionId: string, since: number): Promise<EventsPage> =>
  fromFiles(sessionId) ? staticReplay.getEvents(sessionId, since) : fake(sessionId) ? mock.getEvents(since, sessionId) : call("GET", `/api/session/${enc(sessionId)}/events?since=${since}`);

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
  fromFiles(sessionId) ? staticReplay.refuse() : fake(sessionId) ? mock.runSql(sessionId, sql) : call("POST", `/api/session/${enc(sessionId)}/sql`, { sql });

/** Submit the answer with its cited evidence. The verdict comes back later as an event. */
export const submitAnswer = (sessionId: string, answer: AnswerSubmission): Promise<{ accepted: boolean }> =>
  fromFiles(sessionId) ? staticReplay.refuse() : fake(sessionId) ? mock.submitAnswer(sessionId, answer) : call("POST", `/api/session/${enc(sessionId)}/answer`, answer);

export const openAppeal = (sessionId: string, taskId: string, reason: string): Promise<{ appealId: string }> =>
  fromFiles(sessionId) ? staticReplay.refuse() : fake(sessionId) ? mock.openAppeal(sessionId, taskId, reason) : call("POST", `/api/session/${enc(sessionId)}/appeal`, { taskId, reason });

export const sendAppealMessage = (sessionId: string, appealId: string, text: string): Promise<{ ok: boolean }> =>
  fromFiles(sessionId) ? staticReplay.refuse() : fake(sessionId) ? mock.sendAppealMessage(sessionId, appealId, text) : call("POST", `/api/session/${enc(sessionId)}/appeal/${enc(appealId)}/message`, { text });

/** The learner's mastery, one score per trap type. */
export const getMastery = (sessionId: string): Promise<Mastery> =>
  fromFiles(sessionId) ? staticReplay.getMastery(sessionId) : fake(sessionId) ? mock.getMastery(sessionId) : call("GET", `/api/session/${enc(sessionId)}/mastery`);

/** Column profiles for one table: counts, nulls, distinct values, min, max, mean and the most common values. */
export const getProfile = (sessionId: string, table: string, taskId?: string): Promise<TableProfile> =>
  fromFiles(sessionId) ? staticReplay.getProfile(sessionId, table, taskId) : fake(sessionId) ? mock.getProfile(table) : call("GET", `/api/session/${enc(sessionId)}/tables/${enc(table)}/profile${taskQuery(taskId, "?")}`);

/** Ask one agent a question. The agent answers only from what it could see. */
export const askAgent = (sessionId: string, q: AskRequest): Promise<AskReply> =>
  fromFiles(sessionId) ? staticReplay.refuse() : fake(sessionId) ? mock.ask(sessionId, q) : call("POST", `/api/session/${enc(sessionId)}/ask`, q);

/** Names, floor roles, what each can read, and portrait URLs. Not tied to a session. */
export const getAgents = (): Promise<AgentInfo[]> => (replaying() ? staticReplay.getAgents() : useMock() ? mock.getAgents() : call("GET", "/api/agents"));

/** URL to play a voice line from (the `file` in a voice.line event's data). Use it as an audio element's src. */
export const audioUrl = (file: string): string =>
  useMock() || getDemoState().sample ? mock.audioUrl(file) : replaying() ? STATIC_FILES.audio(file) : `/api/audio/${enc(file)}`;

/** Totals for the sponsor strip. */
export const getSponsors = (sessionId: string): Promise<SponsorTotals> =>
  fromFiles(sessionId) ? staticReplay.getSponsors(sessionId) : fake(sessionId) ? mock.getSponsors() : call("GET", `/api/session/${enc(sessionId)}/sponsors`);

/**
 * The recorded session the backend picked for the demo. `session` is null when there is none: the demo then
 * falls back to the fake session and says "Sample data". In mock mode the fake session stands in directly.
 */
export const getDemo = (): Promise<DemoInfo> => (replaying() ? staticReplay.getDemo() : useMock() ? mock.getDemo() : call("GET", "/api/demo"));

/** Is the server up, is it in mock mode, and is BAND live or local. */
export const getHealth = (): Promise<Health> => (replaying() ? Promise.resolve({ ok: true, mock: false, band: "local" as const }) : useMock() ? Promise.resolve({ ok: true, mock: true, band: "local" as const }) : call("GET", "/api/health"));
