import type { LabEvent } from "./types";

/**
 * Whisper words stay hidden until the verdict. A live server never sends them early, but a finished session read from
 * `since=0` has them filled in, so anything that plays a recording runs its events through this first.
 * Up to the verdict: `panel.whisper` loses `data.text` (and is marked `sealed`), `learner.query` loses `data.useful` (it names the
 * columns that matter, so the server holds it back too), and `panel.transcript` is dropped. From the verdict on, events pass unchanged.
 *
 * Pass the events in time order, from the start up to "now", so the verdict is among them once it has played.
 */
export function withholdWhispers(events: LabEvent[]): LabEvent[] {
  return events.some((e) => e.k === "verdict") ? events : hideWhispers(events);
}

/** The same, whether or not a verdict is among the events. For readers that must never show whisper words. */
export function hideWhispers(events: LabEvent[]): LabEvent[] {
  return events
    .filter((e) => e.k !== "panel.transcript")
    .map((e) => {
      const d = e.data as Record<string, unknown> | undefined;
      if (e.k === "panel.whisper" && d && "text" in d) {
        const { text: _hidden, ...rest } = d;
        return { ...e, data: { ...rest, sealed: true } };
      }
      if (e.k === "learner.query" && d && "useful" in d) {
        const { useful: _hidden, ...rest } = d;
        return { ...e, data: rest };
      }
      return e;
    });
}
