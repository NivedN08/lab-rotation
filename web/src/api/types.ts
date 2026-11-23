import type { TrapId } from "./traps";

// Shapes sent to and from the backend. Written by the front end as a proposal;
// when Nived's contract/ folder lands, change these to match his.

export type Cell = string | number | boolean | null;

export type Column = { name: string; type: "text" | "int" | "real" | "date" };

export type TableInfo = {
  name: string;
  about: string;
  columns: Column[];
  rowCount: number;
};

export type TaskInfo = {
  id: string;
  title: string;
  brief: string;
  /** Time allowed, in seconds. */
  seconds: number;
  /** Difficulty tier of the task. */
  tier?: string;
  /** The claim the learner is checking. */
  claim?: string;
  /** Why this task was picked for this learner. */
  reason?: string;
};

/** Tasks arrive one at a time. `task` is the current one, or null when all are done. */
export type SessionMode = "rotation" | "judge";

/** Optional body of POST /api/session/start. Sending nothing means { mode: "rotation" }. */
export type StartOptions = { mode?: SessionMode; learner?: string };

export type SessionInfo = {
  sessionId: string;
  /** Every task in the rotation, in order, so the top bar can show them before they are reached. */
  tasks: { id: string; title: string }[];
  task: TaskInfo | null;
};

export type AgentId = "vale" | "ines" | "sam" | "telem" | "riley" | "learner" | "system";

/** One thing from the event stream. The floor, the workspace and the decision log all read these. */
export type LabEvent = {
  seq: number;
  /** Seconds since the session started. */
  t: number;
  /** Event kind, e.g. "task.picked", "check.result", "verdict". */
  k: string;
  /** Who did it or who it is about. Always set. `system` for things no agent does (sponsor counters). */
  agent: AgentId;
  /** Why this happened, in plain words. Always set, never empty: it is the decision log the judges read. */
  why: string;
  /** Second agent, for events that move between two (panel.whisper, appeal messages). */
  to?: AgentId;
  /** Id of the task this event belongs to. */
  task?: string;
  /** Plain-words line for the lab log. */
  text?: string;
  data?: Record<string, unknown>;
};

export type EventsPage = { events: LabEvent[]; next: number };

export type SqlResult = { columns: string[]; rows: Cell[][]; ms: number };

export type EvidenceRef = {
  kind: "row" | "column" | "cell";
  /** Table name, or "query" for a SQL result. */
  source: string;
  sql?: string;
  /**
   * 1-based. For a table: the absolute row number in the table, counting from its first row (not from the page).
   * For a SQL result: the row's position within that result, and `sql` is also sent.
   */
  row?: number;
  column?: string;
  value?: Cell;
  label: string;
};

export type CurrentTask = { task: TaskInfo | null };

export type Verdict = "holds" | "fails" | "cant_tell";

export type AnswerSubmission = {
  taskId: string;
  verdict: Verdict;
  /** The trap the learner believes they found: a trap id, never a label. */
  trap: TrapId;
  evidence: EvidenceRef[];
  note: string;
};

export type Mastery = { traps: { trap: TrapId; score: number; attempts: number }[] };

export type ColumnProfile = {
  column: string;
  type: Column["type"];
  /** Rows in the table. */
  count: number;
  nulls: number;
  distinct: number;
  /** Numeric and date columns only (dates as text). */
  min?: Cell;
  max?: Cell;
  /** Numeric columns only. */
  mean?: number;
  /** Most common values, most common first (up to 5). */
  top: { value: Cell; count: number }[];
};

export type TableProfile = { table: string; columns: ColumnProfile[] };

export type AskRequest = { agent: AgentId; text: string };

/** An agent's answer. It only knows what that agent could see; `sources` says what it used. */
export type AskReply = { agent: AgentId; text: string; sources: string[] };

export type AgentInfo = {
  id: AgentId;
  name: string;
  /** Floor role: director, referee, library, head, team-a, team-b. */
  role: string;
  /** What this agent can read, in plain words. */
  reads: string;
  /** URL of the portrait image, or null. */
  portrait: string | null;
};

export type SponsorTotals = {
  band: { messages: number };
  telem: { searches: number; monitorHits: number; traces: string[] };
  bruin: { checksRun: number; checksFailed: number };
  runware: { lines: number; cost: number };
  glasser: { calls: number };
};

/** The recorded session the backend picked for the demo, or `session: null` when there is none. `start` and `end` are seconds since that session began. */
export type DemoInfo = { session: string | null; start: number; end: number; speed: number };
