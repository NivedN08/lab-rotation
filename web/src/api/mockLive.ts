// The fake server for a live sample session (Your rotation and Judge mode).
//
// It never acts for the learner: it emits learner.query, learner.evidence, learner.answer, appeal.* and ask events
// only when the real person does those things. Everything else (the task, Vale, Telem, Riley, the panel, the
// checks, the verdict) is the lab's own work, and the verdict is worked out from what the person actually answered.
// The scripted learner lives only in the demo (mockSession.ts).
//
// Judge mode is one task (t1, tier 1, 240 s) that ends the session after its verdict. Your rotation is three tasks
// at tiers 1, 2 and 3. If time runs out, the server answers cant_tell for the learner and says so in the event's why.

import taskJson from "./mock/task.json";
import { sponsorTotals } from "./sponsors";
import { trapLabel } from "./traps";
import type {
  AgentId, AnswerSubmission, AskReply, AskRequest, CurrentTask, EventsPage, EvidenceRef, LabEvent, Mastery,
  SessionInfo, SponsorTotals, StartOptions, TaskInfo, Verdict,
} from "./types";
import type { TrapId } from "./traps";

type Def = TaskInfo & {
  key: { verdict: Verdict; trap: TrapId };
  riley: { verdict: Verdict; trap: TrapId; note: string };
  say: string;
  background: string;
  realCase: string;
  check: { id: string; detail: string; rows?: (string | number)[][] };
  /** The real case Telem finds after the verdict: a search result with its source. */
  caseResult: { query: string; title: string; url: string; snippet: string };
  pickReason: string;
};

const dictionary = (taskJson as { dictionary?: string }).dictionary;

// Task 1 is the contract's own sample task. Tasks 2 and 3 are made up for the sample and reuse the same tables.
const DEFS: Def[] = [
  {
    ...(taskJson as TaskInfo),
    key: { verdict: "fails", trap: "unit_mismatch" },
    riley: { verdict: "holds", trap: "none", note: "Members average 1067 vs 441 for others. That's 2.4x. Claim holds." },
    say: "Marketing says loyalty members spend 2.4 times as much per visit. It goes to the board on Friday. Check it before it does.",
    background: "Some background for you: comparisons like this usually average spend per visit for each customer group. The source and trace are on the card.",
    realCase: "A real case, now that you have your verdict: a chain once restated a region's sales because its export used cents. Source and trace are on the card.",
    check: { id: "unit_mismatch.spend_range_by_region", detail: "West spend runs 792 to 5600; every other region runs 4 to 74", rows: [["v0083", "st04", 5600], ["v0165", "st04", 5272], ["v0150", "st04", 5108]] },
    pickReason: "new learner with no history: start at tier 1",
    caseResult: { query: "retail sales data reported in cents instead of dollars restated", title: "Mock case: a chain restated regional sales after an export unit bug", url: "https://example.com/mock-case-units", snippet: "One region's export switched to minor units..." },
  },
  {
    id: "t2", title: "Weekend baskets", seconds: 240, tier: 2, dictionary,
    claim: "Weekend visits bring in bigger baskets than weekday visits.",
    brief: "Operations wants more staff on weekends because baskets are bigger. Check the claim before they hire.",
    key: { verdict: "fails", trap: "confounder" },
    riley: { verdict: "holds", trap: "none", note: "Weekend average spend is higher. Claim holds." },
    say: "Operations says weekend baskets are bigger and wants to hire for weekends. Check it first.",
    background: "Some background for you: a difference between two groups is only meaningful if the groups are alike in other ways. The source and trace are on the card.",
    realCase: "A real case, now that you have your verdict: a retailer once credited weekends for a lift that really came from a loyalty promotion. Source and trace are on the card.",
    check: { id: "confounder.loyalty_mix_by_weekday", detail: "Loyalty members make 61% of weekend visits but 28% of weekday visits", rows: [["weekend", "loyalty", 61], ["weekday", "loyalty", 28]] },
    pickReason: "your last task went well, so the next one is a tier harder: a trap plus a decoy",
    caseResult: { query: "weekend sales lift credited to the wrong cause loyalty promotion", title: "Mock case: a retailer credited weekends for a lift that came from a loyalty promotion", url: "https://example.com/mock-case-confounder", snippet: "The lift disappeared once promotion weeks were set aside..." },
  },
  {
    id: "t3", title: "Home store visits", seconds: 240, tier: 3, dictionary,
    claim: "Customers whose home store is in the West visit less often.",
    brief: "The regional manager wants to close West stores because their customers visit less. Check the claim first.",
    key: { verdict: "fails", trap: "hidden_variable" },
    riley: { verdict: "holds", trap: "none", note: "West customers have fewer visits per customer. Claim holds." },
    say: "The regional manager says West customers visit less and wants to close stores. Check it before anyone is told.",
    background: "Some background for you: counts of visits depend on how each store records them, not only on how customers behave. The source and trace are on the card.",
    realCase: "A real case, now that you have your verdict: a chain once saw one region's visits drop because an old till version stopped logging small baskets. Source and trace are on the card.",
    check: { id: "hidden_variable.pos_version_by_region", detail: "Every West store runs the old point-of-sale version, which drops visits under $5", rows: [["st04", "West", "pos_v1"], ["st08", "West", "pos_v1"]] },
    pickReason: "you are ready for a trap that spans two tables, so this one hides in the stores table",
    caseResult: { query: "region visits dropped old point of sale version stopped logging small baskets", title: "Mock case: a chain saw one region's visits drop after an old till stopped logging small baskets", url: "https://example.com/mock-case-hidden-variable", snippet: "The drop traced to one point-of-sale version..." },
  },
];

