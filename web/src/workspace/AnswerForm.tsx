import { useEffect, useRef, useState } from "react";
import { submitAnswer, TRAPS, type TaskInfo, type TrapId, type Verdict } from "../api/client";
import { useDictation } from "./useDictation";
import { useEvidence } from "./evidence";

const VERDICTS: { id: Verdict; label: string; hint: string }[] = [
  { id: "holds", label: "Holds", hint: "The claim stands" },
  { id: "fails", label: "Fails", hint: "The claim is wrong" },
  { id: "cant_tell", label: "Can't tell", hint: "Not enough to say" },
];

type Draft = { verdict: Verdict | ""; trap: TrapId | ""; note: string; sent: boolean };
const empty: Draft = { verdict: "", trap: "", note: "", sent: false };
const keyFor = (id: string) => `lab-rotation.workspace.answer.${id}`;

function load(id: string): Draft {
  try {
    return { ...empty, ...JSON.parse(sessionStorage.getItem(keyFor(id)) ?? "{}") };
  } catch {
    return empty;
  }
}

export function AnswerForm({ sessionId, task, onSent }: { sessionId: string; task: TaskInfo; onSent: () => void }) {
  const [draft, setDraft] = useState<Draft>(() => load(task.id));
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const backRef = useRef<HTMLButtonElement>(null);
  const [error, setError] = useState("");
  const cited = useEvidence();
  const dictation = useDictation((text) => update({ note: [draft.note.trim(), text].filter(Boolean).join(" ") }));

  useEffect(() => {
    if (draft.sent) onSent();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  // Submit asks first, inside the form. Focus lands on Back so a second Enter cannot send by accident.
  function ask() {
    if (missing.length || busy) return;
    setConfirming(true);
    setTimeout(() => backRef.current?.focus(), 0);
  }

  async function submit() {
    if (missing.length || busy || !draft.verdict) return;
    setBusy(true);
    setError("");
    try {
      await submitAnswer(sessionId, {
        taskId: task.id,
        verdict: draft.verdict,
        trap: draft.trap as TrapId,
        evidence: cited.map(({ key: _k, ...rest }) => rest),
        note: draft.note.trim(),
      });
      setConfirming(false);
      update({ sent: true });
      onSent();
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
        <select className="ws-select" value={draft.trap} disabled={locked} onChange={(e) => update({ trap: e.target.value as TrapId | "" })}>
          <option value="">Choose one…</option>
          {TRAPS.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
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

      <div className="ws-field">
        <span className="ws-legend ws-legend-row" id="ws-note-label">
          In your own words (optional)
          {dictation.supported && !locked && (
            <button
              type="button"
              className="btn quiet ws-mic"
              aria-pressed={dictation.listening}
              onClick={dictation.listening ? dictation.stop : dictation.start}
            >
              <span className={`ws-rec${dictation.listening ? " on" : ""}`} aria-hidden="true" />
              {dictation.listening ? "Stop dictating" : "Dictate"}
            </button>
          )}
        </span>
        <textarea
          className="ws-editor ws-note"
          aria-labelledby="ws-note-label"
          rows={3}
          value={draft.note}
          disabled={locked}
          placeholder="Say what you saw and why it matters."
          onChange={(e) => update({ note: e.target.value })}
        />
      </div>

      {dictation.listening && (
        <p className="empty" role="status">
          Listening. Speak, and your words are added to the note.
        </p>
      )}
      {!dictation.supported && !locked && <p className="empty">Voice input isn't available in this browser; type your note instead.</p>}
      {(error || dictation.error) && (
        <p className="ws-error" role="alert">
          {error || dictation.error}
        </p>
      )}

      {locked ? (
        <p className="ws-sent" role="status">
          Answer sent for {task.title}. The verdict shows up when the checks finish.
        </p>
      ) : confirming ? (
        <div className="ws-confirm" role="group" aria-label="Send this answer?">
          <p>
            <b>Send this answer?</b> You can't change it after.
          </p>
          <div className="ws-confirm-actions">
            <button ref={backRef} className="btn" onClick={() => setConfirming(false)} disabled={busy}>
              Back
            </button>
            <button className="btn gold" onClick={submit} disabled={busy}>
              {busy ? "Sending…" : "Send"}
            </button>
          </div>
        </div>
      ) : (
        <div className="ws-foot">
          <span>{missing.length ? `To submit: ${missing.join(", ")}.` : "Ready to submit."}</span>
          <button className="btn gold" onClick={ask} disabled={missing.length > 0}>
            Submit answer
          </button>
        </div>
      )}
    </section>
  );
}
