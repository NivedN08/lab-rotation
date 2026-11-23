// A fake session that plays one full task, served through getEvents like the real server will.
// Add ?mockspeed=10 to the URL to play it ten times faster while testing.

import raw from "./mock/mock_session.jsonl?raw";
import type { EventsPage, LabEvent } from "./types";

type Step = LabEvent;

// The contract's own mock session (contract/mock_session.jsonl, copied into ./mock/), so sample data has exactly the real format.
export const SCRIPT: Step[] = raw
  .split("\n")
  .filter((l) => l.trim())
  .map((l) => JSON.parse(l) as LabEvent);

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
  const events = SCRIPT;
  return { events, next: events.length };
}

/** Every scripted event that has happened so far, with its seq. */
export function eventsSoFar(): (LabEvent & { seq: number })[] {
  const elapsed = ((Date.now() - started()) / 1000) * speed();
  return SCRIPT.filter((e) => e.t <= elapsed);
}

/** Everything that has happened so far with seq > since. Pass the previous page's `next`. */
export function scriptedEvents(since: number): EventsPage {
  const elapsed = ((Date.now() - started()) / 1000) * speed();
  const all: LabEventWithSeq[] = SCRIPT;
  const due = all.filter((e) => e.t <= elapsed);
  const events = due.filter((e) => e.seq > since);
  return { events, next: due.length ? due[due.length - 1].seq : since };
}

type LabEventWithSeq = LabEvent & { seq: number };
