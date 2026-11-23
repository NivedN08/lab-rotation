// A fake session that plays one full task in about two minutes, served through getEvents like the real server will.
// Every event kind the floor needs appears at least once, in a sensible order.
// Add ?mockspeed=10 to the URL to play it ten times faster while testing.

import type { EventsPage, LabEvent } from "./types";

type Step = Omit<LabEvent, "seq">;

const SQL1 = "SELECT sample_id, COUNT(*) FROM samples GROUP BY sample_id HAVING COUNT(*) > 1";
const SQL2 = "SELECT * FROM samples WHERE sample_id = 'S012'";

/** Agent ids are provisional: learner, vale, ines, sam, telem, riley. */
export const SCRIPT: Step[] = [
  { t: 0, k: "session.start", a: "learner", text: "You arrive at the lab." },
  { t: 4, k: "task.picked", a: "vale", text: "Dr. Vale hands you Task 1.", data: { taskId: "t1" } },
  { t: 6, k: "voice.line", a: "vale", text: "Welcome. Check the data before you trust the claim.", data: { audio: null } },
  { t: 12, k: "search", a: "telem", text: "Telem searches for how expression levels are normalised.", data: { query: "TPM vs FPKM comparability", results: 3, trace: "trace://telem/1" } },
  { t: 12, k: "sponsor.call", data: { sponsor: "telem", label: "Search", count: 1, trace: "trace://telem/1" } },
  { t: 18, k: "monitor.hit", a: "telem", text: "Telem's monitor caught a new post on mixing TPM and FPKM.", data: { source: "monitor", trace: "trace://telem/2" } },
  { t: 18, k: "sponsor.call", data: { sponsor: "telem", label: "Monitor hit", count: 1, trace: "trace://telem/2" } },
  { t: 24, k: "learner.query", a: "learner", text: "You look for repeated samples.", data: { sql: SQL1 } },
  { t: 30, k: "learner.evidence", a: "learner", text: "You cite samples, row 12.", data: { label: "samples, row 12 (S012, lung, control, ...)" } },
  { t: 36, k: "agent.say", a: "sam", text: "Have you checked whether any sample appears more than once?", data: { hint: true } },
  { t: 40, k: "voice.line", a: "sam", text: "Have you checked whether any sample appears more than once?", data: { audio: null } },
  { t: 44, k: "panel.whisper", a: "vale", to: "ines", text: "The learner is close. Hold the checks until they answer." },
  { t: 44, k: "sponsor.call", data: { sponsor: "band", label: "Message", count: 1 } },
  { t: 48, k: "panel.whisper", a: "ines", to: "sam", text: "Keep hints to one question." },
  { t: 48, k: "sponsor.call", data: { sponsor: "band", label: "Message", count: 1 } },
  { t: 56, k: "learner.query", a: "learner", text: "You open the repeated sample.", data: { sql: SQL2 } },
  { t: 66, k: "learner.evidence", a: "learner", text: "You cite the repeated sample's second row.", data: { label: "samples, row 121 (S012, lung, control, ...)" } },
  { t: 76, k: "learner.answer", a: "learner", text: "You answer: the claim fails. Duplicated rows.", data: { verdict: "fails", trap: "Duplicated rows" } },
  { t: 80, k: "rival.answer", a: "riley", text: "Riley answers: the claim fails. Duplicated rows.", data: { verdict: "fails", trap: "Duplicated rows" } },
  { t: 86, k: "check.result", a: "ines", text: "Duplicates check failed.", data: { check: "duplicates", passed: false } },
  { t: 86, k: "sponsor.call", data: { sponsor: "bruin", label: "Check run", count: 1, failed: 1 } },
  { t: 90, k: "sponsor.call", data: { sponsor: "glasser", label: "Call", count: 1 } },
  { t: 94, k: "verdict", a: "ines", text: "Verdict: you found the trap. Sealed.", data: { correct: true, key: "fails", trap: "Duplicated rows", sealed: true } },
  { t: 100, k: "mastery.update", a: "learner", text: "Duplicated rows: 40% to 60%.", data: { trap: "Duplicated rows", from: 0.4, to: 0.6 } },
  { t: 104, k: "voice.line", a: "vale", text: "Good catch. The same sample was entered twice.", data: { audio: null } },
  { t: 104, k: "sponsor.call", data: { sponsor: "runware", label: "Voice line", count: 1, cost: 0.004 } },
  { t: 110, k: "appeal.open", a: "learner", text: "You appeal: Riley's evidence was the same as mine.", data: { appealId: "mock-appeal" } },
  { t: 114, k: "appeal.message", a: "learner", to: "vale", text: "Both answers cite the same row.", data: { appealId: "mock-appeal" } },
  { t: 118, k: "sponsor.call", data: { sponsor: "band", label: "Message", count: 1 } },
  { t: 122, k: "appeal.ruling", a: "ines", text: "Ruling: your verdict stands.", data: { appealId: "mock-appeal", upheld: false } },
];

const KEY = "lab-rotation.mock.session-start";

function started(): number {
  try {
    const saved = Number(sessionStorage.getItem(KEY));
    if (saved) return saved;
    const now = Date.now();
    sessionStorage.setItem(KEY, String(now));
    return now;
  } catch {
    return startFallback;
  }
}
const startFallback = Date.now();

const speed = (): number => {
  try {
    return Number(new URLSearchParams(window.location.search).get("mockspeed")) || 1;
  } catch {
    return 1;
  }
};

/** Everything that has happened so far with seq > since. Pass the previous page's `next`. */
export function scriptedEvents(since: number): EventsPage {
  const elapsed = ((Date.now() - started()) / 1000) * speed();
  const all: LabEventWithSeq[] = SCRIPT.map((s, i) => ({ ...s, seq: i + 1 }));
  const due = all.filter((e) => e.t <= elapsed);
  const events = due.filter((e) => e.seq > since);
  return { events, next: due.length ? due[due.length - 1].seq : since };
}

type LabEventWithSeq = LabEvent & { seq: number };