// One check per trap id that has a planted form; the planted trap's check fails and the rest pass.
const CHECKED: TrapId[] = ["duplicate_rows", "dictionary_flip", "confounder", "hidden_variable", "unit_mismatch"];
const PASSES: Record<string, [string, string]> = {
  duplicate_rows: ["duplicate_rows.unique_visit", "visit_id is unique (300 of 300)"],
  dictionary_flip: ["dictionary_flip.loyalty_flag_values", "loyalty_member holds only 0 and 1, as the dictionary says"],
  confounder: ["confounder.pos_version_balance", "point-of-sale versions are spread evenly across customer groups"],
  hidden_variable: ["hidden_variable.joins_complete", "every visit joins to a customer and a store"],
  unit_mismatch: ["unit_mismatch.spend_range_by_region", "spend runs 4 to 74 in every region"],
};

const BANDIT = {
  unit_mismatch: { mean: 0.15, sample: 0.71 }, duplicate_rows: { mean: 0.15, sample: 0.52 }, dictionary_flip: { mean: 0.15, sample: 0.33 },
  confounder: { mean: 0.15, sample: 0.48 }, hidden_variable: { mean: 0.15, sample: 0.29 }, none: { mean: 0.15, sample: 0.44 },
};

// ---- state, kept in sessionStorage so a reload or a closed panel does not restart the session ----

type Ev = Omit<LabEvent, "seq"> & { ref?: string; lineOfRef?: string };
type Answer = { verdict: Verdict; trap: TrapId; evidence: EvidenceRef[]; note: string; timedOut: boolean; score: number; result: "passed" | "failed" };
type Live = {
  mode: "rotation" | "judge";
  learner: string;
  start: number;
  tasks: number; // how many tasks this session has
  index: number; // current task
  taskT: number; // when the current task began, in session seconds
  nextAt: number | null; // when the next task (or the end) happens, after an answer
  ended: boolean;
  planned: Ev[];
  delivered: LabEvent[];
  refs: Record<string, number>;
  answers: Record<string, Answer>;
  queries: number;
  appeals: number;
  files: number;
  traces: number;
  hash: string;
  mastery: Record<string, { score: number; attempts: number }>;
};

const KEY = "lab-rotation.mock.live";
let memory: Live | null = null;

function load(): Live | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (raw) return (memory = JSON.parse(raw) as Live);
  } catch {
    /* keep it in memory */
  }
  return memory;
}

function save(s: Live) {
  memory = s;
  try {
    sessionStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* keep it in memory */
  }
}

const speed = (): number => {
  try {
    return Number(new URLSearchParams(window.location.search).get("mockspeed")) || 1;
  } catch {
    return 1;
  }
};

const nowT = (s: Live) => ((Date.now() - s.start) / 1000) * speed();
const def = (s: Live, i = s.index) => DEFS[i];
const pub = ({ key: _k, riley: _r, say: _s, background: _b, realCase: _c, check: _ch, pickReason: _p, ...task }: Def): TaskInfo => task;

// ---- planning events ----

const plan = (s: Live, ...events: Ev[]) => s.planned.push(...events);

