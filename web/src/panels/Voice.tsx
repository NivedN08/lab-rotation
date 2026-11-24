import { useEffect, useSyncExternalStore } from "react";
import { audioUrl, getDemoState, getRotation, subscribeEvents, subscribeJump, useDemo, useMock, useRotation, type LabEvent } from "../api/client";
import { useMuted, voiceMute } from "./voiceMute";
import "./panels.css";

// One line at a time: lines wait their turn instead of talking over each other.
// A line may have an audio file, the words to speak, or both. If the file is missing or fails, the browser speaks the words.
type Line = { agent: string; file?: string; say?: string };
let queue: Line[] = [];
let current: { stop: () => void } | null = null;

// If the server's audio file keeps failing to load, stop asking it: the browser's own voice does the talking, with no more failed
// requests. Only real load errors count (the audio element's `error` event). A browser blocking sound until the first click does
// not, and neither does a missing file in sample mode. The count starts again whenever a new session or demo starts.
let audioFailures = 0;
const AUDIO_GIVE_UP = 2;

// A line the browser would not play yet (autoplay blocked): it is kept and played after the next click or key press.
let blocked: Line | null = null;
const blockedSubs = new Set<() => void>();
const setBlocked = (line: Line | null) => {
  blocked = line;
  blockedSubs.forEach((f) => f());
};
const useBlocked = (): boolean =>
  useSyncExternalStore(
    (f) => {
      blockedSubs.add(f);
      return () => blockedSubs.delete(f);
    },
    () => blocked !== null,
  );

/** Sample data has no real audio files, so a missing one is expected there. */
const sampleAudio = (): boolean => useMock() || getDemoState().sample;

// Browsers allow sound only after the person has interacted with the page.
const GESTURES = ["pointerdown", "pointerup", "keydown", "touchend"] as const;
function untilGesture(retry: () => void): () => void {
  const go = () => {
    off();
    retry();
  };
  const off = () => GESTURES.forEach((g) => window.removeEventListener(g, go, true));
  GESTURES.forEach((g) => window.addEventListener(g, go, true));
  return off;
}

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
  let over = false; // this line has been dealt with: failed, blocked or cut
  const fallBack = (counts: boolean) => {
    if (over) return;
    over = true;
    if (counts && !sampleAudio()) audioFailures += 1;
    a.onended = null;
    a.onerror = null;
    if (!current) return; // the line was cut (muted or sought) while it was loading
    current = null;
    speak(line, next);
  };
  const cut = { stop: () => {} };
  current = cut;
  cut.stop = () => {
    over = true; // a cut line must not fall back to speech
    a.onended = null;
    a.onerror = null;
    a.pause();
  };
  a.onended = next;
  a.onerror = () => fallBack(true); // a real load error
  a.play().catch((err: unknown) => {
    if (over) return;
    if ((err as { name?: string } | null)?.name === "NotAllowedError") {
      // Autoplay is blocked until the person clicks or presses a key: keep the line, say so, and play it then.
      over = true;
      a.onended = null;
      a.onerror = null;
      setBlocked(line);
      const off = untilGesture(() => {
        const keep = blocked;
        setBlocked(null);
        current = null;
        if (keep) queue.unshift(keep);
        next();
      });
      current = {
        stop: () => {
          off();
          setBlocked(null);
        },
      };
      return;
    }
    fallBack(false); // some other refusal: speak this line, but do not count it against the audio
  });
}

function enqueue(line: Line) {
  queue.push(line);
  if (!current) next();
}

function silence() {
  queue = [];
  current?.stop();
  current = null;
  setBlocked(null);
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

  // A new session or a demo starting gives the server's audio a fresh chance.
  const { sessionId } = useRotation();
  const { status } = useDemo();
  useEffect(() => {
    audioFailures = 0;
  }, [sessionId, status]);

  // Sound is blocked until the person clicks: say so, until they do.
  const waiting = useBlocked();
  if (!waiting) return null;
  return (
    <div className="pn-sound-note" role="status">
      Click anywhere to turn on sound
    </div>
  );
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
