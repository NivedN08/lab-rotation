import { useEffect } from "react";
import { audioUrl, getRotation, subscribeEvents, subscribeJump, type LabEvent } from "../api/client";
import { useMuted, voiceMute } from "./voiceMute";
import "./panels.css";

// One line at a time: lines wait their turn instead of talking over each other.
type Line = { file: string } | { say: string };
let queue: Line[] = [];
let current: { stop: () => void } | null = null;

function next() {
  current = null;
  const line = queue.shift();
  if (!line) return;
  if ("say" in line) {
    // provider "browser": no audio file, so the browser speaks the text itself.
    const synth = window.speechSynthesis;
    if (!synth) return next();
    const u = new SpeechSynthesisUtterance(line.say);
    u.onend = next;
    u.onerror = next;
    current = { stop: () => synth.cancel() };
    synth.speak(u);
    return;
  }
  const a = new Audio(audioUrl(line.file));
  current = {
    stop: () => {
      a.onended = null;
      a.onerror = null;
      a.pause();
    },
  };
  a.onended = next;
  a.onerror = next;
  a.play().catch(next); // a browser may block sound until the first click; skip the line then
}

function enqueue(line: Line) {
  queue.push(line);
  if (!current) next();
}

function silence() {
  queue = [];
  current?.stop();
  current = null;
}

/** The text of the agent.say event a voice.line speaks (`lineOf` is its seq). */
function spoken(lineOf: number | undefined, batch: LabEvent[]): string | undefined {
  if (lineOf === undefined) return undefined;
  return [...getRotation().events, ...batch].find((e) => e.seq === lineOf)?.text;
}

/** Plays each voice.line's audio as it arrives. Draws nothing. Mount it once. */
export function Voice() {
  useEffect(() => {
    const offEvents = subscribeEvents((events) => {
      if (voiceMute.get()) return;
      for (const e of events) {
        if (e.k !== "voice.line") continue;
        const d = (e.data ?? {}) as { file?: string; provider?: string; lineOf?: number };
        if (d.file) enqueue({ file: d.file });
        else if (d.provider === "browser") {
          const say = spoken(d.lineOf, events);
          if (say) enqueue({ say });
        }
      }
    });
    // A seek or loop in the demo: whatever was being said no longer applies.
    const offJump = subscribeJump(silence);
    return () => {
      offEvents();
      offJump();
      silence();
    };
  }, []);

  // Muting cuts the line that is playing.
  const muted = useMuted();
  useEffect(() => {
    if (muted) silence();
  }, [muted]);

  return null;
}

/** Mute or unmute voice lines. Sits in the top bar. */
export function MuteButton() {
  const muted = useMuted();
  return (
    <button
      className="btn quiet pn-mute"
      aria-pressed={muted}
      aria-label={muted ? "Unmute voice lines" : "Mute voice lines"}
      title={muted ? "Unmute voice lines" : "Mute voice lines"}
      onClick={() => voiceMute.set(!muted)}
    >
      <svg width="16" height="16" viewBox="0 0 8 8" shapeRendering="crispEdges" aria-hidden="true">
        <path d="M0 3h1V2h1V1h1v6H2V6H1V5H0z" fill="currentColor" />
        {muted ? <path d="M5 2h1v1h1V2h1v1H7v1h1v1H7V4H6v1H5V4h1V3H5z" fill="currentColor" /> : <path d="M5 3h1v2H5zM6 2h1v4H6z" fill="currentColor" />}
      </svg>
      <span className="hide-sm">{muted ? "Muted" : "Voice"}</span>
    </button>
  );
}