function voice(s: Live, t: number, agent: AgentId, task: string, lineRef: string): Ev[] {
  s.files += 1;
  return [
    { t, k: "voice.line", agent, task, why: "speak the line in the agent's own voice", lineOfRef: lineRef, data: { file: `mock-${s.files}.mp3`, seconds: 8.4, cost: 0.0012, provider: "runware" } },
    { t, k: "sponsor.call", agent: "system", why: "every spoken line is a Runware voice", data: { sponsor: "runware", label: `voice line for ${agent}`, count: 1, op: "tts", by: agent, ms: 820, fallback: false, cost: 0.0012 } },
  ];
}

function band(t: number, by: AgentId, what: string): Ev {
  return { t, k: "sponsor.call", agent: "system", why: "the panel talks in its BAND room", data: { sponsor: "band", label: `${by} ${what}`, count: 1, op: "send_message", by, ms: 140, fallback: false } };
}

/** The lab's own opening of a task: Vale picks it and briefs the learner, Telem gives background on the topic only. */
function intro(s: Live, i: number, T: number) {
  const d = def(s, i);
  const first = i === 0;
  const ref = (n: string) => `${d.id}.${n}`;
  const trace = `https://app.telem.ai/traces/mock-${++s.traces}`;
  if (first) {
    plan(s,
      { t: 0, k: "session.start", agent: "system", why: s.mode === "judge" ? "a judge sat down at the desk and chose judge mode" : "the learner started their rotation", data: { mode: s.mode, learner: s.learner, tasks: s.tasks } },
      { t: 0.5, k: "sponsor.call", agent: "system", why: "every task's tables go through Bruin", data: { sponsor: "bruin", label: "loaded the task tables with ingestr", count: 1, op: "run", by: "system", ms: 1900, fallback: false } },
    );
  }
  plan(s,
    { t: T, k: "task.picked", agent: "vale", task: d.id, why: d.pickReason, text: `Vale picked ${first ? "the first" : "the next"} task.`, data: { taskId: d.id, title: d.title, brief: d.brief, seconds: d.seconds, tier: d.tier, claim: d.claim, dictionary: d.dictionary, fallback: false, reason: d.pickReason } },
    { t: T + 0.5, k: "agent.move", agent: "vale", to: "learner", task: d.id, why: "brief the learner in person", data: { from: "vale_office", place: "learner_desk" } },
    { t: T + 4, k: "agent.say", agent: "vale", to: "learner", task: d.id, why: "deliver the brief and the claim", text: d.say, ref: ref("brief") },
    ...voice(s, T + 4.4, "vale", d.id, ref("brief")),
    { t: T + 5, k: "agent.move", agent: "telem", task: d.id, why: "look up background on the topic of this claim", data: { from: first ? "door" : "shelves", place: "shelves" } },
    { t: T + 6, k: "sponsor.call", agent: "system", why: "the librarian looks up background on the topic with Telem AI", data: { sponsor: "telem", label: "searched for background on the topic", count: 1, op: "search", by: "telem", ms: 1430, fallback: false, trace } },
    { t: T + 7.5, k: "search", agent: "telem", task: d.id, why: "background on the claim's topic; the search uses only the public claim", text: "Telem looked up background on the claim.", data: { phase: "topic", query: `retail data: ${d.claim}`, cached: false, trace, results: [{ title: "Background on this kind of comparison", url: "https://example.com/mock-topic", snippet: "How teams usually compare these numbers..." }] } },
    { t: T + 8, k: "agent.move", agent: "telem", to: "learner", task: d.id, why: "bring the background to the learner", data: { from: "shelves", place: "learner_desk" } },
    { t: T + 11, k: "agent.say", agent: "telem", to: "learner", task: d.id, why: "share some background on the topic, with its source, and nothing about what might be wrong", text: d.background, ref: ref("background") },
    ...voice(s, T + 11.4, "telem", d.id, ref("background")),
    { t: T + 12, k: "agent.move", agent: "vale", task: d.id, why: "brief done; let the learner work", data: { from: "learner_desk", place: "vale_office" } },
    { t: T + 12, k: "agent.move", agent: "telem", task: d.id, why: "back to the shelves", data: { from: "learner_desk", place: "shelves" } },
  );
  // Riley sits down: the task's clock starts here, and so does the server's timer.
  plan(s, { t: T + 13, k: "agent.move", agent: "riley", task: d.id, why: "the intern races the learner on the same task", data: { from: first ? "door" : "learner_desk", place: "riley_desk" } });
  s.taskT = T + 13;
}

// ---- what the panel does once an answer is in ----

