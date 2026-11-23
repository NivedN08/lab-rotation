import { useCallback, useEffect, useRef, useState } from "react";

// The browser's speech-to-text is not in the TypeScript DOM types.
type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
};

const Ctor = (): (new () => Recognition) | null => {
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
};

const MESSAGES: Record<string, string> = {
  "not-allowed": "The microphone is blocked. Allow it in the browser's address bar to dictate.",
  "service-not-allowed": "The microphone is blocked. Allow it in the browser's address bar to dictate.",
  "no-speech": "I didn't hear anything. Try again.",
  "audio-capture": "No microphone found.",
  network: "Dictation needs an internet connection.",
};

/** Browser speech to text. Each finished phrase is passed to `onText`. */
export function useDictation(onText: (text: string) => void) {
  const supported = typeof window !== "undefined" && Ctor() !== null;
  const [listening, setListening] = useState(false);
  const [error, setError] = useState("");
  const rec = useRef<Recognition | null>(null);
  const cb = useRef(onText);
  cb.current = onText;

  const stop = useCallback(() => rec.current?.stop(), []);

  const start = useCallback(() => {
    const C = Ctor();
    if (!C) return;
    setError("");
    const r = new C();
    r.lang = navigator.language || "en-US";
    r.continuous = true;
    r.interimResults = false;
    r.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) cb.current(e.results[i][0].transcript.trim());
      }
    };
    r.onerror = (e) => setError(MESSAGES[e.error] ?? "Dictation stopped unexpectedly.");
    r.onend = () => setListening(false);
    rec.current = r;
    try {
      r.start();
      setListening(true);
    } catch {
      setError("Dictation could not start.");
    }
  }, []);

  useEffect(() => () => rec.current?.stop(), []);

  return { supported, listening, error, start, stop };
}
