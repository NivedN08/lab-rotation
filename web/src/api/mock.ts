// Fake backend: same shapes as client.ts returns, used until Nived's routes exist.
// This stands in for the server only. Nothing outside this file should interpret SQL or invent data.

import customersCsv from "./mock/customers.csv?raw";
import storesCsv from "./mock/stores.csv?raw";
import tablesJson from "./mock/tables.json";
import taskJson from "./mock/task.json";
import visitsCsv from "./mock/visits.csv?raw";
import { elapsedNow, eventsSoFar, hurry, recordedEvents, scriptedEvents, SCRIPT, taskEndTime } from "./mockSession";
import { sponsorTotals } from "./sponsors";
import type { DemoInfo, AgentInfo, AnswerSubmission, AskReply, AskRequest, Cell, ColumnProfile, SponsorTotals, TableProfile, CurrentTask, TaskInfo, EventsPage, EvidenceRef, Mastery, SessionInfo, SqlResult, StartOptions, TableInfo } from "./types";

type FakeTable = Omit<TableInfo, "rowCount"> & { rows: Cell[][] };

// The contract's own sample task and tables (contract/mock_task/, copied into ./mock/), so sample data has the real shape.
const CSVS: Record<string, string> = { visits: visitsCsv, customers: customersCsv, stores: storesCsv };

function parseCsv(text: string, columns: TableInfo["columns"]): Cell[][] {
  return text
    .trim()
    .split("\n")
    .slice(1)
    .map((line) =>
      line.split(",").map((v, i): Cell => {
        if (v === "") return null;
        const type = columns[i]?.type;
        return type === "int" || type === "real" ? Number(v) : v;
      }),
    );
}

const FAKE_TABLES: FakeTable[] = (tablesJson as (TableInfo & { key?: string })[]).map(({ rowCount: _n, key: _k, ...t }) => ({ ...t, rows: parseCsv(CSVS[t.name] ?? "", t.columns) }));

// ---- the fake routes ----

// Slot t1 is the contract's sample task. Slots t2 and t3 reuse it so the one-task-at-a-time flow can be tried.
const TASKS: TaskInfo[] = [taskJson as TaskInfo, { ...(taskJson as TaskInfo), id: "t2", title: "Loyalty spend check, again" }, { ...(taskJson as TaskInfo), id: "t3", title: "Loyalty spend check, once more" }];

// How many answers the learner has sent. Kept in sessionStorage so a page reload does not restart the rotation.
const TASK_KEY = "lab-rotation.mock.answered";
function answered(): number {
  try {
    return Number(sessionStorage.getItem(TASK_KEY) ?? 0);
  } catch {
    return 0;
  }
}

/** The task now: after an answer, the next one is handed out once the sample session reaches the verdict. */
function currentTask(): TaskInfo | null {
  const n = answered();
  if (n === 0) return TASKS[0];
  return elapsedNow() >= taskEndTime() ? TASKS[n] ?? null : TASKS[n - 1];
}

export const DEMO_SESSION = "mock-demo";

const wait = <T,>(v: T, ms = 150) => new Promise<T>((res) => setTimeout(() => res(v), ms));

