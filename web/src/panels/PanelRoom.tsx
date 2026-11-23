import { useState } from "react";
import { openAppeal, sendAppealMessage, useDemo, useRotation, type AgentId, type LabEvent } from "../api/client";
import "./panels.css";

const NAME: Record<AgentId, string> = { vale: "Dr. Vale", ines: "Ines", sam: "Sam", telem: "Telem", riley: "Riley", learner: "You", system: "System" };

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
  const whispers = events.filter((e) => e.k === "panel.whisper");
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
  const shown = new Set(thread.map((e) => e.text));
  const waiting = pending.filter((p) => ![...shown].some((s) => s?.includes(p)));

  return (
    <div className="pn-room">
      <section aria-label="Panel transcript">
        <h3 className="pn-title">Panel transcript</h3>
        {whispers.length === 0 ? (
          <p className="empty">The panel has not said anything yet.</p>
        ) : (
          <ol className="pn-log">
            {whispers.map((e) => (
              <li key={e.seq}>
                <span className="pn-who">
                  {NAME[e.agent]}
                  {e.to ? ` to ${NAME[e.to]}` : ""}
                </span>
                <span>{e.text}</span>
                <span className="pn-why">Why: {e.why}</span>
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
                <span>{e.text}</span>
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
