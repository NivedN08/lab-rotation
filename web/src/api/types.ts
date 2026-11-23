import type { TrapId } from "./traps";

// Shapes sent to and from the backend. Written by the front end as a proposal;
// when Nived's contract/ folder lands, change these to match his.

export type Cell = string | number | boolean | null;

export type Column = { name: string; type: "text" | "int" | "real" | "date"; /** What the column means, in plain words. */ about?: string };

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
  /** Difficulty tier: 1 one trap in one table, 2 a trap plus a decoy, 3 a trap that spans two tables. */
  tier?: number;
  /** The claim the learner is checking. */
  claim?: string;
  /** The data dictionary, in Markdown. The only place the dictionary_flip trap shows up. Sent by GET /task, not in task.picked. */
  dictionary?: string;
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

/** Where an agent can walk to (agent.move's `data.place`; `from` uses the same ids). */
export type Place = "door" | "vale_office" | "learner_desk" | "riley_desk" | "shelves" | "terminal" | "panel_table" | "whiteboard";

export type AgentMoveData = { from: Place; place: Place };

/**
 * `search` (Telem). Each task has two, told apart by `data.phase`:
 * - `topic`: during the brief. Background on the claim only; nothing about what could be wrong.
 * - `case`: right after `panel.transcript`, with Telem walking to the learner's desk. A real case of this task's trap
 *   (or, on a clean task, of trusting a clean result), with its source and trace. `trap` is set only with `case`.
 */
export type SearchPhase = "topic" | "case";

export type SearchData = {
  phase?: SearchPhase;
  trap?: TrapId;
  query: string;
  cached: boolean;
  /** A Telem AI trace link. */
  trace: string;
  results: { title: string; url: string; snippet: string }[];
};

/** `panel.whisper`'s data. Before the task's `panel.transcript` there is no `text` and `sealed` is true. */
export type WhisperData = { text?: string; sealed?: boolean; cc?: AgentId[]; bandMessageId?: string; local?: boolean };

/**
 * `panel.transcript`: sent right after the verdict. Before the verdict, `panel.whisper` has no `data.text`;
 * this event carries the words of every whisper, keyed by the whisper's `seq`.
 */
export type PanelTranscriptData = { taskId?: string; whispers: { seq: number; agent: AgentId; to?: AgentId; text: string }[] };

export type EventsPage = { events: LabEvent[]; next: number };

export type SqlResult = { columns: string[]; rows: Cell[][]; ms: number; /** True when the server's 500-row cap cut the result. */ truncated?: boolean };

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
  /** A short title, such as "Lab head" or "Examiner". */
  title?: string;
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
  /** The front end may ignore this. */
  teamily?: { posts: number };
};

/** The recorded session the backend picked for the demo, or `session: null` when there is none. `start` and `end` are seconds since that session began. */
export type DemoInfo = { session: string | null; start: number; end: number; speed: number };

export type Health = { ok: boolean; mock: boolean; band: "live" | "local" };
