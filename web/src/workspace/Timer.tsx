import { useEffect, useState } from "react";
import { useDemo } from "../api/client";

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/**
 * Counts down a task's time. Live, it counts real seconds from the shared clock (`startedAt`).
 * In the demo it follows the recording's clock instead, so speed, pause, seek and loop all show correctly.
 */
export function Timer({ startedAt, seconds }: { startedAt: number; seconds: number }) {
  const demo = useDemo();
  const left = () => Math.max(0, seconds - Math.floor((Date.now() - startedAt) / 1000));
  const [live, setLive] = useState(left);

  useEffect(() => {
    setLive(left());
    const id = setInterval(() => setLive(left()), 1000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startedAt, seconds]);

  let remaining = live;
  if (demo.status === "ready") {
    // Recording time since this task was picked.
    const picked = [...demo.timeline].reverse().find((e) => e.k === "task.picked" && e.t <= demo.position);
    const elapsed = demo.position - (picked?.t ?? demo.start);
    remaining = Math.max(0, seconds - Math.floor(elapsed));
  }

  const state = remaining === 0 ? "over" : remaining <= 60 ? "low" : "ok";
  return (
    <div className={`ws-timer ${state}`} role="timer" aria-label="Time left on this task">
      <span className="ws-timer-num">{fmt(remaining)}</span>
      <span className="ws-timer-note">{state === "over" ? "Time's up. Send what you have." : "left"}</span>
    </div>
  );
}
