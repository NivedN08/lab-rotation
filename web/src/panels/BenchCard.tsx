import { useEffect, useState } from "react";
import { getBench, type Bench, type BenchDimension, type BenchRow, type BenchSplit } from "../api/client";
import "./panels.css";

// Where the benchmark's data and the task come from.
const SOURCE_URL = "https://github.com/kaushal0494/UnifyingAITutorEvaluation";

const DIMS: { id: BenchDimension; name: string; short: string }[] = [
  { id: "Mistake_Identification", name: "Spots the mistake", short: "MI" },
  { id: "Mistake_Location", name: "Says where it is", short: "ML" },
  { id: "Providing_Guidance", name: "Gives guidance", short: "PG" },
  { id: "Actionability", name: "Student can act on it", short: "AC" },
];

// Every number names its split. A dev number is never shown as a test number.
const SPLITS: { id: BenchSplit; title: string; note: string }[] = [
  { id: "dev-B", title: "Held-out check (dev-B)", note: "Chats the grading guide was never tuned on. This is the honest number." },
  { id: "test", title: "Test set (CodaBench)", note: "Scored by the competition's organisers." },
  { id: "dev-A", title: "Tuning set (dev-A)", note: "The guide was tuned on these chats, so these scores flatter it." },
];

const WHERE: Record<Bench["source"], string> = {
  bruin: "Scores read from Bruin's learn.bench_results table.",
  csv: "Scores read from the benchmark's results file.",
  none: "The detailed scores aren't available yet.",
};

/** "single-opus-tuned" becomes "One reader, tuned guide". Unknown names are shown as they are. */
function systemName(system: string): string {
  const readers = /panel/i.test(system) ? "Two readers and a referee" : /single/i.test(system) ? "One reader" : null;
  const guide = /tuned/i.test(system) ? "tuned guide" : /start/i.test(system) ? "starting guide" : null;
  return readers && guide ? `${readers}, ${guide}` : system;
}

/** A score, "pending" when CodaBench has not scored it yet (null), or a dash when there is no such row. */
const score = (v: number | null | undefined) => (v === undefined ? "–" : v === null ? "pending" : v.toFixed(1));

/**
 * The examiner panel's result on the BEA 2025 shared task, in plain words: what was tested, the three demo lines, a table
 * grouped by split (each named, so a dev score never passes for a test score), the best team's test score for comparison,
 * and a link to the benchmark's source. `compact` leaves out the explanation and the tuning set.
 */
export function BenchCard({ compact = false }: { compact?: boolean }) {
  const [bench, setBench] = useState<Bench | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    getBench()
      .then((b) => live && setBench(b))
      .catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
  }, []);

  if (error)
    return (
      <p className="pn-error" role="alert">
        {error}
      </p>
    );
  if (!bench)
    return (
      <p className="empty" role="status">
        Loading the benchmark…
      </p>
    );

  const bySplit = (split: BenchSplit): Map<string, BenchRow[]> => {
    const systems = new Map<string, BenchRow[]>();
    for (const r of bench.rows.filter((x) => x.split === split)) systems.set(r.system, [...(systems.get(r.system) ?? []), r]);
    return systems;
  };
  const record = DIMS.map((d) => bench.rows.find((r) => r.dimension === d.id)?.record);
  const splits = SPLITS.filter((s) => !(compact && s.id === "dev-A") && bySplit(s.id).size > 0);

  return (
    <section className="pn-bench box" aria-label="Examiner benchmark">
      <h3 className="pn-title">How the examiners score</h3>
      {!compact && (
        <p className="pn-bench-what">
          We tested our examiner panel on a public benchmark, the BEA 2025 shared task on judging AI tutors. Each item is a short maths tutoring chat and one more
          tutor reply. The panel labels four things about that reply, and each gets a score out of 100 (macro-F1, so higher is better).
        </p>
      )}

      {bench.lines.length > 0 && (
        <ul className="pn-bench-lines" aria-label="The result in three lines">
          {bench.lines.map((l, i) => (
            <li key={i} className={i === 0 ? "lead" : undefined}>
              {l}
            </li>
          ))}
        </ul>
      )}

      {splits.length > 0 && (
        <div className="pn-bench-scroll" tabIndex={0} aria-label="Benchmark scores">
          <table className="pn-bench-table">
            <thead>
              <tr>
                <th scope="col">System</th>
                {DIMS.map((d) => (
                  <th key={d.id} scope="col" title={d.name}>
                    {d.name}
                    <span className="pn-bench-short">{d.short}</span>
                  </th>
                ))}
                <th scope="col">Replies</th>
              </tr>
            </thead>
            {splits.map((s) => (
              <tbody key={s.id}>
                <tr className="pn-bench-split">
                  <th colSpan={6} scope="colgroup">
                    {s.title}
                    <span>{s.note}</span>
                  </th>
                </tr>
                {[...bySplit(s.id)].map(([system, rows]) => (
                  <tr key={system}>
                    <th scope="row">{systemName(system)}</th>
                    {DIMS.map((d) => {
                      const row = rows.find((r) => r.dimension === d.id);
                      return (
                        <td key={d.id} className={!row || row.macro_f1 === null ? "pn-bench-pending" : undefined}>
                          {score(row?.macro_f1)}
                        </td>
                      );
                    })}
                    <td>{rows[0].n.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            ))}
            {record.some((v) => v !== undefined) && (
              <tbody>
                <tr className="pn-bench-record">
                  <th scope="row">Best team on the test set</th>
                  {record.map((v, i) => (
                    <td key={i}>{score(v)}</td>
                  ))}
                  <td />
                </tr>
              </tbody>
            )}
          </table>
        </div>
      )}

      <p className="pn-bench-foot">
        <a href={SOURCE_URL} target="_blank" rel="noreferrer">
          Source: BEA 2025 shared task data
        </a>
        <span className="pn-why">{WHERE[bench.source]}</span>
      </p>
    </section>
  );
}
