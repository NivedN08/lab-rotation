// One shared rotation state for the whole app: one session, one clock, one event poll.
// The workspace, the top bar and the floor all read it with useRotation() or subscribeEvents().
// The first reader starts the session and the poll; when nobody is reading, the poll pauses.

import { useSyncExternalStore } from "react";
import { getCurrentTask, getEvents, startSession } from "./client";
import type { LabEvent, StartOptions, TaskInfo } from "./types";

export type TaskResult = "passed" | "failed";

export type RotationState = {
  sessionId: string | null;
  /** Every task in the rotation, in order. */
  tasks: { id: string; title: string }[];
  current: TaskInfo | null;
  /** ms since epoch when the current task's clock started: the value the Timer counts from. */
  startedAt: number | null;
  /** Filled from verdict events. */
  results: Record<string, TaskResult>;
  /** Every event so far, from the one shared poll. */
  events: LabEvent[];
  /** Set when the session could not start. Cleared by rotation.retry(). */
  error: string | null;
  /** True after an answer is sent, until the server hands out the next task (or none). */
  awaitingNext: boolean;
};

const POLL_MS = 1000;
const startKey = (id: string) => `lab-rotation.workspace.start.${id}`;

let state: RotationState = { sessionId: null, tasks: [], current: null, startedAt: null, results: {}, events: [], error: null, awaitingNext: false };
const stateSubs = new Set<() => void>();
const eventSubs = new Set<(events: LabEvent[]) => void>();

let since = 0;
let running = false;
let starting = false;
let startOptions: StartOptions | undefined;

function set(patch: Partial<RotationState>) {
  state = { ...state, ...patch };
  stateSubs.forEach((f) => f());
}

/** Start time for a task, kept so closing the panel or reloading does not reset the clock. */
function clockFor(id: string): number {
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

const taskPatch = (task: TaskInfo | null) => ({ current: task, startedAt: task ? clockFor(task.id) : null });
const nobodyReading = () => stateSubs.size === 0 && eventSubs.size === 0;

async function tick() {
  if (!running) return;
  if (nobodyReading()) {
    running = false;
    return;
  }
  try {
    const page = await getEvents(state.sessionId!, since);
    since = page.next;
    if (page.events.length) {
      const results = { ...state.results };
      for (const e of page.events) {
        const d = e.data as { taskId?: string; result?: TaskResult } | undefined;
        if (e.k === "verdict" && d?.taskId && d.result) results[d.taskId] = d.result;
      }
      set({ events: [...state.events, ...page.events], results });
      eventSubs.forEach((f) => f(page.events));
    }
    if (state.awaitingNext) {
      const { task } = await getCurrentTask(state.sessionId!);
      if (task?.id !== state.current?.id) set({ ...taskPatch(task), awaitingNext: false });
    }
  } catch {
    /* a missed poll is not fatal: try again next second */
  }
  setTimeout(tick, POLL_MS);
}

function begin() {
  if (running || starting) return;
  starting = true;
  (async () => {
    try {
      if (!state.sessionId) {
        const s = await startSession(startOptions);
        set({ sessionId: s.sessionId, tasks: s.tasks, ...taskPatch(s.task), error: null });
      }
      running = true;
      tick();
    } catch (e) {
      set({ error: (e as Error).message });
    } finally {
      starting = false;
    }
  })();
}

export const rotation = {
  /** Choose rotation or judge mode (and the learner's name) before the session starts. Has no effect once it has. */
  configure(options: StartOptions) {
    if (!state.sessionId) startOptions = options;
  },
  /** Try again after a failed start. */
  retry() {
    set({ error: null });
    begin();
  },
  /** Call after the answer is sent: the next task is fetched on the shared poll. */
  answerSent() {
    if (!state.awaitingNext) set({ awaitingNext: true });
  },
};

export function useRotation(): RotationState {
  return useSyncExternalStore(
    (f) => {
      stateSubs.add(f);
      begin();
      return () => stateSubs.delete(f);
    },
    () => state,
  );
}

/** New events only, as they arrive. For earlier ones, read `events` from useRotation(). */
export function subscribeEvents(cb: (events: LabEvent[]) => void): () => void {
  eventSubs.add(cb);
  begin();
  return () => eventSubs.delete(cb);
}
