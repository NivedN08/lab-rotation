import type { LabEvent, SponsorTotals } from "./types";

/**
 * Adds events up into the sponsor strip's totals. Works on any slice of a session, so it follows a demo's seek and rewind.
 * Live, the server's own totals (GET /sponsors) are used; this is for replays.
 *
 * - BAND: every `sponsor.call` from band is one message.
 * - Telem: searches are `sponsor.call`s with op `search`; monitor hits are `monitor.hit` events; traces are the `trace` links.
 * - Bruin: checks are `check.result` events (each has `passed`); `sponsor.call`s with op `run` load or update data and are not checks.
 * - Runware: voice lines are `sponsor.call`s with op `tts`; cost is every Runware call's `cost`.
 * - Glasser and Teamily: one per call.
 */
export function sponsorTotals(events: LabEvent[]): SponsorTotals {
  const t: SponsorTotals = {
    band: { messages: 0 },
    telem: { searches: 0, monitorHits: 0, traces: [] },
    bruin: { checksRun: 0, checksFailed: 0 },
    runware: { lines: 0, cost: 0 },
    glasser: { calls: 0 },
    teamily: { posts: 0 },
  };
  for (const e of events) {
    if (e.k === "monitor.hit") t.telem.monitorHits++;
    if (e.k === "check.result") {
      t.bruin.checksRun++;
      if ((e.data as { passed?: boolean } | undefined)?.passed === false) t.bruin.checksFailed++;
    }
    if (e.k !== "sponsor.call") continue;
    const d = e.data as { sponsor: string; op?: string; count?: number; cost?: number; trace?: string };
    const n = d.count ?? 1;
    if (d.sponsor === "band") t.band.messages += n;
    if (d.sponsor === "telem") {
      if (d.op === "search") t.telem.searches += n;
      if (d.trace && !t.telem.traces.includes(d.trace)) t.telem.traces.push(d.trace);
    }
    if (d.sponsor === "runware") {
      if (d.op === "tts") t.runware.lines += n;
      t.runware.cost = Math.round((t.runware.cost + (d.cost ?? 0)) * 1e6) / 1e6;
    }
    if (d.sponsor === "glasser") t.glasser.calls += n;
    if (d.sponsor === "teamily") t.teamily!.posts += n;
  }
  return t;
}
