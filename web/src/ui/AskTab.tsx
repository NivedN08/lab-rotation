import { useEffect, useRef, useState, type CSSProperties } from "react";
import { askAgent, isStatic, type AgentId, type AskReply } from "../api/client";
import type { Replay } from "../sim/replay";
import { colorOf } from "../world/palette";
import { Avatar } from "./Avatar";

// The Ask tab: put a question to anyone on the panel. The backend answers from only what that
// agent could see; Telem answers with a live search and sends its links and trace.

export type Msg = { role: "user" | "bot"; text: string; sources?: string[]; links?: { title: string; url: string }[]; trace?: string; error?: boolean; pending?: boolean };

const SUGGEST: Record<string, string[]> = {
  vale: ["Why did I get this task?", "What happens after I answer?"],
  sam: ["Where should I look first?", "Can I have a hint?"],
  telem: ["What's the background on this claim?", "Where does data like this usually come from?"],
  ines: ["How will my answer be checked?", "What counts as good evidence?"],
  riley: ["How are you approaching it?", "Have you finished yet?"],
};

type Props = {
  R: Replay;
  sessionId: string | null;
  agent: string;
  setAgent: (id: string) => void;
  /** Who can be asked: everyone on the floor but you. */
  people: string[];
  chats: Record<string, Msg[]>;
  setChats: (f: (c: Record<string, Msg[]>) => Record<string, Msg[]>) => void;
};

export function AskTab({ R, sessionId: liveSession, agent, setAgent, people, chats, setChats }: Props) {
  // The hosted replay has no one to ask: the input is off there.
  const off = isStatic();
  const sessionId = off ? null : liveSession;
  const [text, setText] = useState("");
  const msgsRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const a = R.agents.get(agent);
  const msgs = chats[agent] ?? [];
  const busy = msgs.some((m) => m.pending);

  useEffect(() => {
    msgsRef.current?.scrollTo({ top: msgsRef.current.scrollHeight, behavior: "smooth" });
  }, [msgs.length, msgs[msgs.length - 1]?.pending]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [agent]);

  const send = async (q: string) => {
    const question = q.trim();
    if (!question || busy || !sessionId) return;
    setText("");
    setChats((c) => ({ ...c, [agent]: [...(c[agent] ?? []), { role: "user", text: question }, { role: "bot", text: "", pending: true }] }));
    let answer: Msg;
    try {
      const r: AskReply = await askAgent(sessionId, { agent: agent as AgentId, text: question });
      answer = { role: "bot", text: r.text, sources: r.sources, links: r.links, trace: r.trace };
    } catch (e) {
      answer = { role: "bot", text: (e as Error).message || "No answer came back. Try again in a moment.", error: true };
    }
    setChats((c) => {
      const list = [...(c[agent] ?? [])];
      list[list.length - 1] = answer;
      return { ...c, [agent]: list };
    });
  };

  const name = R.name(agent);
  const bandStyle = { "--band": a ? colorOf(a.role, agent) : "var(--gold)" } as CSSProperties;

  return (
    <div className="chat" style={bandStyle}>
      <div className="chat-who">
        {a && <Avatar id={agent} role={a.role} scale={2} />}
        <div style={{ minWidth: 0 }}>
          <b>{name}</b>
          <small>
            {R.label(agent)}. {a?.reads}
          </small>
        </div>
      </div>
      <div style={{ padding: "8px 16px 0" }}>
        <label className="sr-only" htmlFor="persona">
          Who to ask
        </label>
        <select id="persona" className="run-pick" style={{ width: "100%", display: "block" }} value={agent} onChange={(e) => setAgent(e.target.value)}>
          {people.map((id) => (
            <option key={id} value={id}>
              {R.name(id)}: {R.label(id)}
            </option>
          ))}
        </select>
      </div>
      <div className="msgs" ref={msgsRef} aria-live="polite">
        {!msgs.length && (
          <p className="empty" style={{ fontSize: 14 }}>
            {off
              ? "Questions are off in this recorded replay. Ask the panel when you play live."
              : sessionId
                ? `${name} answers only from what they can see.`
                : "Start your rotation to ask the panel."}
          </p>
        )}
        {msgs.map((m, i) =>
          m.pending ? (
            <div key={i} className="msg bot typing" aria-label="Thinking">
              <span />
              <span />
              <span />
            </div>
          ) : (
            <div key={i} className={`msg ${m.role}`}>
              {m.text}
              {((m.links?.length ?? 0) > 0 || m.trace) && (
                <div className="src">
                  {m.links?.slice(0, 5).map((l) => (
                    <a key={l.url} href={l.url} target="_blank" rel="noreferrer noopener" title={l.url}>
                      {l.title || l.url}
                    </a>
                  ))}
                  {m.trace && (
                    <a href={m.trace} target="_blank" rel="noreferrer noopener">
                      Telem trace
                    </a>
                  )}
                </div>
              )}
              {m.role === "bot" && !m.error && m.sources && m.sources.length > 0 && <span className="mode">Used: {m.sources.join("; ")}</span>}
            </div>
          ),
        )}
      </div>
      {msgs.length < 2 && sessionId && (
        <div className="suggest">
          {(SUGGEST[agent] ?? []).map((s) => (
            <button key={s} onClick={() => send(s)} disabled={busy}>
              {s}
            </button>
          ))}
        </div>
      )}
      <form
        className="compose"
        onSubmit={(e) => {
          e.preventDefault();
          send(text);
        }}
      >
        <label className="sr-only" htmlFor="ask">
          Your question
        </label>
        <textarea
          id="ask"
          ref={inputRef}
          rows={1}
          value={text}
          placeholder={`Ask ${name}`}
          disabled={!sessionId}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(text);
            }
          }}
          maxLength={2000}
        />
        <button className="btn gold" type="submit" disabled={busy || !text.trim() || !sessionId}>
          Send
        </button>
      </form>
    </div>
  );
}
