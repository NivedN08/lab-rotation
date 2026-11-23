// The demo: replays a real recorded session from the backend through the same rotation state and events
// as a live one, with play/pause, speed, seek and loop. Front end only; the one backend route is GET /api/demo.
// In mock mode the fake session stands in, and `sample` is true so the page can say "Sample data".
// Start it with startDemo() or ?demo=1. stopDemo() goes back to a live session.

import { useSyncExternalStore } from "react";
import { getDemo, getEvents, useMock } from "./client";
import { mock } from "./mock";
import { drive } from "./session";
import { taskClockStart } from "./clock";
import { hideWhispers, withholdWhispers } from "./visibility";
import type { AgentId, LabEvent, TaskInfo } from "./types";

export type DemoStatus = "off" | "loading" | "ready" | "error";

export type DemoState = {
  status: DemoStatus;
  error: string | null;
  playing: boolean;
  speed: number;
  /** Seconds since the recorded session began. */
  position: number;
  start: number;
  end: number;
  /** True when this is the fake session (mock mode): the page must show "Sample data". */
  sample: boolean;
  /** Every recorded event's time, kind and agent, so the timeline can draw marks and rewind. */
  timeline: { seq: number; t: number; k: string; agent: AgentId }[];
};

const TICK_MS = 200;
const off: DemoState = { status: "off", error: null, playing: false, speed: 1, position: 0, start: 0, end: 0, sample: false, timeline: [] };

let state: DemoState = off;
let events: LabEvent[] = [];
let sessionId = "";
let timer: ReturnType<typeof setInterval> | null = null;
let last = 0; // wall clock of the previous tick
let prevPos = 0; // position the last frame was published at
let token = 0; // ignores a load that was stopped or restarted
const subs = new Set<() => void>();

function set(patch: Partial<DemoState>) {
  state = { ...state, ...patch };
  subs.forEach((f) => f());
}

// ---- turning recorded events into the rotation state ----

const taskOf = (e: LabEvent, n: number): TaskInfo => {
  // In a replay the task comes from task.picked only.
  const d = (e.data ?? {}) as Partial<TaskInfo> & { taskId?: string };
  return {
    id: String(d.taskId ?? e.task ?? `t${n}`),
    title: d.title ?? `Task ${n}`,
    brief: d.brief ?? e.text ?? "",
    seconds: d.seconds ?? 600,
    tier: d.tier,
    claim: d.claim,
    reason: d.reason,
    dictionary: d.dictionary,
  };
};

function derive(pos: number) {
  const picks = events.filter((e) => e.k === "task.picked");
  const tasks = picks.map((e, i) => taskOf(e, i + 1));
  // A finished session has whisper words filled in; hide them until the verdict has played.
  const seen = withholdWhispers(events.filter((e) => e.t <= pos));
  const pickIdx = seen.filter((e) => e.k === "task.picked").length - 1;
  const current = pickIdx >= 0 ? tasks[pickIdx] : null;
  const results: Record<string, "passed" | "failed"> = {};
  for (const e of seen) {
    const d = e.data as { taskId?: string; result?: "passed" | "failed" } | undefined;
    if (e.k === "verdict" && d?.taskId && d.result) results[d.taskId] = d.result;
  }
  // The task clock starts when Riley sits down after the brief; null until the recording gets there (at normal speed).
  const clockT = current ? taskClockStart(seen, current.id) : undefined;
  const startedAt = clockT !== undefined ? Date.now() - (pos - clockT) * 1000 : null;
  return { tasks: tasks.map(({ id, title }) => ({ id, title })), seen, patch: { current, startedAt, results, events: seen, awaitingNext: !current } };
}

function publish(jumped: boolean) {
  const pos = state.position;
  const d = derive(pos);
  if (jumped) {
    drive.jump(d.patch, pos);
  } else {
    drive.frame(d.patch, d.seen.filter((e) => e.t > prevPos));
  }
  prevPos = pos;
}

