import { useEffect, useState } from "react";
import { atLeast, getSponsors, sponsorTotals, useDemo, useRotation, type SponsorTotals } from "../api/client";
import "./panels.css";

/** A number that flashes when it changes. */
function Num({ v, children }: { v: string | number; children?: React.ReactNode }) {
  return (
    <b key={String(v)} className="pn-num">
      {children ?? v}
    </b>
  );
}

function Trace({ href, i }: { href: string; i: number }) {
  return /^https?:/.test(href) ? (
    <a href={href} target="_blank" rel="noreferrer">
      trace {i + 1}
    </a>
  ) : (
    <span title={href}>trace {i + 1}</span>
  );
}

/**
 * Thin bar of sponsor totals. Refreshes whenever the shared poll brings a sponsor.call event.
 * Live, the totals come from the server; in the demo they are added up from the events so far, so they follow seek and rewind.
 */
export function SponsorStrip() {
  const { sessionId, events } = useRotation();
  const watching = useDemo().status !== "off";
  const calls = events.filter((e) => e.k === "sponsor.call").length;
  const [served, setServed] = useState<SponsorTotals | null>(null);

  useEffect(() => {
    if (!sessionId || watching) return;
    let live = true;
    getSponsors(sessionId)
      .then((t) => live && setServed(t))
      .catch(() => live && setServed(null));
    return () => {
      live = false;
    };
  }, [sessionId, calls, watching]);

  // The server's totals can trail the events already received, so they are never shown lower than what the events add up to.
  const folded = sponsorTotals(events);
  const t = watching || !served ? folded : atLeast(served, folded);
  // And a count is never lower than the trace links shown beside it.
  const searches = Math.max(t.telem.searches, t.telem.traces.length);
  const plural = (n: number, w: string) => (n === 1 ? w : w.endsWith("ch") ? `${w}es` : `${w}s`);

  return (
    <div className="pn-strip" role="region" aria-label="Sponsor totals">
      <span className="pn-item">
        <span className="pn-name">BAND</span>
        <Num v={t.band.messages} /> {plural(t.band.messages, "message")}
      </span>
      <span className="pn-item">
        <span className="pn-name">Telem</span>
        <Num v={searches} /> {plural(searches, "search")}
        {t.telem.traces.length > 0 && (
          <span className="pn-traces">
            {t.telem.traces.map((h, i) => (
              <Trace key={h} href={h} i={i} />
            ))}
          </span>
        )}
      </span>
      <span className="pn-item">
        <span className="pn-name">Bruin</span>
        <Num v={t.bruin.checksRun} /> {plural(t.bruin.checksRun, "check")} run,{" "}
        <Num v={t.bruin.checksFailed}>
          <span className={t.bruin.checksFailed ? "pn-bad" : undefined}>{t.bruin.checksFailed}</span>
        </Num>{" "}
        failed
      </span>
      <span className="pn-item">
        <span className="pn-name">Runware</span>
        <Num v={t.runware.lines} /> {plural(t.runware.lines, "line")}, <Num v={t.runware.cost}>${t.runware.cost.toFixed(3)}</Num>
      </span>
      <span className="pn-item">
        <span className="pn-name">Glasser</span>
        <Num v={t.glasser.calls} /> {plural(t.glasser.calls, "call")}
      </span>
    </div>
  );
}
