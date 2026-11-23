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
};

export type SessionInfo = { sessionId: string; tasks: TaskInfo[] };

/** One thing from the event stream. The floor and the workspace both read these. */
export type LabEvent = {
  seq: number;
  /** Seconds since the session started. */
  t: number;
  /** Event kind, e.g. "task.picked", "check.result", "verdict". */
  k: string;
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
  row?: number;
  column?: string;
  value?: Cell;
  label: string;
};

export type Verdict = "holds" | "fails" | "cant_tell";

export type AnswerSubmission = {
  taskId: string;
  verdict: Verdict;
  /** The trap type the learner believes they found. */
  trap: string;
  evidence: EvidenceRef[];
  note: string;
};

export type Mastery = { traps: { trap: string; score: number; attempts: number }[] };
