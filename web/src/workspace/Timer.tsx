import { useEffect, useState } from "react";

const startKey = (id: string) => `lab-rotation.workspace.start.${id}`;

/** Start time for a task, kept so closing the panel or reloading does not reset the clock. */
function startedAt(id: string): number {
  try {
    const saved = Number(sessionStorage.getItem(startKey(id)));
    if (saved) return saved;
    const now = Date.now();
    sessionStorage.setItem(startKey(id), String(now));
    return now;
  } catch {
    return Date.now();
  }
}

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

export function Timer({ taskId, seconds }: { taskId: string; seconds: number }) {
  const [start] = useState(() => startedAt(taskId));
  const left = () => Math.max(0, seconds - Math.floor((Date.now() - start) / 1000));
  const [remaining, setRemaining] = useState(left);

  useEffect(() => {
    const id = setInterval(() => setRemaining(left()), 1000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [start, seconds]);

  const state = remaining === 0 ? "over" : remaining <= 60 ? "low" : "ok";
  return (
    <div className={`ws-timer ${state}`} role="timer" aria-label="Time left on this task">
      <span className="ws-timer-num">{fmt(remaining)}</span>
      <span className="ws-timer-note">{state === "over" ? "Time's up. Send what you have." : "left"}</span>
    </div>
  );
}