function score(d: Def, a: { verdict: Verdict; trap: TrapId; evidence: EvidenceRef[] }) {
  const verdict = a.verdict === d.key.verdict;
  const trap = a.trap === d.key.trap;
  const evidence = a.evidence.length > 0;
  const total = Math.round(((verdict ? 0.4 : 0) + (trap ? 0.4 : 0) + (evidence ? 0.2 : 0)) * 100) / 100;
  // Right needs both the verdict and the trap; anything less is partly right or wrong, and fails.
  return { verdict, trap, evidence, total, result: (verdict && trap ? "passed" : "failed") as "passed" | "failed" };
}

function feedback(d: Def, a: { verdict: Verdict; trap: TrapId; note: string }, r: ReturnType<typeof score>, timedOut: boolean) {
  const keyVerdict = d.key.verdict === "holds" ? "holds" : d.key.verdict === "fails" ? "fails" : "can't be told";
  if (timedOut) return `Time ran out, so the answer was "can't tell". The key says the claim ${keyVerdict}: ${trapLabel(d.key.trap).toLowerCase()}.`;
  if (r.verdict && r.trap) return `Right verdict, right trap.${a.note.trim() ? ` You wrote "${a.note.trim().slice(0, 80)}", which matches what the failing check shows.` : ""}`;
  if (r.verdict) return `Right verdict, but the trap was ${trapLabel(d.key.trap).toLowerCase()}, not ${trapLabel(a.trap).toLowerCase()}.`;
  if (r.trap) return `You spotted the trap, ${trapLabel(d.key.trap).toLowerCase()}, but the claim ${keyVerdict}, so the verdict was wrong.`;
  return `Not this time. The key says the claim ${keyVerdict} and the trap is ${trapLabel(d.key.trap).toLowerCase()}.`;
}

