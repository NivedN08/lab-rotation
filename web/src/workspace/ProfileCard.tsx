import type { ColumnProfile } from "../api/client";
import { show } from "./evidence";

const pct = (n: number, of: number) => (of ? `${Math.round((n / of) * 100)}%` : "0%");

/** The profile of one column: how many rows, how many missing, how many different values, the range and the common values. */
export function ProfileCard({ profile, onClose }: { profile: ColumnProfile; onClose: () => void }) {
  const p = profile;
  const max = Math.max(1, ...p.top.map((t) => t.count));
  const stats: [string, string][] = [
    ["Rows", String(p.count)],
    ["Missing", `${p.nulls} (${pct(p.nulls, p.count)})`],
    ["Different values", String(p.distinct)],
    ...(p.min !== undefined ? ([["Lowest", show(p.min)]] as [string, string][]) : []),
    ...(p.max !== undefined ? ([["Highest", show(p.max)]] as [string, string][]) : []),
    ...(p.mean !== undefined ? ([["Average", String(p.mean)]] as [string, string][]) : []),
  ];
  return (
    <section className="ws-profile box" aria-label={`Profile of ${p.column}`}>
      <div className="ws-profile-head">
        <h3 className="ws-title">{p.column}</h3>
        <span className="ws-type">{p.type}</span>
        <button className="btn quiet icon" aria-label="Close profile" onClick={onClose}>
          ×
        </button>
      </div>
      <dl className="ws-stats">
        {stats.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      {p.nulls > 0 && p.nulls / p.count >= 0.05 && <p className="ws-flag">{pct(p.nulls, p.count)} of this column is missing.</p>}
      {p.top.length > 0 && (
        <>
          <p className="ws-legend">Most common values</p>
          <ul className="ws-bars">
            {p.top.map((t, i) => (
              <li key={i}>
                <span className="ws-bar-label">{show(t.value)}</span>
                <span className="ws-bar-track">
                  <span className="ws-bar-fill" style={{ width: `${(t.count / max) * 100}%` }} />
                </span>
                <span className="ws-bar-n">{t.count}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
