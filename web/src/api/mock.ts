// Fake backend: same shapes as client.ts returns, used until Nived's routes exist.
// This stands in for the server only. Nothing outside this file should interpret SQL or invent data.

import customersCsv from "./mock/customers.csv?raw";
import storesCsv from "./mock/stores.csv?raw";
import tablesJson from "./mock/tables.json";
import visitsCsv from "./mock/visits.csv?raw";
import { live } from "./mockLive";
import type { TrapId } from "./traps";
import { recordedEvents, SCRIPT } from "./mockSession";
import { runMockSql } from "./mockSql";
import type { DemoInfo, AgentInfo, AnswerSubmission, AskReply, AskRequest, Cell, ColumnProfile, SponsorTotals, TableProfile, CurrentTask, EventsPage, EvidenceRef, Mastery, SessionInfo, SqlResult, StartOptions, TableInfo } from "./types";

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

export const DEMO_SESSION = "mock-demo";

const wait = <T,>(v: T, ms = 150) => new Promise<T>((res) => setTimeout(() => res(v), ms));

export const mock = {
  // The live sample is a small fake server that never acts for the learner (mockLive.ts).
  startSession: (o?: StartOptions) => wait<SessionInfo>(live.start(o)),

  getCurrentTask: () => wait<CurrentTask>(live.currentTask(), 50),

  getTables: () => wait<TableInfo[]>(FAKE_TABLES.map(({ rows, ...info }) => ({ ...info, rowCount: rows.length }))),

  getRows: (table: string, offset: number, limit: number) => {
    const t = FAKE_TABLES.find((x) => x.name === table);
    if (!t) return Promise.reject(new Error(`No such table: ${table}.`));
    return wait({ rows: t.rows.slice(offset, offset + limit) });
  },

  getEvents: (since: number, sessionId?: string) =>
    wait<EventsPage>(
      // The demo's recorded session is finished: it hands out every event at once. The live one grows as things happen.
      sessionId === DEMO_SESSION ? (since >= SCRIPT.length ? { events: [], next: since } : recordedEvents()) : live.events(since),
      30,
    ),

  // Mock mode only: the fake session stands in for the one the backend would pick.
  getDemo: () => wait<DemoInfo>({ session: DEMO_SESSION, start: 0, end: SCRIPT[SCRIPT.length - 1].t + 6, speed: 1 }),

  // Stand-in for the server's SQL runner (see mockSql.ts). Every query by the person becomes a learner.query event.
  runSql(sessionId: string, sql: string): Promise<SqlResult> {
    const record = sessionId !== DEMO_SESSION;
    try {
      const r = runMockSql(FAKE_TABLES, sql);
      if (record) live.query(sql, true, r.rows.length, 4);
      return wait({ ...r, ms: 4 });
    } catch (e) {
      if (record) live.query(sql, false, 0, 2, (e as Error).message);
      return Promise.reject(e);
    }
  },

  // What the person does: the fake panel reacts to their actual answer, appeal and questions. The demo session ignores them.
  submitAnswer: (sessionId: string, a: AnswerSubmission) => wait(sessionId === DEMO_SESSION ? { accepted: true } : live.answer(a)),
  openAppeal: (sessionId: string, taskId: string, reason: string) => wait(sessionId === DEMO_SESSION ? { appealId: "demo-appeal" } : live.appeal(taskId, reason)),
  sendAppealMessage: (sessionId: string, appealId: string, text: string) => {
    if (sessionId !== DEMO_SESSION) live.appealMessage(appealId, text);
    return wait({ ok: true });
  },
  getMastery: (sessionId: string) =>
    wait<Mastery>(
      sessionId === DEMO_SESSION
        ? { traps: ["duplicate_rows", "unit_mismatch", "dictionary_flip", "confounder", "hidden_variable", "none"].map((trap) => ({ trap: trap as TrapId, score: 0.15, attempts: 0 })) }
        : live.mastery(),
    ),

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

  ask: (sessionId: string, q: AskRequest): Promise<AskReply> =>
    wait(
      sessionId === DEMO_SESSION ? { agent: q.agent, text: "This is a recording, so there is nobody to ask.", sources: [] } : live.ask(q),
      400,
    ),

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

  getSponsors: (): Promise<SponsorTotals> => wait(live.sponsors(), 50),
};

export type { EvidenceRef };
