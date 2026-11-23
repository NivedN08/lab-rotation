import type { ReactNode } from "react";
import { trapLabel } from "../api/traps";
import type { LabEvent, Verdict } from "../api/types";

// The verdict card shows what the backend sent and nothing else. Props mirror the event `data`
// fields documented in web/src/api/README.md; the card never grades or decides anything.

/** `data` of a `verdict` event. */
export type VerdictData = { correct: boolean; key: Verdict; trap: string; sealed?: boolean };
/** `data` of a `check.result` event (Ines's Bruin checks). */
export type CheckData = { check: string; passed: boolean };
/** `data` of a `learner.answer` or `rival.answer` event. */
export type AnswerData = { verdict: Verdict; trap: string };

export type VerdictCardProps = {
  taskTitle: string;
  verdict: VerdictData;
  /** Your answer, the evidence you cited (labels) and your own words, if you wrote any. */
  yours: AnswerData & { evidence: string[]; words?: string };
  riley?: AnswerData | null;
  checks: CheckData[];
  /** Room for the mastery chart (item 11). */
  children?: ReactNode;
  onClose: () => void;
  onPanelRoom?: () => void;
  /** The demo's end: play it again. */
  onAgain?: () => void;
};

type CardData = Pick<VerdictCardProps, "verdict" | "yours" | "riley" | "checks">;

/** Gather one task's card from its events, exactly as sent. Null until that task has a verdict. */
export function verdictFromEvents(events: LabEvent[], taskId: string): CardData | null {
  const mine = events.filter((e) => e.task === taskId);
  const last = (k: string) => [...mine].reverse().find((e) => e.k === k)?.data as Record<string, unknown> | undefined;
  const v = last("verdict") as VerdictData | undefined;
  if (!v) return null;
  const answer = last("learner.answer") as (AnswerData & { note?: string }) | undefined;
  const rival = last("rival.answer") as AnswerData | undefined;
  return {
    verdict: v,
    yours: {
      verdict: answer?.verdict ?? "cant_tell",
      trap: answer?.trap ?? "none",
      evidence: mine.filter((e) => e.k === "learner.evidence").map((e) => String((e.data as { label?: string } | undefined)?.label ?? e.text ?? "")),
      words: answer?.note || undefined,
    },
    riley: rival ?? null,
    checks: mine.filter((e) => e.k === "check.result").map((e) => e.data as CheckData),
  };
}

const SAY: Record<Verdict, string> = { holds: "the claim holds", fails: "the claim fails", cant_tell: "can't tell" };

function Mark({ ok, yes = "passed", no = "failed" }: { ok: boolean; yes?: string; no?: string }) {
  return <span className={`mark ${ok ? "pass" : "fail"}`}>{ok ? yes : no}</span>;
}

export function VerdictCard({ taskTitle, verdict, yours, riley, checks, children, onClose, onPanelRoom, onAgain }: VerdictCardProps) {
  const failing = checks.filter((c) => !c.passed);
  return (
    <div className="tour box verdict" role="dialog" aria-label={`Verdict for ${taskTitle}`}>
      <span className="count">
        {taskTitle} · Verdict{verdict.sealed ? " · sealed" : ""}
      </span>
      <h2>{verdict.correct ? "You found the trap" : "Not this time"}</h2>
      <p>
        The key says {SAY[verdict.key]}: {trapLabel(verdict.trap).toLowerCase()}.
      </p>

      <section className="section">
        <h3>Your verdict against the key</h3>
        <dl className="kv">
          <dt>You said</dt>
          <dd>
            {SAY[yours.verdict]}, {trapLabel(yours.trap).toLowerCase()} <Mark ok={verdict.correct} yes="right" no="wrong" />
          </dd>
          <dt>The key</dt>
          <dd>
            {SAY[verdict.key]}, {trapLabel(verdict.trap).toLowerCase()}
          </dd>
          {riley && (
            <>
              <dt>Riley said</dt>
              <dd>
                {SAY[riley.verdict]}, {trapLabel(riley.trap).toLowerCase()}
              </dd>
            </>
          )}
        </dl>
      </section>

      {(checks.length > 0 || yours.evidence.length > 0) && (
        <section className="section">
          <h3>Bruin checks next to your evidence</h3>
          <div className="verdict-pair">
            <div>
              {(failing.length ? failing : checks).map((c) => (
                <div className="item" key={c.check}>
                  {c.check} check <Mark ok={c.passed} />
                </div>
              ))}
              {!checks.length && <p className="empty">No checks run.</p>}
            </div>
            <div>
              {yours.evidence.map((e, i) => (
                <div className="item" key={i}>
                  {e}
                </div>
              ))}
              {!yours.evidence.length && <p className="empty">You cited no evidence.</p>}
            </div>
          </div>
        </section>
      )}

      {yours.words && (
        <section className="section">
          <h3>In your words</h3>
          <div className="quote">“{yours.words}”</div>
        </section>
      )}

      {children}

      <div className="row">
        {onPanelRoom && (
          <button className="btn" onClick={onPanelRoom}>
            Open the panel room
          </button>
        )}
        {onAgain ? (
          <>
            <button className="btn" onClick={onClose}>
              Explore the lab
            </button>
            <button className="btn gold" onClick={onAgain} autoFocus>
              Watch again
            </button>
          </>
        ) : (
          <button className="btn gold" onClick={onClose} autoFocus>
            Back to the lab
          </button>
        )}
      </div>
    </div>
  );
}
