import { useState } from "react";
import { submitAnswer, type TaskInfo, type Verdict } from "../api/client";
import { useEvidence } from "./evidence";

export const TRAPS = ["Duplicate rows", "Missing values", "Unit mix-up", "Wrong join", "Outliers", "Selection bias", "Something else", "No trap"];

const VERDICTS: { id: Verdict; label: string; hint: string }[] = [
  { id: "holds", label: "Holds", hint: "The claim stands" },
  { id: "fails", label: "Fails", hint: "The claim is wrong" },
  { id: "cant_tell", label: "Can't tell", hint: "Not enough to say" },
];

type Draft = { verdict: Verdict | ""; trap: string; note: string; sent: boolean };
const empty: Draft = { verdict: "", trap: "", note: "", sent: false };
const keyFor = (id: string) => `lab-rotation.workspace.answer.${id}`;

function load(id: string): Draft {
  try {
    return { ...empty, ...JSON.parse(sessionStorage.getItem(keyFor(id)) ?? "{}") };
  } catch {
    return empty;
  }
}

export function AnswerForm({ sessionId, task }: { sessionId: string; task: TaskInfo }) {
  const [draft, setDraft] = useState<Draft>(() => load(task.id));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const cited = useEvidence();

  function update(patch: Partial<Draft>) {
    const next = { ...draft, ...patch };
    setDraft(next);
    try {
      sessionStorage.setItem(keyFor(task.id), JSON.stringify(next));
    } catch {
      /* keep it in memory */
    }
  }

  const missing = [!draft.verdict && "pick a verdict", !draft.trap && "pick the trap", cited.length === 0 && "cite at least one piece of evidence"].filter(Boolean) as string[];
  const locked = draft.sent;

  async function submit() {
    if (missing.length || busy || !draft.verdict) return;
    setBusy(true);
    setError("");
    try {
      await submitAnswer(sessionId, {
        taskId: task.id,
        verdict: draft.verdict,
        trap: draft.trap,
        evidence: cited.map(({ key: _k, ...rest }) => rest),
        note: draft.note.trim(),
      });
      update({ sent: true });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="ws-answer box" aria-label="Your answer">
      <h2 className="ws-title">Your answer</h2>

      <fieldset className="ws-field" disabled={locked}>
        <legend>Does the claim hold?</legend>
        <div className="ws-choices" role="radiogroup" aria-label="Verdict">
          {VERDICTS.map((v) => (
            <button
              key={v.id}
              type="button"
              role="radio"
              aria-checked={draft.verdict === v.id}
              className={`chip ws-choice ${v.id}`}
              onClick={() => update({ verdict: v.id })}
              title={v.hint}
            >
              {v.label}
            </button>
          ))}
        </div>
      </fieldset>

      <label className="ws-field">
        <span className="ws-legend">The trap you found</span>
        <select className="ws-select" value={draft.trap} disabled={locked} onChange={(e) => update({ trap: e.target.value })}>
          <option value="">Choose one…</option>
          {TRAPS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>

      <div className="ws-field">
        <span className="ws-legend">Your evidence ({cited.length})</span>
        {cited.length === 0 ? (
          <p className="empty">Nothing cited yet. Click rows, columns or cells above and they appear here.</p>
        ) : (
          <ul className="ws-cites ws-cites-plain">
            {cited.map((e) => (
              <li key={e.key}>{e.label}</li>
            ))}
          </ul>
        )}
      </div>

      <label className="ws-field">
        <span className="ws-legend">In your own words (optional)</span>
        <textarea
          className="ws-editor ws-note"
          rows={3}
          value={draft.note}
          disabled={locked}
          placeholder="Say what you saw and why it matters."
          onChange={(e) => update({ note: e.target.value })}
        />
      </label>

      {error && (
        <p className="ws-error" role="alert">
          {error}
        </p>
      )}

      {locked ? (
        <p className="ws-sent" role="status">
          Answer sent for {task.title}. The verdict shows up when the checks finish.
        </p>
      ) : (
        <div className="ws-foot">
          <span>{missing.length ? `To submit: ${missing.join(", ")}.` : "Ready to submit."}</span>
          <button className="btn gold" onClick={submit} disabled={missing.length > 0 || busy}>
            {busy ? "Sending…" : "Submit answer"}
          </button>
        </div>
      )}
    </section>
  );
}