// ---- the clock ----

function tick() {
  const now = Date.now();
  let pos = state.position + ((now - last) / 1000) * state.speed;
  last = now;
  if (pos >= state.end) {
    // Loop: back to the beginning, as a jump so the floor redraws from the start.
    set({ position: state.start });
    publish(true);
    return;
  }
  set({ position: pos });
  publish(false);
}

function run() {
  stopClock();
  last = Date.now();
  timer = setInterval(tick, TICK_MS);
}

function stopClock() {
  if (timer) clearInterval(timer);
  timer = null;
}

// ---- loading ----

async function load() {
  const mine = ++token;
  drive.claim(load);
  set({ ...off, status: "loading", sample: useMock() });
  try {
    let info = await getDemo();
    let sample = useMock();
    if (info.session === null) {
      // The backend has no recorded demo: fall back to the fake session, and say so.
      info = await mock.getDemo();
      sample = true;
    }
    const session = info.session as string;
    // The full event list from the beginning, with the same events route a live session uses.
    const all: LabEvent[] = [];
    let since = 0;
    for (let i = 0; i < 200; i++) {
      const page = await getEvents(session, since);
      if (!page.events.length) break;
      all.push(...page.events);
      since = page.next;
    }
    if (mine !== token) return;
    events = all.sort((a, b) => a.t - b.t || a.seq - b.seq);
    sessionId = session;
    const first = derive(info.start);
    drive.open(sessionId, first.tasks);
    set({
      sample,
      status: "ready",
      playing: true,
      speed: info.speed || 1,
      position: info.start,
      start: info.start,
      end: info.end,
      timeline: events.map(({ seq, t, k, agent }) => ({ seq, t, k, agent })),
    });
    prevPos = info.start - 0.001;
    publish(true);
    run();
  } catch (e) {
    if (mine !== token) return;
    const message = (e as Error).message;
    set({ status: "error", error: message });
    drive.fail(message);
  }
}

// ---- public controls ----

export const demo = {
  play() {
    if (state.status !== "ready" || state.playing) return;
    set({ playing: true });
    run();
  },
  pause() {
    if (state.status !== "ready" || !state.playing) return;
    stopClock();
    set({ playing: false });
  },
  toggle() {
    state.playing ? demo.pause() : demo.play();
  },
  /** 1 is normal speed. */
  setSpeed(speed: number) {
    if (speed > 0) set({ speed });
  },
  /** Jump to a time (seconds since the recorded session began). Works forwards and backwards. */
  seek(t: number) {
    if (state.status !== "ready") return;
    set({ position: Math.min(Math.max(t, state.start), state.end) });
    last = Date.now();
    publish(true);
  },
};

/** Start the demo: fetch the recorded session and play it from the beginning, looping. */
export function startDemo() {
  if (state.status === "loading" || state.status === "ready") return;
  load();
}

/** Leave the demo and go back to a live session. */
export function stopDemo() {
  token++;
  stopClock();
  events = [];
  set({ ...off });
  drive.release();
}

/** Every recorded event (whisper words hidden until the verdict, as everywhere), for readers that need what is still to come (for example mastery before and after an update). */
export const getRecordedEvents = (): LabEvent[] => hideWhispers(events);

/** The demo's current state without subscribing (for code outside React). */
export const getDemoState = (): DemoState => state;

export function useDemo(): DemoState {
  return useSyncExternalStore(
    (f) => {
      subs.add(f);
      return () => subs.delete(f);
    },
    () => state,
  );
}

// ?demo=1 starts it as soon as the app loads, before anything starts a live session.
try {
  if (new URLSearchParams(window.location.search).get("demo") === "1") {
    // Take the state now so no live session starts first; fetch once every module has finished loading.
    drive.claim(load);
    set({ status: "loading" });
    setTimeout(load, 0);
  }
} catch {
  /* no window */
}
