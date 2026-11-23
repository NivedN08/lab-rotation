import { useEffect, useState } from "react";
import { getMastery, getRecordedEvents, TRAPS, trapLabel, useDemo, useRotation, type Mastery, type TrapId } from "../api/client";
import "./panels.css";

const level = (s: number) => (s < 0.34 ? "low" : s < 0.67 ? "mid" : "high");

/**
 * One bar per trap type, from the learner's mastery. Fits a Details panel (default) or the results card (`compact`).
 * Refreshes when a verdict or a mastery.update event arrives. In the demo, a trap shows its "from" score until the recording reaches the update.
 */
export function MasteryChart({ compact = false }: { compact?: boolean }) {
  const { sessionId, events } = useRotation();
  const demo = useDemo();
  // Refresh when the verdict arrives as well as on the mastery update itself.
  const updates = events.filter((e) => e.k === "mastery.update" || e.k === "verdict").length;
  const [data, setData] = useState<Mastery | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!sessionId) return;
    let live = true;
    setError("");
    getMastery(sessionId)
      .then((m) => live && setData(m))
      .catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
  }, [sessionId, updates]);

  if (error) return <p className="pn-error pn-msg" role="alert">{error}</p>;
  if (!data) return <p className="empty" role="status">Loading mastery…</p>;

  const score: Record<string, number> = Object.fromEntries(data.traps.map((t) => [t.trap, t.score]));
  const seen = new Map<string, { from: number; to: number }>();
  for (const e of events) {
    const d = e.data as { trap?: string; from?: number; to?: number } | undefined;
    if (e.k === "mastery.update" && d?.trap && d.to !== undefined) seen.set(d.trap, { from: d.from ?? d.to, to: d.to });
  }
  // The server's mastery is as of now; in a replay, show it as of the recording's clock.
  if (demo.status === "ready") {
    for (const e of getRecordedEvents()) {
      const d = e.data as { trap?: string; from?: number; to?: number } | undefined;
      if (e.k === "mastery.update" && d?.trap && !seen.has(d.trap) && d.from !== undefined) score[d.trap] = d.from;
    }
  }
  for (const [trap, u] of seen) score[trap] = u.to;

  return (
    <ul className={`pn-mastery${compact ? " compact" : ""}`} aria-label="Mastery by trap type">
      {TRAPS.map((t) => {
        const s = Math.max(0, Math.min(1, score[t.id as TrapId] ?? 0));
        const u = seen.get(t.id);
        const tries = data.traps.find((x) => x.trap === t.id)?.attempts ?? 0;
        return (
          <li key={t.id}>
            <span className="pn-trap" title={trapLabel(t.id)}>
              {trapLabel(t.id)}
            </span>
            <span
              className="pn-track"
              role="img"
              aria-label={`${trapLabel(t.id)}: ${Math.round(s * 100)} percent${tries ? `, ${tries} tries` : ", not tried yet"}`}
            >
              <span className={`pn-fill ${level(s)}`} style={{ width: `${s * 100}%` }} />
            </span>
            <span className="pn-pct">
              {Math.round(s * 100)}%
              {u && u.to !== u.from && <span className={`pn-delta ${u.to > u.from ? "up" : "down"}`}>{u.to > u.from ? "+" : "−"}{Math.abs(Math.round((u.to - u.from) * 100))}</span>}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
