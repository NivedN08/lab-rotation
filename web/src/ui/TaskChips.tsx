import { useEffect, useState } from "react";
import type { RotationState } from "../api/client";

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/**
 * Task 1, 2, 3 in the top bar, with the marks the backend sent and the time left on the current
 * task. Everything comes from the shared rotation state: the countdown counts from the same
 * start time the workspace timer uses, so the two always agree. `noTimer`: judge mode keeps one
 * clock only, the workspace's.
 */
export function TaskChips({ rotation, onOpen, noTimer = false }: { rotation: RotationState; onOpen: () => void; noTimer?: boolean }) {
  const { tasks, current, startedAt, results } = rotation;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!current || !startedAt) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [current, startedAt]);

  // The clock stops once the task has its verdict.
  const done = !!(current && results[current.id]);
  const left = current && startedAt && !done && !noTimer ? Math.max(0, current.seconds - Math.floor((now - startedAt) / 1000)) : null;

  return (
    <nav className="chips" aria-label="Tasks">
      {tasks.map((task, i) => {
        const result = results[task.id];
        const on = current?.id === task.id;
        return (
          <button key={task.id} className="chip" aria-pressed={on} onClick={onOpen} title={task.title}>
            <span className={`dot ${on && !result ? "working" : result ? "done" : ""}`} title={result ? "Finished" : on ? "Working on it" : "Not yet"} />
            Task {i + 1}
            {result && <span className={`mark ${result === "passed" ? "pass" : "fail"}`}>{result}</span>}
          </button>
        );
      })}
      {left !== null && (
        <span className="chip" role="timer" aria-label="Time left on this task">
          {left === 0 ? <span className="mark fail">time's up</span> : `${fmt(left)} left`}
        </span>
      )}
    </nav>
  );
}