function react(s: Live, d: Def, a: Answer, r: ReturnType<typeof score>, T: number) {
  const t = d.id;
  const tracedRef = `${t}.verdict`;
  const prev = s.hash;
  s.hash = Math.abs([...`${prev}${t}${a.verdict}${a.trap}`].reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 7)).toString(16).padStart(12, "0").slice(0, 12);
  const index = Object.keys(s.answers).length;
  const m = s.mastery[d.key.trap] ?? { score: 0.15, attempts: 0 };
  const from = m.score;
  const to = Math.round((a.result === "passed" ? from + (1 - from) * 0.5 : Math.max(0.05, from - 0.05)) * 100) / 100;
  s.mastery[d.key.trap] = { score: to, attempts: m.attempts + 1 };
  const said = feedback(d, a, r, a.timedOut);
  const quote = a.note.trim() ? [{ text: a.note.trim().slice(0, 60), source: "note" }] : [];
  const ruleWhy = d.key.trap === "none" ? "the data is clean" : `the planted trap is ${trapLabel(d.key.trap).toLowerCase()}`;
  const trace = `https://app.telem.ai/traces/mock-${++s.traces}`;
  const L = (n: string) => `${t}.${n}`;

  plan(s,
    { t: T + 2.5, k: "rival.answer", agent: "riley", task: t, why: "the intern took the overall numbers and stopped there", text: `Riley answered: ${d.riley.verdict}.`, data: { verdict: d.riley.verdict, trap: d.riley.trap, note: d.riley.note, model: "open model via Runware", provider: "runware" } },
    { t: T + 2.6, k: "sponsor.call", agent: "system", why: "the intern runs on an open model served by Runware", data: { sponsor: "runware", label: "Riley's analysis on an open model", count: 1, op: "chat", by: "riley", ms: 2300, fallback: false, cost: 0.0004 } },
    { t: T + 4, k: "agent.move", agent: "vale", task: t, why: "the panel meets to grade the answer", data: { from: "vale_office", place: "panel_table" } },
    { t: T + 4, k: "agent.move", agent: "ines", task: t, why: "the panel meets to grade the answer", data: { from: "terminal", place: "panel_table" } },
    { t: T + 4, k: "agent.move", agent: "sam", task: t, why: "the panel meets to grade the answer", data: { from: "whiteboard", place: "panel_table" } },
    // Whispers carry no words (and say they are sealed) until the verdict; panel.transcript brings the words.
    { t: T + 5, k: "panel.whisper", agent: "ines", to: "vale", task: t, why: "Ines shares the basis for the grade", ref: L("w1"), data: { sealed: true, cc: ["sam"], bandMessageId: `band-mock-${t}-1`, local: false } },
    band(T + 5.2, "ines", "posted in the panel room"),
    { t: T + 6.5, k: "panel.whisper", agent: "sam", to: "ines", task: t, why: "Sam reports the coaching history", ref: L("w2"), data: { sealed: true, cc: ["vale"], bandMessageId: `band-mock-${t}-2`, local: false } },
    band(T + 6.7, "sam", "posted in the panel room"),
    { t: T + 8, k: "panel.whisper", agent: "vale", to: "ines", task: t, why: "Vale decides the verdict", ref: L("w3"), data: { sealed: true, cc: ["sam"], bandMessageId: `band-mock-${t}-3`, local: false } },
    band(T + 8.2, "vale", "posted in the panel room"),
    // One Bruin run, five checks (one per trap id); the planted trap's check fails.
    { t: T + 8.5, k: "sponsor.call", agent: "system", why: "Bruin's checks prove the planted trap", data: { sponsor: "bruin", label: "ran 5 quality checks", count: 1, op: "check", by: "ines", ms: 2600, fallback: false } },
    ...CHECKED.map((trap, i): Ev => {
      const planted = trap === d.key.trap;
      const [id, passDetail] = PASSES[trap];
      return {
        t: T + 8.7 + i * 0.4, k: "check.result", agent: "ines", task: t,
        why: planted ? `the answer key: ${ruleWhy}` : `no sign of ${trapLabel(trap).toLowerCase()}, so this check passes`,
        text: planted ? `Check failed: ${d.check.detail}.` : `Check passed: ${passDetail}.`,
        data: planted
          ? { check: d.check.id, trap, passed: false, detail: d.check.detail, bruinRun: "run-mock-2", rows: d.check.rows }
          : { check: id, trap, passed: true, detail: passDetail, bruinRun: "run-mock-2" },
      };
    }),
    { t: T + 10.8, k: "sponsor.call", agent: "system", why: "a failed check is counted on the strip", data: { sponsor: "bruin", label: "1 check failed", count: 1, op: "check", by: "ines", ms: 0, fallback: false, failed: true } },
    { t: T + 11, k: "ledger.seal", agent: "system", task: t, why: "seal the grade in the hash chain", data: { index: index + 1, hash: s.hash, prev: prev, record: { taskId: t, score: a.score, verdict: a.verdict, trap: a.trap } } },
    {
      t: T + 11.5, k: "verdict", agent: "ines", task: t, text: `${a.result === "passed" ? "Passed" : "Failed"}: ${a.score}.`,
      why: "graded against the answer key, with the failing Bruin check as evidence",
      data: { taskId: t, result: a.result, score: a.score, parts: { verdict: r.verdict ? 1 : 0, trap: r.trap ? 1 : 0, evidence: r.evidence ? 1 : 0, hints: 0 }, correctVerdict: d.key.verdict, correctTrap: d.key.trap, text: said, quotes: quote, failingCheck: d.check.id, ledger: { index: index + 1, hash: s.hash, prev } },
      ref: tracedRef,
    },
    // Right after the verdict: the words of the whispers.
    { t: T + 11.7, k: "panel.transcript", agent: "ines", task: t, why: "the verdict is in, so the panel's whispers are open", data: { taskId: t, whispers: [
      { refSeq: L("w1"), agent: "ines", to: "vale", text: `The key says ${trapLabel(d.key.trap).toLowerCase()}, verdict ${d.key.verdict}. The learner answered ${a.verdict}, ${trapLabel(a.trap).toLowerCase()}.` },
      { refSeq: L("w2"), agent: "sam", to: "ines", text: "No hints were needed. Nothing to deduct." },
      { refSeq: L("w3"), agent: "vale", to: "ines", text: `${r.verdict && r.trap ? "Full marks on verdict and trap." : r.verdict || r.trap ? "Partly right." : "Not right."} Ines, deliver it with the failing check.` },
    ] } },
    { t: T + 12, k: "agent.move", agent: "ines", task: t, why: "the panel is done, so Ines goes back to the terminal", data: { from: "panel_table", place: "terminal" } },
    { t: T + 12.5, k: "agent.say", agent: "ines", to: "learner", task: t, why: "deliver the verdict out loud", text: said, ref: L("say"), data: { quotes: quote } },
    ...voice(s, T + 12.9, "ines", t, L("say")),
    { t: T + 13, k: "agent.move", agent: "vale", task: t, why: "the panel is done, so Vale goes back to the office", data: { from: "panel_table", place: "vale_office" } },
    { t: T + 13, k: "agent.move", agent: "sam", task: t, why: "the panel is done, so Sam goes back to the whiteboard", data: { from: "panel_table", place: "whiteboard" } },
    // Telem's real case, after the transcript: he walks to the learner's desk and the case search holds the source and trace.
    { t: T + 13.5, k: "agent.move", agent: "telem", to: "learner", task: t, why: "the verdict is in, so Telem can bring a real case", data: { from: "shelves", place: "learner_desk" } },
    { t: T + 14, k: "sponsor.call", agent: "system", why: "the librarian finds real cases with Telem AI", data: { sponsor: "telem", label: "searched for real cases", count: 1, op: "search", by: "telem", ms: 1380, fallback: false, trace } },
    { t: T + 14.5, k: "search", agent: "telem", task: t, why: `this happens in real life: a real case of ${trapLabel(d.key.trap).toLowerCase()}`, text: `Telem found a real case: ${d.caseResult.title}`, data: { phase: "case", trap: d.key.trap, query: d.caseResult.query, cached: false, trace, results: [{ title: d.caseResult.title, url: d.caseResult.url, snippet: d.caseResult.snippet }] } },
    { t: T + 15.5, k: "agent.say", agent: "telem", to: "learner", task: t, why: "share one real case with its source, now that the verdict is in", text: d.realCase, ref: L("case") },
    ...voice(s, T + 15.9, "telem", t, L("case")),
    { t: T + 16.5, k: "agent.move", agent: "riley", to: "learner", task: t, why: "the intern walks over to see who won", data: { from: "riley_desk", place: "learner_desk" } },
    { t: T + 17, k: "agent.move", agent: "telem", task: t, why: "back to the shelves", data: { from: "learner_desk", place: "shelves" } },
    { t: T + 17.5, k: "task.end", agent: "system", task: t, why: "the verdict is in", data: { taskId: t, score: a.score, beatRival: a.score > (d.riley.verdict === d.key.verdict ? 0.4 : 0), trap: d.key.trap, pickReason: d.pickReason, bandit: BANDIT } },
    { t: T + 18.5, k: "mastery.update", agent: "system", task: t, why: `knowledge tracing after ${a.result === "passed" ? "a correct" : "a missed"} answer on ${trapLabel(d.key.trap).toLowerCase()}`, text: `${trapLabel(d.key.trap)} mastery: ${from} to ${to}.`, data: { trap: d.key.trap, from, to, correct: a.result === "passed", attempts: m.attempts + 1, bruinRun: "run-mock-3" } },
    { t: T + 18.6, k: "sponsor.call", agent: "system", why: "the learner model runs as a Bruin asset", data: { sponsor: "bruin", label: "updated the learner model (bkt_mastery)", count: 1, op: "run", by: "system", ms: 2100, fallback: false } },
  );

  // What comes next: the next task, or the end of the session.
  const next = T + 21;
  s.nextAt = next;
  if (s.index + 1 < s.tasks) {
    intro(s, s.index + 1, next);
  } else {
    const total = Math.round((Object.values(s.answers).reduce((n, x) => n + x.score, 0) + a.score) / Math.max(1, Object.keys(s.answers).length + 1) * 100) / 100;
    plan(s, { t: next, k: "session.end", agent: "system", why: s.mode === "judge" ? "judge mode is one task" : "that was the last task in the rotation", data: { tasks: s.tasks, totalScore: total } });
  }
}

