import type { LabEvent, SponsorTotals } from "./types";

/** Adds up `sponsor.call` events into the sponsor strip's totals. Works on any slice of a session, so it follows a demo's seek and rewind. */
export function sponsorTotals(events: LabEvent[]): SponsorTotals {
  const t: SponsorTotals = {
    band: { messages: 0 },
    telem: { searches: 0, monitorHits: 0, traces: [] },
    bruin: { checksRun: 0, checksFailed: 0 },
    runware: { lines: 0, cost: 0 },
    glasser: { calls: 0 },
  };
  for (const e of events) {
    if (e.k !== "sponsor.call") continue;
    const d = e.data as { sponsor: string; label?: string; count?: number; failed?: number; cost?: number; trace?: string };
    const n = d.count ?? 1;
    if (d.sponsor === "band") t.band.messages += n;
    if (d.sponsor === "telem") {
      if (d.label === "Monitor hit") t.telem.monitorHits += n;
      else t.telem.searches += n;
      if (d.trace) t.telem.traces.push(d.trace);
    }
    if (d.sponsor === "bruin") {
      t.bruin.checksRun += n;
      t.bruin.checksFailed += d.failed ?? 0;
    }
    if (d.sponsor === "runware") {
      t.runware.lines += n;
      t.runware.cost = Math.round((t.runware.cost + (d.cost ?? 0)) * 1e6) / 1e6;
    }
    if (d.sponsor === "glasser") t.glasser.calls += n;
  }
  return t;
}
