import { useMemo, useState } from "react";
import type { LabEvent } from "../api/types";
import { describeLive, fmtElapsed, type Replay } from "../sim/replay";
import type { Target } from "../world/engine";

/** The last few things that happened, in plain words. Click one to go to whoever did it. */
/** `compact` (judge mode, while playing): only the latest line, kept short; click it for the why. */
export function LabLog({ R, t, filter, select, live = [], compact = false }: { R: Replay; t: number; filter: string | null; select: (t: Target) => void; live?: LabEvent[]; compact?: boolean }) {
  const [openWhy, setOpenWhy] = useState<number | null>(null);
  // During a rotation the log shows the session's events, in the backend's own words.
  const liveLines = useMemo(() => {
    const out: { e: LabEvent; text: string; why: string; tone?: string }[] = [];
    const seen = live.filter((e) => e.t <= t + 0.5); // scrubbed back: only what had happened by then
    for (const e of seen) {
      const d = describeLive(e, seen);
      if (d && out[out.length - 1]?.text !== d.text) out.push({ e, ...d });
    }
    return out.slice(-3);
  }, [live, t]);
  const described = useMemo(
    () =>
      R.run.events
        .map((e) => ({ e, d: R.describe(e) }))
        .filter((x) => x.d && !["memory.write"].includes(x.e.k)),
    [R],
  );
  if (liveLines.length && compact) {
    const { e, text, why, tone } = liveLines[liveLines.length - 1];
    // Lines spoken to you (Telem's background, Sam's question) show in full; the rest stay short.
    const toYou = e.to === "learner";
    const short = !toYou && text.length > 90 ? `${text.slice(0, 88).replace(/\s+\S*$/, "")}…` : text;
    const open = openWhy === e.seq;
    return (
      <div className="log" aria-label="Lab log">
        <button className={tone ?? ""} onClick={() => setOpenWhy(open ? null : e.seq)} aria-expanded={open} title={why ? "Why?" : undefined}>
          <time>{fmtElapsed(e.t)}</time>
          <span>
            {open ? text : short}
            {open && why && <small className="why">Why: {why}</small>}
          </span>
        </button>
      </div>
    );
  }
  if (liveLines.length) {
    return (
      <div className="log" aria-label="Lab log">
        {liveLines.map(({ e, text, why, tone }) => {
          const who = R.liveAgent(e.agent);
          return (
            <button key={e.seq} className={tone ?? ""} onClick={() => who && select({ type: "agent", id: who })}>
              <time>{fmtElapsed(e.t)}</time>
              <span>
                {text}
                {why && <small className="why">Why: {why}</small>}
              </span>
            </button>
          );
        })}
      </div>
    );
  }
  const recent = [];
  for (let i = described.length - 1; i >= 0 && recent.length < 3; i--) {
    const x = described[i];
    if (R.timeOf(x.e) > t) continue;
    if (filter && x.e.s && x.e.s !== filter) continue;
    if (t - R.timeOf(x.e) > 240) break;
    recent.push(x);
  }
  recent.reverse();
  return (
    <div className="log" aria-label="Lab log">
      {recent.map(({ e, d }, i) => (
        <button
          key={`${e.t}-${e.k}-${i}`}
          className={d!.tone ?? ""}
          onClick={() => {
            if (d!.who) select({ type: "agent", id: d!.who });
            else if (e.s) select({ type: "study", id: e.s });
          }}
        >
          <time>{fmtElapsed(R.timeOf(e))}</time>
          <span>{d!.text}</span>
        </button>
      ))}
    </div>
  );
}