// ---- the fake server ----

/** Moves due events into the delivered log (numbering them in time order) and handles time running out. */
function tick(s: Live): Live {
  const now = nowT(s);
  const d = def(s);

  // Time ran out with no answer: the server answers cant_tell for the learner.
  if (!s.ended && s.nextAt === null && !s.answers[d.id] && now >= s.taskT + d.seconds) {
    const r = score(d, { verdict: "cant_tell", trap: "none", evidence: [] });
    const a: Answer = { verdict: "cant_tell", trap: "none", evidence: [], note: "", timedOut: true, score: r.total, result: r.result };
    const T = s.taskT + d.seconds;
    s.answers[d.id] = a;
    plan(s, { t: T, k: "learner.answer", agent: "learner", task: d.id, why: "time ran out, so the server answered cant_tell for the learner", text: "Time ran out, so the answer is: can't tell.", data: { verdict: "cant_tell", trap: "none", note: "", evidence: [], timedOut: true } });
    react(s, d, a, r, T);
  }

  // The next task, or the end, arrives.
  if (s.nextAt !== null && now >= s.nextAt) {
    if (s.index + 1 < s.tasks) s.index += 1;
    else s.ended = true;
    s.nextAt = null;
  }

  // Deliver what is due.
  const due = s.planned.filter((e) => e.t <= now).map((e, i) => ({ e, i })).sort((a, b) => a.e.t - b.e.t || a.i - b.i);
  if (due.length) {
    s.planned = s.planned.filter((e) => e.t > now);
    for (const { e } of due) {
      const { ref, lineOfRef, ...event } = e;
      const seq = s.delivered.length + 1;
      const data = event.data ? { ...event.data } : undefined;
      if (lineOfRef && data) data.lineOf = s.refs[lineOfRef];
      if (event.k === "panel.transcript" && data) {
        data.whispers = (data.whispers as { refSeq: string }[]).map(({ refSeq, ...w }) => ({ seq: s.refs[refSeq], ...w }));
      }
      if (ref) s.refs[ref] = seq;
      s.delivered.push({ ...event, ...(data ? { data } : {}), seq } as LabEvent);
    }
  }
  save(s);
  return s;
}

