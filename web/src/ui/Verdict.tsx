import type { ReactNode } from "react";
import { trapLabel } from "../api/traps";
import type { LabEvent, Verdict } from "../api/types";

// The verdict card shows what the backend sent and nothing else (contract/events.md); it never
// grades or decides anything.

/** The verdict, from a `verdict` event: passed or not, the answer key, and Ines's feedback. */
export type VerdictData = { correct: boolean; key: Verdict; trap: string; sealed?: boolean; feedback?: string };
/** One of Ines's Bruin checks, from a `check.result` event, with its plain-words line. */
export type CheckData = { check: string; passed: boolean; label?: string };
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
  type Ev = { label?: string };
  const v = last("verdict") as { result?: string; correctVerdict?: Verdict; correctTrap?: string; text?: string; ledger?: unknown } | undefined;
  if (!v) return null;
  const answer = last("learner.answer") as (Partial<AnswerData> & { note?: string; evidence?: Ev[] }) | undefined;
  const rival = last("rival.answer") as Partial<AnswerData> | undefined;
  const cited = [
    ...(answer?.evidence ?? []).map((x) => x.label),
    ...mine.filter((e) => e.k === "learner.evidence").flatMap((e) => ((e.data as { action?: string; items?: Ev[] } | undefined)?.action === "remove" ? [] : ((e.data as { items?: Ev[] } | undefined)?.items ?? []).map((x) => x.label))),
  ].filter((x): x is string => !!x);
  return {
    verdict: {
      correct: v.result === "passed",
      key: v.correctVerdict ?? "cant_tell",
      trap: v.correctTrap ?? "none",
      sealed: !!v.ledger || mine.some((e) => e.k === "ledger.seal"),
      feedback: v.text,
    },
    yours: { verdict: answer?.verdict ?? "cant_tell", trap: answer?.trap ?? "none", evidence: [...new Set(cited)], words: answer?.note || undefined },
    riley: rival?.verdict ? { verdict: rival.verdict, trap: rival.trap ?? "none" } : null,
    checks: mine
      .filter((e) => e.k === "check.result")
      .map((e) => {
        const d = (e.data ?? {}) as { check?: string; passed?: boolean; detail?: string };
        return { check: d.check ?? "check", passed: d.passed !== false, label: e.text ?? d.detail };
      }),
  };
}

const SAY_VERDICT: Record<string, string> = { holds: "the claim holds", fails: "the claim fails", cant_tell: "can't tell" };
const say = (v: string | undefined) => SAY_VERDICT[v ?? ""] ?? String(v);
const trapWords = (id: string | undefined) => (trapLabel(id ?? "none") ?? String(id)).toLowerCase();

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
        The key says {say(verdict.key)}: {trapWords(verdict.trap)}.
      </p>
      {verdict.feedback && <p style={{ marginTop: 6 }}>{verdict.feedback}</p>}

      <section className="section">
        <h3>Your verdict against the key</h3>
        <dl className="kv">
          <dt>You said</dt>
          <dd>
            {say(yours.verdict)}, {trapWords(yours.trap)} <Mark ok={verdict.correct} yes="right" no="wrong" />
          </dd>
          <dt>The key</dt>
          <dd>
            {say(verdict.key)}, {trapWords(verdict.trap)}
          </dd>
          {riley && (
            <>
              <dt>Riley said</dt>
              <dd>
                {say(riley.verdict)}, {trapWords(riley.trap)}
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
              {(failing.length ? failing : checks).map((c, i) => (
                <div className="item" key={`${c.check}-${i}`}>
                  {c.label ?? `${c.check} check`} <Mark ok={c.passed} />
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
