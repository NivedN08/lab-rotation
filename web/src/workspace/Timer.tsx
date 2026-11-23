import { useEffect, useState } from "react";
import { useDemo, useRotation, type LabEvent } from "../api/client";

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/**
 * What the events say about this task's clock: when it began, when the answer stopped it, and whether the
 * learner answered before time ran out. Read from the events, so it holds after a reload and follows a demo's seek.
 */
function clockFacts(events: LabEvent[], taskId: string, seconds: number) {
  const idOf = (e: LabEvent) => (e.data as { taskId?: string } | undefined)?.taskId ?? e.task;
  const picked = events.find((e) => e.k === "task.picked" && idOf(e) === taskId);
  const answer = events.find((e) => e.k === "learner.answer" && e.task === taskId);
  return {
    // The clock stops when the answer is sent, not at the verdict: grading time does not count against the learner.
    stoppedAt: picked && answer ? Math.max(0, seconds - Math.floor(answer.t - picked.t)) : undefined,
    // An answer that came in at or after the deadline is the server's "can't tell", not the learner's.
    answeredInTime: !!(picked && answer && answer.t - picked.t < seconds),
  };
}

/**
 * Counts down a task's time. Live, it counts real seconds from the shared clock (`startedAt`).
 * In the demo it follows the recording's clock instead, so speed, pause, seek and loop all show correctly.
 * It stops when the answer is sent.
 */
export function Timer({ taskId, startedAt, seconds }: { taskId: string; startedAt: number; seconds: number }) {
  const demo = useDemo();
  const { events } = useRotation();
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

  const { stoppedAt, answeredInTime } = clockFacts(events, taskId, seconds);
  const stopped = stoppedAt !== undefined;
  if (stopped) remaining = stoppedAt;

  const over = remaining === 0 && !answeredInTime;
  const state = over ? "over" : remaining === 0 || stopped ? "done" : remaining <= 60 ? "low" : "ok";
  return (
    <div className={`ws-timer ${state}`} role="timer" aria-label="Time left on this task">
      {stopped && !over ? (
        <span className="ws-timer-note">
          Answered with <b className="ws-timer-num">{fmt(remaining)}</b> left
        </span>
      ) : (
        <>
          <span className="ws-timer-num">{fmt(remaining)}</span>
          <span className="ws-timer-note">{over ? "Time's up. The panel recorded 'can't tell'." : "left"}</span>
        </>
      )}
    </div>
  );
}
