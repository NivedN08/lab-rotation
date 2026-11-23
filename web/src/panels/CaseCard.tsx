import { trapLabel, useRotation, type LabEvent, type SearchData } from "../api/client";
import "./panels.css";

const isCase = (e: LabEvent) => e.k === "search" && (e.data as SearchData | undefined)?.phase === "case";

function Link({ href, children }: { href: string; children: React.ReactNode }) {
  return /^https?:/.test(href) ? (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  ) : (
    <span title={href}>{children}</span>
  );
}

/**
 * Telem's real case, from the `case` search that comes right after the verdict: what happened, the source link and the
 * trace link. Draws nothing until that event has arrived. By default it shows the latest case; pass `taskId` for one task's,
 * or `event` to show a particular search event.
 */
export function CaseCard({ taskId, event }: { taskId?: string; event?: LabEvent }) {
  const { events } = useRotation();
  const found = event ?? [...events].reverse().find((e) => isCase(e) && (!taskId || e.task === taskId));
  if (!found) return null;
  const d = found.data as SearchData;
  const [main, ...more] = d.results;
  if (!main) return null;

  return (
    <section className="pn-case box" aria-label="A real case from Telem">
      <div className="pn-case-head">
        <span className="pn-name">Telem</span>
        <h3 className="pn-title">A real case</h3>
        {d.trap && <span className="chip pn-case-trap">{trapLabel(d.trap)}</span>}
      </div>
      <p className="pn-case-what">
        <b>{main.title}</b>
      </p>
      {main.snippet && <p className="pn-case-snippet">{main.snippet}</p>}
      <p className="pn-case-links">
        <Link href={main.url}>Source</Link>
        <Link href={d.trace}>Telem trace</Link>
        {d.cached && <span className="pn-why">from a recorded search</span>}
      </p>
      {more.length > 0 && (
        <ul className="pn-case-more" aria-label="More sources">
          {more.map((r) => (
            <li key={r.url}>
              <Link href={r.url}>{r.title}</Link>
            </li>
          ))}
        </ul>
      )}
      <p className="pn-why">Why: {found.why}</p>
    </section>
  );
}