export const mock = {
  startSession: (_o?: StartOptions) =>
    wait<SessionInfo>({ sessionId: "mock-session", tasks: TASKS.map(({ id, title }) => ({ id, title })), task: currentTask() }),

  getCurrentTask: () => wait<CurrentTask>({ task: currentTask() }, 50),

  getTables: () => wait<TableInfo[]>(FAKE_TABLES.map(({ rows, ...info }) => ({ ...info, rowCount: rows.length }))),

  getRows: (table: string, offset: number, limit: number) => {
    const t = FAKE_TABLES.find((x) => x.name === table);
    if (!t) return Promise.reject(new Error(`No such table: ${table}.`));
    return wait({ rows: t.rows.slice(offset, offset + limit) });
  },

  getEvents: (since: number, sessionId?: string) =>
    wait<EventsPage>(
      // The fake recorded session is finished: it hands out every event at once.
      sessionId === DEMO_SESSION ? (since >= SCRIPT.length ? { events: [], next: since } : recordedEvents()) : scriptedEvents(since),
      30,
    ),

  // Mock mode only: the fake session stands in for the one the backend would pick.
  getDemo: () => wait<DemoInfo>({ session: DEMO_SESSION, start: 0, end: SCRIPT[SCRIPT.length - 1].t + 6, speed: 1 }),

  // Canned stand-in for the server's SQL runner.
  runSql(sql: string): Promise<SqlResult> {
    const m = sql
      .trim()
      .replace(/;\s*$/, "")
      .match(/^select\s+(.+?)\s+from\s+(\w+)(?:\s+where\s+(\w+)\s*(=|!=|>|<)\s*('?[^']*'?))?(?:\s+limit\s+(\d+))?$/is);
    if (!m) return Promise.reject(new Error("Sample mode can't run that one. It understands SELECT columns (or COUNT, AVG, SUM, MIN, MAX of a column) FROM one table, with an optional WHERE col = value and LIMIT n. The real server runs full SQL."));
    const [, sel, tname, wcol, op, wval, lim] = m;
    const table = FAKE_TABLES.find((t) => t.name.toLowerCase() === tname.toLowerCase());
    if (!table) return Promise.reject(new Error(`No such table: ${tname}. Tables are ${FAKE_TABLES.map((t) => t.name).join(", ")}.`));
    const names = table.columns.map((c) => c.name);
    const names0 = names;
    let rows = table.rows;
    if (wcol) {
      const i = names.indexOf(wcol);
      if (i < 0) return Promise.reject(new Error(`No such column: ${wcol} in ${table.name}.`));
      const v = wval.replace(/^'|'$/g, "");
      rows = rows.filter((r) => {
        const c = r[i];
        if (c === null) return false;
        if (op === "=") return String(c) === v;
        if (op === "!=") return String(c) !== v;
        return op === ">" ? Number(c) > Number(v) : Number(c) < Number(v);
      });
    }
    const aggs = sel.split(",").map((s) => s.trim().match(/^(count|avg|sum|min|max)\((\*|\w+)\)$/i));
    if (aggs.every(Boolean)) {
      const out: Cell[] = [];
      const names: string[] = [];
      for (const a of aggs as RegExpMatchArray[]) {
        const fn = a[1].toLowerCase();
        names.push(`${fn}(${a[2]})`);
        if (a[2] === "*") {
          if (fn !== "count") return Promise.reject(new Error(`${fn}(*) is not valid. Use a column name.`));
          out.push(rows.length);
          continue;
        }
        const i = names0.indexOf(a[2]);
        if (i < 0) return Promise.reject(new Error(`No such column: ${a[2]} in ${table.name}.`));
        const vals = rows.map((r) => r[i]).filter((v): v is string | number | boolean => v !== null);
        const nums = vals.filter((v): v is number => typeof v === "number");
        if (fn === "count") out.push(vals.length);
        else if (!nums.length) out.push(null);
        else if (fn === "sum") out.push(Math.round(nums.reduce((x, y) => x + y, 0) * 100) / 100);
        else if (fn === "avg") out.push(Math.round((nums.reduce((x, y) => x + y, 0) / nums.length) * 100) / 100);
        else out.push(fn === "min" ? Math.min(...nums) : Math.max(...nums));
      }
      return wait({ columns: names, rows: [out], ms: 3 });
    }
    const cols = sel.trim() === "*" ? names : sel.split(",").map((s) => s.trim());
    const idx: number[] = [];
    for (const c of cols) {
      const i = names.indexOf(c);
      if (i < 0) return Promise.reject(new Error(`No such column: ${c} in ${table.name}.`));
      idx.push(i);
    }
    return wait({ columns: cols, rows: rows.slice(0, lim ? Number(lim) : 200).map((r) => idx.map((i) => r[i])), ms: 4 });
  },

  submitAnswer: (_a: AnswerSubmission) => {
    try {
      sessionStorage.setItem(TASK_KEY, String(answered() + 1));
    } catch {
      /* ignore */
    }
    hurry(); // the sample session plays on faster toward the verdict
    return wait({ accepted: true });
  },
  openAppeal: (_taskId: string, _reason: string) => wait({ appealId: "mock-appeal" }),
  sendAppealMessage: (_appealId: string, _text: string) => wait({ ok: true }),
  getMastery: () =>
    wait<Mastery>({
      traps: [
        { trap: "duplicate_rows", score: 0.4, attempts: 2 },
        { trap: "unit_mismatch", score: 0.2, attempts: 1 },
        { trap: "dictionary_flip", score: 0.0, attempts: 0 },
        { trap: "confounder", score: 0.7, attempts: 3 },
        { trap: "hidden_variable", score: 0.1, attempts: 1 },
        { trap: "none", score: 0.5, attempts: 2 },
      ],
    }),

  getProfile(table: string): Promise<TableProfile> {
    const t = FAKE_TABLES.find((x) => x.name === table);
    if (!t) return Promise.reject(new Error(`No such table: ${table}.`));
    const columns: ColumnProfile[] = t.columns.map((c, j) => {
      const vals = t.rows.map((r) => r[j]);
      const present = vals.filter((v): v is string | number | boolean => v !== null);
      const counts = new Map<Cell, number>();
      present.forEach((v) => counts.set(v, (counts.get(v) ?? 0) + 1));
      const top = [...counts.entries()].sort((x, y) => y[1] - x[1]).slice(0, 5).map(([value, count]) => ({ value, count }));
      const nums = present.filter((v): v is number => typeof v === "number");
      const sorted = [...present].sort((x, y) => (x < y ? -1 : x > y ? 1 : 0));
      return {
        column: c.name,
        type: c.type,
        count: vals.length,
        nulls: vals.length - present.length,
        distinct: counts.size,
        ...(c.type !== "text" && sorted.length ? { min: sorted[0], max: sorted[sorted.length - 1] } : {}),
        ...(nums.length ? { mean: Math.round((nums.reduce((a, b) => a + b, 0) / nums.length) * 100) / 100 } : {}),
        top,
      };
    });
    return wait({ table, columns });
  },

  ask: (q: AskRequest): Promise<AskReply> =>
    wait({
      agent: q.agent,
      text: `(Sample answer) I can only speak to what I could see. You asked: "${q.text}".`,
      sources: ["samples", "trace://telem/1"],
    }, 400),

  getAgents: () =>
    wait<AgentInfo[]>([
      { id: "vale", name: "Dr. Vale", role: "director", reads: "The task list and your learner profile.", portrait: null },
      { id: "ines", name: "Ines", role: "referee", reads: "The answers, the checks and the key.", portrait: null },
      { id: "sam", name: "Sam", role: "head", reads: "What you have queried and cited so far.", portrait: null },
      { id: "telem", name: "Telem", role: "library", reads: "Search results and monitor hits.", portrait: null },
      { id: "riley", name: "Riley", role: "team-b", reads: "The same tables you see, worked separately.", portrait: null },
      { id: "learner", name: "You", role: "team-a", reads: "Everything you open in the workspace.", portrait: null },
    ]),

  // A short silent clip so the audio element has something to play.
  audioUrl: (_file: string): string =>
    "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=",

  getSponsors: (): Promise<SponsorTotals> => wait(sponsorTotals(eventsSoFar()), 50),
};

export type { EvidenceRef };
