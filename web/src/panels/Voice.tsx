import { useEffect } from "react";
import { audioUrl, subscribeEvents, subscribeJump } from "../api/client";
import { useMuted, voiceMute } from "./voiceMute";
import "./panels.css";

// One audio element at a time: lines wait their turn instead of talking over each other.
let queue: string[] = [];
let current: HTMLAudioElement | null = null;

function next() {
  current = null;
  const file = queue.shift();
  if (!file) return;
  const a = new Audio(audioUrl(file));
  current = a;
  a.onended = next;
  a.onerror = next;
  a.play().catch(next); // a browser may block sound until the first click; skip the line then
}

function enqueue(file: string) {
  queue.push(file);
  if (!current) next();
}

function silence() {
  queue = [];
  if (current) {
    current.onended = null;
    current.onerror = null;
    current.pause();
    current = null;
  }
}

/** Plays each voice.line's audio as it arrives. Draws nothing. Mount it once. */
export function Voice() {
  useEffect(() => {
    const offEvents = subscribeEvents((events) => {
      if (voiceMute.get()) return;
      for (const e of events) {
        const file = (e.data as { file?: string } | undefined)?.file;
        if (e.k === "voice.line" && file) enqueue(file);
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