/** A learner event, at this moment, because the person just did something. */
function byPerson(s: Live, event: Ev) {
  plan(s, { ...event, t: nowT(s) });
}

function fresh(options?: StartOptions): Live {
  const mode = options?.mode === "judge" ? "judge" : "rotation";
  const s: Live = {
    mode, learner: options?.learner ?? (mode === "judge" ? "guest" : "you"), start: Date.now(), tasks: mode === "judge" ? 1 : 3, index: 0, taskT: 1, nextAt: null,
    ended: false, planned: [], delivered: [], refs: {}, answers: {}, queries: 0, appeals: 0, files: 0, traces: 0, hash: "000000000000",
    mastery: Object.fromEntries(["duplicate_rows", "unit_mismatch", "dictionary_flip", "confounder", "hidden_variable", "none"].map((t) => [t, { score: 0.15, attempts: 0 }])),
  };
  // A new session starts clean: forget the workspace's saved drafts and task clocks from any earlier one.
  try {
    Object.keys(sessionStorage).filter((k) => k.startsWith("lab-rotation.workspace.")).forEach((k) => sessionStorage.removeItem(k));
  } catch {
    /* ignore */
  }
  intro(s, 0, 1);
  return s;
}

const session = (): Live => {
  const s = load();
  if (!s) throw new Error("No session yet. Start one first.");
  return tick(s);
};

