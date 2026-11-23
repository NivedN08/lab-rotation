import type { LabEvent } from "./types";

/**
 * When a task's clock starts, in session seconds (`t`), read from the events. Per the backend (requests/n1.md):
 * the clock starts at the `agent.move` of `riley` to `riley_desk` after the brief, and the server's own timer starts
 * there too. `task.picked`'s `t` is only a fallback, for a recording that has no such walk but went on past the brief.
 * Returns undefined while the clock has not started (the brief is still going on).
 */
export function taskClockStart(events: LabEvent[], taskId: string): number | undefined {
  const idOf = (e: LabEvent) => (e.data as { taskId?: string } | undefined)?.taskId ?? e.task;
  const picked = [...events].reverse().find((e) => e.k === "task.picked" && idOf(e) === taskId);
  if (!picked) return undefined;
  const sits = events.find((e) => e.k === "agent.move" && e.agent === "riley" && (e.data as { place?: string } | undefined)?.place === "riley_desk" && e.t >= picked.t);
  if (sits) return sits.t;
  const movedOn = events.some((e) => e.t > picked.t && e.task === taskId && (e.k === "learner.query" || e.k === "learner.answer" || e.k === "verdict"));
  return movedOn ? picked.t : undefined;
}
