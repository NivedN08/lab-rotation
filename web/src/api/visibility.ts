import type { LabEvent } from "./types";

/**
 * Whisper words stay hidden until the verdict. A live server never sends them early, but a finished session read from
 * `since=0` has them filled in, so anything that plays a recording runs its events through this first.
 * Up to the verdict: `panel.whisper` loses `data.text`, and `panel.transcript` is dropped. From the verdict on, events pass unchanged.
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
      if (e.k !== "panel.whisper" || !e.data || !("text" in e.data)) return e;
      const { text: _hidden, ...rest } = e.data as Record<string, unknown>;
      return { ...e, data: rest };
    });
}
