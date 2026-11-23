import { useEffect, useState } from "react";

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/** Counts down from the shared clock (`startedAt` comes from the rotation state). */
export function Timer({ startedAt, seconds }: { startedAt: number; seconds: number }) {
  const left = () => Math.max(0, seconds - Math.floor((Date.now() - startedAt) / 1000));
  const [remaining, setRemaining] = useState(left);

  useEffect(() => {
    setRemaining(left());
    const id = setInterval(() => setRemaining(left()), 1000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startedAt, seconds]);

  const state = remaining === 0 ? "over" : remaining <= 60 ? "low" : "ok";
  return (
    <div className={`ws-timer ${state}`} role="timer" aria-label="Time left on this task">
      <span className="ws-timer-num">{fmt(remaining)}</span>
      <span className="ws-timer-note">{state === "over" ? "Time's up. Send what you have." : "left"}</span>
    </div>
  );
}
