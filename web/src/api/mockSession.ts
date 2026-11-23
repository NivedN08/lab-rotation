// A fake session that plays one full task in about two minutes, served through getEvents like the real server will.
// Every event kind the floor needs appears at least once, in a sensible order.
// Add ?mockspeed=10 to the URL to play it ten times faster while testing.

import type { EventsPage, LabEvent } from "./types";

type Step = Omit<LabEvent, "seq">;

const SQL1 = "SELECT sample_id, COUNT(*) FROM samples GROUP BY sample_id HAVING COUNT(*) > 1";
const SQL2 = "SELECT * FROM samples WHERE sample_id = 'S012'";

const T = "t1";

export const SCRIPT: Step[] = [
  { t: 0, k: "session.start", agent: "learner", task: T, text: "You arrive at the lab.", why: "A rotation begins when the learner walks in; the clock for the session starts here." },
  { t: 4, k: "task.picked", agent: "vale", to: "learner", task: T, text: "Dr. Vale hands you Task 1.", data: { taskId: T, title: "Task 1", tier: "core", claim: "Treated samples show higher expression than control.", reason: "Duplicated rows is the trap this learner has practised least.", brief: "Does the treated arm really show higher expression? Check the data before you say.", seconds: 600 }, why: "Task 1 is the learner's first untried task, and duplicated rows is a trap they have not been tested on yet." },
  { t: 6, k: "voice.line", agent: "vale", task: T, text: "Welcome. Check the data before you trust the claim.", data: { file: "vale-welcome.wav" }, why: "A short spoken brief sets the tone without giving away which trap is planted." },
  { t: 12, k: "search", agent: "telem", task: T, text: "Telem searches for how expression levels are normalised.", data: { query: "TPM vs FPKM comparability", results: 3, trace: "trace://telem/1" }, why: "The task brief mentions expression levels, so Telem looks up how they are normally compared before anyone drew a conclusion." },
  { t: 12, k: "sponsor.call", agent: "system", task: T, data: { sponsor: "telem", label: "Search", count: 1, trace: "trace://telem/1" }, why: "Counts one Telem search for the sponsor strip." },
  { t: 18, k: "monitor.hit", agent: "telem", task: T, text: "Telem's monitor caught a new post on mixing TPM and FPKM.", data: { source: "monitor", trace: "trace://telem/2" }, why: "A standing monitor on normalisation topics matched a new post, so Telem raised it with the learner." },
  { t: 18, k: "sponsor.call", agent: "system", task: T, data: { sponsor: "telem", label: "Monitor hit", count: 1, trace: "trace://telem/2" }, why: "Counts one Telem monitor hit for the sponsor strip." },
  { t: 24, k: "learner.query", agent: "learner", task: T, text: "You look for repeated samples.", data: { sql: SQL1 }, why: "The learner suspects the same sample was entered twice and groups by sample id to test it." },
  { t: 30, k: "learner.evidence", agent: "learner", task: T, text: "You cite samples, row 12.", data: { label: "samples, row 12 (S012, lung, control, ...)" }, why: "The first repeated sample the query found is worth keeping as evidence." },
  { t: 36, k: "agent.say", agent: "sam", to: "learner", task: T, text: "Have you checked whether any sample appears more than once?", data: { hint: true }, why: "The learner has queried for repeats but not opened one; Sam nudges with a question instead of an answer." },
  { t: 40, k: "voice.line", agent: "sam", task: T, text: "Have you checked whether any sample appears more than once?", data: { file: "sam-hint.wav" }, why: "Sam's hint is voiced so it is not missed while the learner reads tables." },
  { t: 44, k: "panel.whisper", agent: "vale", to: "ines", task: T, text: "The learner is close. Hold the checks until they answer.", why: "Vale tells the referee not to run checks early, so the learner's answer is judged on what they found themselves." },
  { t: 44, k: "sponsor.call", agent: "system", task: T, data: { sponsor: "band", label: "Message", count: 1 }, why: "Counts one BAND message for the sponsor strip." },
  { t: 48, k: "panel.whisper", agent: "ines", to: "sam", task: T, text: "Keep hints to one question.", why: "Ines caps Sam at one hint so the hint stays a nudge and the score stays fair." },
  { t: 48, k: "sponsor.call", agent: "system", task: T, data: { sponsor: "band", label: "Message", count: 1 }, why: "Counts one BAND message for the sponsor strip." },
  { t: 56, k: "learner.query", agent: "learner", task: T, text: "You open the repeated sample.", data: { sql: SQL2 }, why: "After the hint the learner looks at every row for sample S012 to confirm it really is a duplicate." },
  { t: 66, k: "learner.evidence", agent: "learner", task: T, text: "You cite the repeated sample's second row.", data: { label: "samples, row 121 (S012, lung, control, ...)" }, why: "The second copy of S012 is the proof that the same row was entered twice." },
  { t: 76, k: "learner.answer", agent: "learner", task: T, text: "You answer: the claim fails. Duplicated rows.", data: { verdict: "fails", trap: "duplicate_rows" }, why: "Two identical rows for one sample inflate the treated group, so the learner says the claim fails." },
  { t: 80, k: "rival.answer", agent: "riley", task: T, text: "Riley answers: the claim fails. Duplicated rows.", data: { verdict: "fails", trap: "duplicate_rows" }, why: "Riley worked the same task independently and reached the same verdict, so the two answers can be compared." },
  { t: 86, k: "check.result", agent: "ines", task: T, text: "Duplicates check failed.", data: { check: "duplicates", passed: false }, why: "Ines ran the duplicates check on the samples table; it failed, which confirms the learner's evidence." },
  { t: 86, k: "sponsor.call", agent: "system", task: T, data: { sponsor: "bruin", label: "Check run", count: 1, failed: 1 }, why: "Counts one Bruin check run, and that it failed, for the sponsor strip." },
  { t: 90, k: "sponsor.call", agent: "system", task: T, data: { sponsor: "glasser", label: "Call", count: 1 }, why: "Counts one Glasser call made while judging the answer." },
  { t: 94, k: "verdict", agent: "ines", task: T, text: "Verdict: you found the trap. Sealed.", data: { taskId: T, result: "passed", correct: true, key: "fails", trap: "duplicate_rows", sealed: true }, why: "The verdict and the trap both match the key and the failed check backs the cited rows, so the task is passed and sealed." },
  { t: 100, k: "mastery.update", agent: "learner", task: T, text: "Duplicated rows: 40% to 60%.", data: { trap: "duplicate_rows", from: 0.4, to: 0.6 }, why: "A correct catch on a trap the learner had only half mastered raises that trap's score." },
  { t: 104, k: "voice.line", agent: "vale", task: T, text: "Good catch. The same sample was entered twice.", data: { file: "vale-verdict.wav" }, why: "Vale confirms the result out loud so the learner hears what the check found." },
  { t: 104, k: "sponsor.call", agent: "system", task: T, data: { sponsor: "runware", label: "Voice line", count: 1, cost: 0.004 }, why: "Counts one Runware voice line and its cost for the sponsor strip." },
  { t: 110, k: "appeal.open", agent: "learner", task: T, text: "You appeal: Riley's evidence was the same as mine.", data: { appealId: "mock-appeal" }, why: "The learner thinks matching evidence should not count against them and asks the panel to look again." },
  { t: 114, k: "appeal.message", agent: "learner", to: "vale", task: T, text: "Both answers cite the same row.", data: { appealId: "mock-appeal" }, why: "The learner adds the specific reason so the panel has something to rule on." },
  { t: 118, k: "sponsor.call", agent: "system", task: T, data: { sponsor: "band", label: "Message", count: 1 }, why: "Counts one BAND message for the sponsor strip." },
  { t: 122, k: "appeal.ruling", agent: "ines", task: T, text: "Ruling: your verdict stands.", data: { appealId: "mock-appeal", upheld: false }, why: "Matching evidence is expected when the trap is real, and the verdict was already correct, so the ruling leaves it as it was." },
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

/** The whole script as a finished, recorded session: every event, from the beginning. */
export function recordedEvents(): EventsPage {
  const events = SCRIPT.map((s, i) => ({ ...s, seq: i + 1 }));
  return { events, next: events.length };
}

/** Every scripted event that has happened so far, with its seq. */
export function eventsSoFar(): (LabEvent & { seq: number })[] {
  const elapsed = ((Date.now() - started()) / 1000) * speed();
  return SCRIPT.map((s, i) => ({ ...s, seq: i + 1 })).filter((e) => e.t <= elapsed);
}

/** Everything that has happened so far with seq > since. Pass the previous page's `next`. */
export function scriptedEvents(since: number): EventsPage {
  const elapsed = ((Date.now() - started()) / 1000) * speed();
  const all: LabEventWithSeq[] = SCRIPT.map((s, i) => ({ ...s, seq: i + 1 }));
  const due = all.filter((e) => e.t <= elapsed);
  const events = due.filter((e) => e.seq > since);
  return { events, next: due.length ? due[due.length - 1].seq : since };
}

type LabEventWithSeq = LabEvent & { seq: number };
