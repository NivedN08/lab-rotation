import { useState } from "react";
import { labelTraps, openAppeal, sendAppealMessage, useDemo, useRotation, type AgentId, type LabEvent, type PanelTranscriptData } from "../api/client";
import "./panels.css";

const NAME: Record<AgentId, string> = { vale: "Dr. Vale", ines: "Ines", sam: "Sam", telem: "Telem", riley: "Riley", learner: "You", system: "System" };

const wordsOf = (e: LabEvent): string | undefined => {
  const d = (e.data ?? {}) as { text?: string; reason?: string };
  const words = e.text ?? d.text ?? d.reason;
  return words === undefined ? undefined : labelTraps(words);
};

const verdictTask = (events: LabEvent[]): string | undefined => {
  const v = [...events].reverse().find((e) => e.k === "verdict");
  return (v?.data as { taskId?: string } | undefined)?.taskId ?? v?.task;
};

/**
 * The panel room: the BAND transcript (the panel's whispers) once a verdict exists, and under it the appeal:
 * open one, send messages, see the ruling. In the demo it is read-only.
 */
export function PanelRoom() {
  const { sessionId, events } = useRotation();
  const watching = useDemo().status !== "off";
  const [reason, setReason] = useState("");
  const [text, setText] = useState("");
  const [localAppeal, setLocalAppeal] = useState("");
  const [pending, setPending] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const task = verdictTask(events);
  // The words come from the panel.transcript event that follows the verdict. Whispers carry only who talked to whom.
  const transcript = [...events].reverse().find((e) => e.k === "panel.transcript");
  const said = ((transcript?.data as PanelTranscriptData | undefined)?.whispers ?? []).slice().sort((a, b) => a.seq - b.seq);
  const whyOf = new Map(events.filter((e) => e.k === "panel.whisper").map((e) => [e.seq, e.why]));
  const thread = events.filter((e) => e.k === "appeal.open" || e.k === "appeal.message" || e.k === "appeal.ruling");
  const opened = thread.find((e) => e.k === "appeal.open");
  const ruling = thread.find((e) => e.k === "appeal.ruling");
  const appealId = (opened?.data as { appealId?: string } | undefined)?.appealId ?? localAppeal;
  const hasAppeal = !!opened || !!localAppeal;

  if (!task) {
    return <p className="empty">The panel room opens after the verdict. Vale, Ines and Sam talk it over here.</p>;
  }

  async function open() {
    if (!sessionId || !task || !reason.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const r = await openAppeal(sessionId, task, reason.trim());
      setLocalAppeal(r.appealId);
      setPending((p) => [...p, reason.trim()]);
      setReason("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    if (!sessionId || !appealId || !text.trim() || busy) return;
    const msg = text.trim();
    setBusy(true);
    setError("");
    try {
      await sendAppealMessage(sessionId, appealId, msg);
      setPending((p) => [...p, msg]);
      setText("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // A message already confirmed by an event is not shown twice.
  const shown = new Set(thread.map(wordsOf));
  const waiting = pending.filter((p) => ![...shown].some((s) => s?.includes(p)));

  return (
    <div className="pn-room">
      <section aria-label="Panel transcript">
        <h3 className="pn-title">Panel transcript</h3>
        {!transcript ? (
          <p className="empty" role="status">
            The verdict is in. The panel's messages are on their way.
          </p>
        ) : said.length === 0 ? (
          <p className="empty">The panel did not say anything.</p>
        ) : (
          <ol className="pn-log">
            {said.map((w) => (
              <li key={w.seq}>
                <span className="pn-who">
                  {NAME[w.agent] ?? w.agent}
                  {w.to ? ` to ${NAME[w.to] ?? w.to}` : ""}
                </span>
                <span>{labelTraps(w.text)}</span>
                {whyOf.get(w.seq) && <span className="pn-why">Why: {whyOf.get(w.seq)}</span>}
              </li>
            ))}
          </ol>
        )}
      </section>

      <section aria-label="Appeal">
        <h3 className="pn-title">Appeal</h3>
        {thread.length > 0 || waiting.length > 0 ? (
          <ol className="pn-log">
            {thread.map((e) => (
              <li key={e.seq} className={e.k === "appeal.ruling" ? "pn-ruling" : undefined}>
                <span className="pn-who">{e.k === "appeal.ruling" ? `Ruling, ${NAME[e.agent]}` : NAME[e.agent]}</span>
                <span>{wordsOf(e)}</span>
                <span className="pn-why">Why: {e.why}</span>
              </li>
            ))}
            {waiting.map((m, i) => (
              <li key={`p${i}`}>
                <span className="pn-who">You (sent)</span>
                <span>{m}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="empty">{watching ? "No appeal was made in this recording." : "Think the verdict is wrong? Say why and the panel will look again."}</p>
        )}

        {watching ? null : ruling ? (
          <p className="pn-ok" role="status">
            The panel has ruled, so this appeal is closed.
          </p>
        ) : hasAppeal ? (
          <div className="pn-compose">
            <textarea className="pn-editor" rows={2} value={text} aria-label="Message to the panel" placeholder="Add a message for the panel." onChange={(e) => setText(e.target.value)} />
            <button className="btn gold" disabled={!text.trim() || busy} onClick={send}>
              {busy ? "Sending…" : "Send"}
            </button>
          </div>
        ) : (
          <div className="pn-compose">
            <textarea className="pn-editor" rows={3} value={reason} aria-label="Why you are appealing" placeholder="Why do you think the verdict is wrong?" onChange={(e) => setReason(e.target.value)} />
            <button className="btn gold" disabled={!reason.trim() || busy} onClick={open}>
              {busy ? "Opening…" : "Open an appeal"}
            </button>
          </div>
        )}
        {error && (
          <p className="pn-error" role="alert">
            {error}
          </p>
        )}
      </section>
    </div>
  );
}
