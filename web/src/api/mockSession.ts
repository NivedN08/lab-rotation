// A fake session that plays one full task, served through getEvents like the real server will.
// Add ?mockspeed=10 to the URL to play it ten times faster while testing.

import raw from "./mock/mock_session.jsonl?raw";
import taskJson from "./mock/task.json";
import { withholdWhispers } from "./visibility";
import type { EventsPage, LabEvent } from "./types";

type Step = LabEvent;

// The contract's own mock session (contract/mock_session.jsonl, copied into ./mock/), so sample data has the real format.
// `upgrade` brings it up to the contract's latest announced shape where the copied file is older. Each step does
// nothing once the file already has the change, so syncing a newer contract file is safe.
const rawEvents = raw
  .split("\n")
  .filter((l) => l.trim())
  .map((l) => JSON.parse(l) as LabEvent);

function upgrade(events: LabEvent[]): LabEvent[] {
  const list: (LabEvent & { orig?: number })[] = events.map((e) => ({ ...e, orig: e.seq }));
  const verdict = list.find((e) => e.k === "verdict");
  const taskId = (verdict?.data as { taskId?: string } | undefined)?.taskId;

  // task.picked carries the data dictionary, the same as GET /task.
  const picked = list.find((e) => e.k === "task.picked");
  if (picked?.data && !("dictionary" in picked.data)) picked.data = { ...picked.data, dictionary: (taskJson as { dictionary?: string }).dictionary };

  // Whisper words move out of panel.whisper into a panel.transcript sent right after the verdict.
  if (verdict && !list.some((e) => e.k === "panel.transcript")) {
    const whispers = list
      .filter((e) => e.k === "panel.whisper" && (e.data as { text?: string } | undefined)?.text)
      .map((e) => ({ seq: e.orig as number, agent: e.agent, to: e.to, text: (e.data as { text: string }).text }));
    for (const e of list) {
      if (e.k === "panel.whisper" && e.data) {
        const { text: _t, ...rest } = e.data as Record<string, unknown>;
        e.data = rest;
      }
    }
    list.push({
      seq: 0,
      t: verdict.t + 0.1,
      k: "panel.transcript",
      agent: "system",
      why: "the verdict is in, so the panel's private messages can be shown",
      task: taskId,
      data: { whispers },
    });
  }

  // A few more walks, so every place on the floor is used: the learner comes in and leaves, the panel breaks up.
  const move = (t: number, agent: LabEvent["agent"], from: string, place: string, why: string, to?: LabEvent["agent"]) =>
    list.push({ seq: 0, t, k: "agent.move", agent, to, task: taskId, why, data: { from, place } });
  if (!list.some((e) => e.k === "agent.move" && e.agent === "learner")) {
    move(0.8, "learner", "door", "learner_desk", "the learner walks in and sits down to start the task");
    move(214, "vale", "panel_table", "vale_office", "the panel is done, so Vale goes back to the office");
    move(214.2, "sam", "panel_table", "whiteboard", "the panel is done, so Sam goes back to the whiteboard");
    move(254, "learner", "learner_desk", "door", "the rotation is over, so the learner leaves");
  }

  // Number the events in time order and keep the references between events pointing at the right ones.
  const sorted = list.map((e, i) => ({ e, i })).sort((x, y) => x.e.t - y.e.t || x.i - y.i).map((x) => x.e);
  const seqOf = new Map<number, number>();
  sorted.forEach((e, i) => {
    e.seq = i + 1;
    if (e.orig !== undefined) seqOf.set(e.orig, e.seq);
  });
  for (const e of sorted) {
    const d = e.data as { lineOf?: number; whispers?: { seq: number }[] } | undefined;
    if (d?.lineOf !== undefined) d.lineOf = seqOf.get(d.lineOf) ?? d.lineOf;
    if (e.k === "panel.transcript" && d?.whispers) for (const w of d.whispers) w.seq = seqOf.get(w.seq) ?? w.seq;
    delete e.orig;
  }
  return sorted;
}

export const SCRIPT: Step[] = upgrade(rawEvents);

// The sample session's clock. It runs at normal speed from the first look, and `hurry()` speeds it up after the
// learner submits, so the verdict theatre does not take minutes. Kept in sessionStorage so a reload does not restart it.
const KEY = "lab-rotation.mock.clock";
type Clock = { anchor: number; base: number; rate: number };
let memory: Clock = { anchor: Date.now(), base: 0, rate: 1 };

function clock(): Clock {
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY) ?? "null") as Clock | null;
    if (saved && typeof saved.anchor === "number") return saved;
    sessionStorage.setItem(KEY, JSON.stringify(memory));
  } catch {
    /* keep it in memory */
  }
  return memory;
}

const speed = (): number => {
  try {
    return Number(new URLSearchParams(window.location.search).get("mockspeed")) || 1;
  } catch {
    return 1;
  }
};

/** Seconds into the sample session right now. */
export function elapsedNow(): number {
  const c = clock();
  return c.base + ((Date.now() - c.anchor) / 1000) * c.rate * speed();
}

/** Play the rest of the sample session faster (after the learner submits). */
export function hurry(rate = 8) {
  const c: Clock = { anchor: Date.now(), base: elapsedNow(), rate };
  memory = c;
  try {
    sessionStorage.setItem(KEY, JSON.stringify(c));
  } catch {
    /* keep it in memory */
  }
}

/** When the sample task's verdict is in (its `task.end`), in session seconds. */
export const taskEndTime = (): number => SCRIPT.find((e) => e.k === "task.end")?.t ?? SCRIPT[SCRIPT.length - 1].t;

/** The whole script as a finished, recorded session: every event, from the beginning. */
export function recordedEvents(): EventsPage {
  const events = SCRIPT;
  return { events, next: events.length };
}

/** Every scripted event that has happened so far, with its seq. */
export function eventsSoFar(): (LabEvent & { seq: number })[] {
  return withholdWhispers(SCRIPT.filter((e) => e.t <= elapsedNow()));
}

/** Everything that has happened so far with seq > since. Pass the previous page's `next`. */
export function scriptedEvents(since: number): EventsPage {
  // The server never sends whisper words before the verdict; neither does the sample.
  const due: LabEventWithSeq[] = withholdWhispers(SCRIPT.filter((e) => e.t <= elapsedNow()));
  const events = due.filter((e) => e.seq > since);
  return { events, next: due.length ? due[due.length - 1].seq : since };
}

type LabEventWithSeq = LabEvent & { seq: number };
