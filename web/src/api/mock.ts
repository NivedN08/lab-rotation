// Fake backend: same shapes as client.ts returns, used until Nived's routes exist.
// This stands in for the server only. Nothing outside this file should interpret SQL or invent data.

import type { AnswerSubmission, Cell, EventsPage, EvidenceRef, LabEvent, Mastery, SessionInfo, SqlResult, TableInfo } from "./types";

type FakeTable = Omit<TableInfo, "rowCount"> & { rows: Cell[][] };

function rng(seed: number) {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
}

const r = rng(7);
const pick = <T,>(xs: T[]) => xs[Math.floor(r() * xs.length)];
const round = (n: number, d = 2) => Math.round(n * 10 ** d) / 10 ** d;

const genes = ["BRCA1", "TP53", "EGFR", "MYC", "KRAS", "PTEN", "CDK2", "IL6", "TNF", "GAPDH", "ACTB", "VEGFA"];
const tissues = ["liver", "lung", "breast", "colon", "skin"];
const arms = ["control", "treated"];

const samples: Cell[][] = [];
for (let i = 1; i <= 120; i++) {
  samples.push([
    `S${String(i).padStart(3, "0")}`,
    pick(tissues),
    pick(arms),
    pick(["A", "B", "C"]),
    r() < 0.06 ? null : round(30 + r() * 50, 0),
    `2026-0${1 + Math.floor(r() * 9)}-${String(1 + Math.floor(r() * 27)).padStart(2, "0")}`,
  ]);
}
// planted trap: the same sample entered twice
samples.push([...samples[11]], [...samples[40]]);

const expression: Cell[][] = [];
let id = 1;
for (const s of samples.slice(0, 120)) {
  for (const g of genes.slice(0, 6)) {
    expression.push([id++, s[0], g, round(Math.exp(r() * 6), 2), s[3] === "C" ? "TPM" : "FPKM"]);
  }
}

const variants: Cell[][] = [];
for (let i = 1; i <= 80; i++) {
  variants.push([
    `V${String(i).padStart(3, "0")}`,
    pick(genes),
    `chr${1 + Math.floor(r() * 22)}`,
    Math.floor(r() * 1e8),
    pick(["missense", "synonymous", "nonsense", "intronic"]),
    round(r() * 0.5, 3),
  ]);
}

const FAKE_TABLES: FakeTable[] = [
  {
    name: "samples",
    about: "One row per sample: tissue, arm, batch, age and collection date.",
    columns: [
      { name: "sample_id", type: "text" },
      { name: "tissue", type: "text" },
      { name: "arm", type: "text" },
      { name: "batch", type: "text" },
      { name: "age", type: "int" },
      { name: "collected", type: "date" },
    ],
    rows: samples,
  },
  {
    name: "expression",
    about: "Expression level of each gene in each sample. Batch C reports TPM, the rest FPKM.",
    columns: [
      { name: "id", type: "int" },
      { name: "sample_id", type: "text" },
      { name: "gene", type: "text" },
      { name: "level", type: "real" },
      { name: "unit", type: "text" },
    ],
    rows: expression,
  },
  {
    name: "variants",
    about: "Variant calls per gene with allele frequency.",
    columns: [
      { name: "variant_id", type: "text" },
      { name: "gene", type: "text" },
      { name: "chrom", type: "text" },
      { name: "pos", type: "int" },
      { name: "effect", type: "text" },
      { name: "allele_freq", type: "real" },
    ],
    rows: variants,
  },
];

// ---- the fake routes ----

const wait = <T,>(v: T, ms = 150) => new Promise<T>((res) => setTimeout(() => res(v), ms));

export const mock = {
  startSession: () =>
    wait<SessionInfo>({
      sessionId: "mock-session",
      tasks: [
        { id: "t1", title: "Task 1", brief: "Does the treated arm really show higher expression? Check the data before you say.", seconds: 600 },
        { id: "t2", title: "Task 2", brief: "Is the batch C result comparable with the others?", seconds: 600 },
        { id: "t3", title: "Task 3", brief: "Do the variant calls support the claim?", seconds: 600 },
      ],
    }),

  getTables: () => wait<TableInfo[]>(FAKE_TABLES.map(({ rows, ...info }) => ({ ...info, rowCount: rows.length }))),

  getRows: (table: string, offset: number, limit: number) => {
    const t = FAKE_TABLES.find((x) => x.name === table);
    if (!t) return Promise.reject(new Error(`No such table: ${table}.`));
    return wait({ rows: t.rows.slice(offset, offset + limit) });
  },

  getEvents: (since: number) => wait<EventsPage>({ events: [] as LabEvent[], next: since }, 50),

  // Canned stand-in for the server's SQL runner.
  runSql(sql: string): Promise<SqlResult> {
    const m = sql
      .trim()
      .replace(/;\s*$/, "")
      .match(/^select\s+(.+?)\s+from\s+(\w+)(?:\s+where\s+(\w+)\s*(=|!=|>|<)\s*('?[^']*'?))?(?:\s+limit\s+(\d+))?$/is);
    if (!m) return Promise.reject(new Error("Sample mode understands only: SELECT <columns or *> FROM <table> [WHERE col = value] [LIMIT n]."));
    const [, sel, tname, wcol, op, wval, lim] = m;
    const table = FAKE_TABLES.find((t) => t.name.toLowerCase() === tname.toLowerCase());
    if (!table) return Promise.reject(new Error(`No such table: ${tname}. Tables are ${FAKE_TABLES.map((t) => t.name).join(", ")}.`));
    const names = table.columns.map((c) => c.name);
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
    if (/^count\(\*\)$/i.test(sel.trim())) return wait({ columns: ["count"], rows: [[rows.length]], ms: 3 });
    const cols = sel.trim() === "*" ? names : sel.split(",").map((s) => s.trim());
    const idx: number[] = [];
    for (const c of cols) {
      const i = names.indexOf(c);
      if (i < 0) return Promise.reject(new Error(`No such column: ${c} in ${table.name}.`));
      idx.push(i);
    }
    return wait({ columns: cols, rows: rows.slice(0, lim ? Number(lim) : 200).map((r) => idx.map((i) => r[i])), ms: 4 });
  },

  submitAnswer: (_a: AnswerSubmission) => wait({ accepted: true }),
  openAppeal: (_taskId: string, _reason: string) => wait({ appealId: "mock-appeal" }),
  sendAppealMessage: (_appealId: string, _text: string) => wait({ ok: true }),
  getMastery: () =>
    wait<Mastery>({
      traps: [
        { trap: "duplicates", score: 0.4, attempts: 2 },
        { trap: "missing values", score: 0.7, attempts: 3 },
        { trap: "unit mix-up", score: 0.2, attempts: 1 },
      ],
    }),
};

export type { EvidenceRef };