export const live = {
  start(options?: StartOptions): SessionInfo {
    const wanted = options?.mode === "judge" ? "judge" : "rotation";
    let s = load();
    if (!s || s.mode !== wanted) s = fresh(options);
    s = tick(s);
    return { sessionId: "mock-session", tasks: DEFS.slice(0, s.tasks).map(({ id, title }) => ({ id, title })), task: s.ended ? null : pub(def(s)) };
  },

  currentTask(): CurrentTask {
    const s = session();
    return { task: s.ended ? null : pub(def(s)) };
  },

  events(since: number): EventsPage {
    const s = session();
    const events = s.delivered.filter((e) => e.seq > since);
    return { events, next: events.length ? events[events.length - 1].seq : since };
  },

  allEvents: (): LabEvent[] => (load() ? tick(load()!).delivered : []),

  sponsors: (): SponsorTotals => sponsorTotals(load() ? tick(load()!).delivered : []),

  mastery(): Mastery {
    const s = load() ?? fresh();
    return { traps: Object.entries(s.mastery).map(([trap, m]) => ({ trap: trap as TrapId, score: m.score, attempts: m.attempts })) };
  },

  /** The person ran a query. */
  query(sql: string, ok: boolean, rowCount: number, ms: number, error?: string) {
    const s = session();
    if (s.ended || s.answers[def(s).id] || s.nextAt !== null) return;
    s.queries += 1;
    byPerson(s, { t: 0, k: "learner.query", agent: "learner", task: def(s).id, why: ok ? "the learner ran a query in the SQL box" : "the query failed", text: sql, data: { queryId: `q${s.queries}`, sql, ok, rowCount, ms, ...(error ? { error } : {}) } });
    save(s);
  },

  /** The person sent an answer. The panel compares it with the key and replies to what was actually said. */
  answer(a: AnswerSubmission): { accepted: boolean } {
    const s = session();
    const d = def(s);
    if (s.ended || a.taskId !== d.id || s.answers[d.id]) return { accepted: true };
    const r = score(d, a);
    const ans: Answer = { verdict: a.verdict, trap: a.trap, evidence: a.evidence, note: a.note, timedOut: false, score: r.total, result: r.result };
    s.answers[d.id] = ans;
    const T = nowT(s);
    if (a.evidence.length) byPerson(s, { t: 0, k: "learner.evidence", agent: "learner", task: d.id, why: "the learner cited these items in their answer", data: { action: "add", items: a.evidence } });
    byPerson(s, { t: 0, k: "learner.answer", agent: "learner", task: d.id, why: "the learner submitted an answer", text: `The learner answered: ${a.verdict}, ${trapLabel(a.trap).toLowerCase()}.`, data: { verdict: a.verdict, trap: a.trap, note: a.note, evidence: a.evidence } });
    react(s, d, ans, r, T);
    save(s);
    tick(s);
    return { accepted: true };
  },

  /** The person opened an appeal. The panel looks at it and rules. */
  appeal(taskId: string, reason: string): { appealId: string } {
    const s = session();
    s.appeals += 1;
    const appealId = `a${s.appeals}`;
    const T = nowT(s);
    const d = DEFS.find((x) => x.id === taskId) ?? def(s);
    const a = s.answers[d.id];
    byPerson(s, { t: 0, k: "appeal.open", agent: "learner", task: d.id, why: "the learner asked the panel to look at the grade again", text: "The learner appealed.", data: { appealId, taskId: d.id, reason, room: "local" } });
    plan(s,
      band(T + 0.3, "system", "relayed the appeal into the panel room"),
      { t: T + 3, k: "appeal.message", agent: "sam", to: "learner", task: d.id, why: "Sam reports what the log shows", text: "The log shows what you cited and when. The panel is reading it now.", data: { appealId, text: "The log shows what you cited and when. The panel is reading it now.", bandMessageId: `band-mock-${appealId}-1` } },
      { t: T + 7, k: "appeal.ruling", agent: "ines", task: d.id, why: "the answer key and the failing check agree with the grade", text: "Appeal ruled: the grade stands.", data: { appealId, upheld: true, oldScore: a?.score ?? 0, newScore: a?.score ?? 0, reason: "The key and the failing check both support the original grade, so it stands." } },
    );
    save(s);
    return { appealId };
  },

  appealMessage(appealId: string, text: string) {
    const s = session();
    byPerson(s, { t: 0, k: "appeal.message", agent: "learner", to: "ines", task: def(s).id, why: "the learner added to their appeal", text, data: { appealId, text } });
    save(s);
  },

  /** The person asked an agent a question. Each agent answers only from what it could see. Telem runs a live search and adds links and a trace. */
  ask(q: AskRequest): AskReply {
    const s = session();
    const d = def(s);
    const sees: Record<AgentId, { text: string; sources: string[] }> = {
      vale: { text: `You were new, so every skill sat at 0.15, and the pick was ${d.pickReason}.`, sources: ["your learner profile", "the task pick"] },
      sam: { text: "I can see what you have queried and cited. I can't see the answer key, so I can't say if you are right.", sources: ["your queries", "your cited items"] },
      telem: { text: "", sources: [] },
      ines: { text: "I keep the answer key, so I can't discuss the answer before the verdict.", sources: ["the lab's rules"] },
      riley: { text: "I work on my own and can't share my work while you are on the task.", sources: [] },
      learner: { text: "That's you.", sources: [] },
      system: { text: "", sources: [] },
    };
    let r: AskReply = { agent: q.agent, ...(sees[q.agent] ?? sees.vale) };
    const T = nowT(s);
    if (q.agent === "telem") {
      // Telem searches with the learner's question alone and builds its answer from the results.
      const trace = `https://app.telem.ai/traces/mock-${++s.traces}`;
      const links = [
        { title: "How retailers report spend per visit for loyalty members", url: "https://example.com/mock-ask-loyalty-spend" },
        { title: "Comparing customer groups: what to check before you trust an average", url: "https://example.com/mock-ask-compare-groups" },
      ];
      r = {
        agent: "telem",
        text: "I searched for your question. The results cover how teams usually compare spend between customer groups and what they check first. The sources and the trace are below.",
        sources: ["a live Telem search with your question"],
        links,
        trace,
      };
      plan(s, { t: T + 0.8, k: "sponsor.call", agent: "system", why: "Telem searches live to answer the learner's question", data: { sponsor: "telem", label: "searched to answer a question", count: 1, op: "search", by: "telem", ms: 1210, fallback: false, trace } });
    }
    byPerson(s, { t: 0, k: "ask", agent: "learner", to: q.agent, task: d.id, why: `the learner asked ${q.agent} a question`, text: q.text });
    plan(s, { t: T + 1.5, k: "ask.answer", agent: q.agent, to: "learner", task: d.id, why: `answered only from what ${q.agent} could see`, text: r.text, data: { sources: r.sources, ...(r.links ? { links: r.links, trace: r.trace } : {}) } });
    save(s);
    return r;
  },
};
