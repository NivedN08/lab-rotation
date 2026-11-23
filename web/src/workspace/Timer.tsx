import { useEffect, useState } from "react";
import { taskClockStart, useDemo, useRotation, type LabEvent } from "../api/client";

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/**
 * The task's clock, from the events. It starts when Riley sits down at `riley_desk` after the brief (the server's timer starts
 * there too), stops when the learner's answer is sent (so grading time does not count against them), and the answer counts as
 * in time only if it came before the deadline. Read from events, so it holds after a reload and follows a demo's seek.
 */
function clockFacts(events: LabEvent[], taskId: string, seconds: number) {
  const start = taskClockStart(events, taskId);
  const answer = events.find((e) => e.k === "learner.answer" && e.task === taskId);
  // An answer sent before the clock started used no time.
  const used = start !== undefined && answer ? Math.max(0, answer.t - start) : undefined;
  return {
    start,
    // Seconds left at the moment the answer arrived.
    stoppedAt: used !== undefined ? Math.max(0, seconds - Math.floor(used)) : undefined,
    // An answer at or after the deadline is the server's "can't tell", not the learner's.
    answeredInTime: used !== undefined && used < seconds,
  };
}

/**
 * Counts down a task's time. Live, it counts real seconds from the shared clock (`startedAt`, null until the clock starts).
 * In the demo it follows the recording's clock instead, so speed, pause, seek and loop all show correctly.
 * It stops when the answer is sent.
 */
export function Timer({ taskId, startedAt, seconds }: { taskId: string; startedAt: number | null; seconds: number }) {
  const demo = useDemo();
  const { events } = useRotation();
  const left = () => (startedAt === null ? seconds : Math.max(0, seconds - Math.floor((Date.now() - startedAt) / 1000)));
  const [live, setLive] = useState(left);

  useEffect(() => {
    setLive(left());
    const id = setInterval(() => setLive(left()), 1000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startedAt, seconds]);

  const { start, stoppedAt, answeredInTime } = clockFacts(events, taskId, seconds);
  let remaining = live;
  let started = startedAt !== null;
  if (demo.status === "ready") {
    // Recording time since Riley sat down.
    started = start !== undefined && demo.position >= start;
    remaining = started ? Math.max(0, seconds - Math.floor(demo.position - (start as number))) : seconds;
  }

  const stopped = stoppedAt !== undefined;
  if (stopped) {
    remaining = stoppedAt;
    started = true;
  }

  if (!started) {
    return (
      <div className="ws-timer wait" role="timer" aria-label="Time allowed for this task">
        <span className="ws-timer-num">{fmt(seconds)}</span>
        <span className="ws-timer-note">The clock starts when the brief ends</span>
      </div>
    );
  }

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
