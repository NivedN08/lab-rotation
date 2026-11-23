// One shared rotation state for the whole app: one session, one clock, one event poll.
// The workspace, the top bar and the floor all read it with useRotation() or subscribeEvents().
// The first reader starts the session and the poll; when nobody is reading, the poll pauses.

import { useSyncExternalStore } from "react";
import { getCurrentTask, getEvents, startSession } from "./client";
import { taskClockStart } from "./clock";
import type { LabEvent, StartOptions, TaskInfo } from "./types";

export type TaskResult = "passed" | "failed";

export type RotationState = {
  sessionId: string | null;
  /** Every task in the rotation, in order. */
  tasks: { id: string; title: string }[];
  current: TaskInfo | null;
  /**
   * ms since epoch when the current task's clock started: the value the Timer counts from. The clock starts when Riley sits
   * down at `riley_desk` after the brief (the server's timer starts there too), so this is `null` while the brief is going on.
   */
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
// Keys start with lab-rotation.workspace. so a new sample session clears them with the rest.
const startGuessKey = (sessionId: string) => `lab-rotation.workspace.sessionstart.${sessionId}`;
const clockKey = (sessionId: string, taskId: string) => `lab-rotation.workspace.clock.${sessionId}.${taskId}`;

let state: RotationState = { sessionId: null, tasks: [], current: null, startedAt: null, results: {}, events: [], error: null, awaitingNext: false };

const stateSubs = new Set<() => void>();
const eventSubs = new Set<(events: LabEvent[]) => void>();

let since = 0;
let running = false;
let starting = false;
let startOptions: StartOptions | undefined;
let driven = false; // true while the demo player, not the live poll, feeds the state
let epoch = 0;
let retryHook: (() => void) | null = null;
const jumpSubs = new Set<(t: number, events: LabEvent[]) => void>();
const initial: RotationState = { sessionId: null, tasks: [], current: null, startedAt: null, results: {}, events: [], error: null, awaitingNext: false };

function set(patch: Partial<RotationState>) {
  state = { ...state, ...patch };
  stateSubs.forEach((f) => f());
}

/**
 * The wall-clock time at which the session's `t` was 0, as well as the poll can tell. An event cannot have been received before
 * it happened, so `received - t` is never earlier than the true start, and the smallest such value over every event seen is
 * within about one poll of it. Kept in sessionStorage so a reload does not lose it.
 */
let startGuess: number | null = null;

function noteArrival(sessionId: string, events: LabEvent[]) {
  const now = Date.now();
  if (startGuess === null) {
    try {
      const saved = Number(sessionStorage.getItem(startGuessKey(sessionId)));
      if (saved) startGuess = saved;
    } catch {
      /* ignore */
    }
  }
  let best = startGuess;
  for (const e of events) best = Math.min(best ?? Infinity, now - e.t * 1000);
  if (best !== startGuess && best !== null) {
    startGuess = best;
    try {
      sessionStorage.setItem(startGuessKey(sessionId), String(best));
    } catch {
      /* ignore */
    }
  }
}

/** Starts the current task's clock once Riley has sat down. Once set it does not move, and survives a reload. */
function refreshClock() {
  const { sessionId, current, startedAt, events } = state;
  if (!sessionId || !current || startedAt !== null || startGuess === null) return;
  const t0 = taskClockStart(events, current.id);
  if (t0 === undefined) return;
  let at = Math.round(startGuess + t0 * 1000);
  try {
    const saved = Number(sessionStorage.getItem(clockKey(sessionId, current.id)));
    if (saved) at = saved;
    else sessionStorage.setItem(clockKey(sessionId, current.id), String(at));
  } catch {
    /* ignore */
  }
  set({ startedAt: at });
}

const taskPatch = (task: TaskInfo | null) => ({ current: task, startedAt: null });
const nobodyReading = () => stateSubs.size === 0 && eventSubs.size === 0;

async function tick(ep: number) {
  if (!running || driven || ep !== epoch) return;
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
      noteArrival(state.sessionId!, page.events);
      set({ events: [...state.events, ...page.events], results });
      refreshClock();
      eventSubs.forEach((f) => f(page.events));
    }
    if (state.awaitingNext) {
      const { task } = await getCurrentTask(state.sessionId!);
      if (task?.id !== state.current?.id) {
        set({ ...taskPatch(task), awaitingNext: false });
        refreshClock();
      }
    }
  } catch {
    /* a missed poll is not fatal: try again next second */
  }
  setTimeout(() => tick(ep), POLL_MS);
}

function begin() {
  if (running || starting || driven) return;
  starting = true;
  (async () => {
    try {
      if (!state.sessionId) {
        const s = await startSession(startOptions);
        set({ sessionId: s.sessionId, tasks: s.tasks, ...taskPatch(s.task), error: null });
      }
      running = true;
      tick(epoch);
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
    if (retryHook) retryHook();
    else begin();
  },
  /** Call after the answer is sent: the next task is fetched on the shared poll. */
  answerSent() {
    if (!state.awaitingNext) set({ awaitingNext: true });
  },
};

/**
 * For the demo player only. While it holds the state, the live poll is off and the same state and events
 * a live session produces are fed in from a recorded session instead.
 */
export const drive = {
  claim(onRetry: () => void) {
    driven = true;
    epoch++;
    running = false;
    since = 0;
    retryHook = onRetry;
    set({ ...initial, awaitingNext: true });
  },
  /** The recorded session is known: set its id and task list. */
  open(sessionId: string, tasks: RotationState["tasks"]) {
    set({ sessionId, tasks, error: null });
  },
  fail(message: string) {
    set({ error: message });
  },
  /** Normal playback: new events are handed to subscribeEvents readers. */
  frame(patch: Partial<RotationState>, fresh: LabEvent[]) {
    set(patch);
    if (fresh.length) eventSubs.forEach((f) => f(fresh));
  },
  /** A seek or a loop: the state is replaced and subscribeJump readers get everything up to `t` at once. */
  jump(patch: Partial<RotationState>, t: number) {
    set(patch);
    jumpSubs.forEach((f) => f(t, patch.events ?? []));
  },
  release() {
    driven = false;
    retryHook = null;
    epoch++;
    since = 0;
    set({ ...initial });
    if (!nobodyReading()) begin();
  },
};

/** Called when the demo seeks or loops, with the new time and every event up to it. Floors reset and redraw from this. */
export function subscribeJump(cb: (t: number, events: LabEvent[]) => void): () => void {
  jumpSubs.add(cb);
  return () => jumpSubs.delete(cb);
}

/** The current state without subscribing (for code outside React). */
export const getRotation = (): RotationState => state;

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
