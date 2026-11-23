import { useMemo } from "react";
import type { LabEvent } from "../api/types";
import { describeLive, fmtElapsed, type Replay } from "../sim/replay";
import type { Target } from "../world/engine";

/** The last few things that happened, in plain words. Click one to go to whoever did it. */
export function LabLog({ R, t, filter, select, live = [] }: { R: Replay; t: number; filter: string | null; select: (t: Target) => void; live?: LabEvent[] }) {
  // During a rotation the log shows the session's events, in the backend's own words.
  const liveLines = useMemo(() => {
    const out: { e: LabEvent; text: string; tone?: string }[] = [];
    for (const e of live) {
      const d = describeLive(e);
      if (d && out[out.length - 1]?.text !== d.text) out.push({ e, ...d });
    }
    return out.slice(-3);
  }, [live]);
  const described = useMemo(
    () =>
      R.run.events
        .map((e) => ({ e, d: R.describe(e) }))
        .filter((x) => x.d && !["memory.write"].includes(x.e.k)),
    [R],
  );
  if (liveLines.length) {
    return (
      <div className="log" aria-label="Lab log">
        {liveLines.map(({ e, text, tone }) => {
          const who = R.liveAgent((e as { a?: string }).a);
          return (
            <button key={e.seq} className={tone ?? ""} onClick={() => who && select({ type: "agent", id: who })}>
              <time>{fmtElapsed(e.t)}</time>
              <span>{text}</span>
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
