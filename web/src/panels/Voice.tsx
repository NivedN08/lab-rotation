import { useEffect } from "react";
import { audioUrl, getRotation, subscribeEvents, subscribeJump, type LabEvent } from "../api/client";
import { useMuted, voiceMute } from "./voiceMute";
import "./panels.css";

// One line at a time: lines wait their turn instead of talking over each other.
// A line may have an audio file, the words to speak, or both. If the file is missing or fails, the browser speaks the words.
type Line = { agent: string; file?: string; say?: string };
let queue: Line[] = [];
let current: { stop: () => void } | null = null;

// If the server's audio keeps failing, stop asking it: the browser's own voice does the talking, with no more failed requests.
let audioFailures = 0;
const AUDIO_GIVE_UP = 2;

// A different voice for each agent where the browser has several, and a different pitch either way.
const PITCH: Record<string, number> = { vale: 0.85, ines: 1.15, sam: 1.0, telem: 1.3, riley: 0.75, learner: 1.0 };
const ORDER = ["vale", "ines", "sam", "telem", "riley", "learner"];

function voiceFor(agent: string): SpeechSynthesisVoice | undefined {
  const all = window.speechSynthesis?.getVoices?.() ?? [];
  const lang = (navigator.language || "en").slice(0, 2).toLowerCase();
  const pool = all.filter((v) => v.lang.toLowerCase().startsWith(lang));
  const voices = pool.length ? pool : all;
  if (!voices.length) return undefined;
  return voices[Math.max(0, ORDER.indexOf(agent)) % voices.length];
}

/** Speaks the words with the browser's built-in voice. Calls `done` when finished (or at once if it cannot). */
function speak(line: Line, done: () => void) {
  const synth = window.speechSynthesis;
  if (!line.say || !synth || typeof SpeechSynthesisUtterance === "undefined") return done();
  const u = new SpeechSynthesisUtterance(line.say);
  const v = voiceFor(line.agent);
  if (v) u.voice = v;
  u.pitch = PITCH[line.agent] ?? 1;
  u.onend = done;
  u.onerror = done;
  current = { stop: () => synth.cancel() };
  synth.speak(u);
}

function next() {
  current = null;
  const line = queue.shift();
  if (!line) return;
  if (!line.file || audioFailures >= AUDIO_GIVE_UP) return speak(line, next);

  const a = new Audio(audioUrl(line.file));
  let failed = false;
  const fallBack = () => {
    if (failed) return;
    failed = true;
    audioFailures += 1;
    a.onended = null;
    a.onerror = null;
    if (!current) return; // the line was cut (muted or sought) while it was loading
    current = null;
    speak(line, next);
  };
  current = {
    stop: () => {
      failed = true; // a cut line must not fall back to speech
      a.onended = null;
      a.onerror = null;
      a.pause();
    },
  };
  a.onended = next;
  a.onerror = fallBack;
  a.play().catch(fallBack);
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
        const d = (e.data ?? {}) as { file?: string; lineOf?: number };
        const say = spoken(d.lineOf, events);
        if (d.file || say) enqueue({ agent: e.agent, file: d.file || undefined, say });
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
