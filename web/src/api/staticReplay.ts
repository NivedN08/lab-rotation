// Static replay mode: answers the client's functions from recorded JSON files (see staticFiles.ts) instead of /api.
// Reading only. Anything that would change the session is refused with a short plain note.

import { STATIC_FILES } from "./staticFiles";
import type { AgentInfo, Cell, CurrentTask, DemoInfo, EventsPage, LabEvent, Mastery, SponsorTotals, TableInfo, TableProfile } from "./types";

export const REPLAY_ONLY = "Replay only: this is a recorded session, so it can't be changed.";

const cache = new Map<string, Promise<unknown>>();

/** Reads the first of these files that exists. Each is read once. */
async function read<T>(paths: string[]): Promise<T> {
  const key = paths.join("|");
  if (!cache.has(key)) {
    cache.set(
      key,
      (async () => {
        for (const path of paths) {
          let res: Response;
          try {
            res = await fetch(path, { headers: { accept: "application/json" } });
          } catch {
            throw new Error("Can't reach the recording.");
          }
          if (res.status === 404) continue;
          if (!res.ok) throw new Error(`The recording answered ${res.status}.`);
          try {
            return await res.json();
          } catch {
            // An app that falls back to index.html for unknown paths answers 200 with a page, not JSON.
            continue;
          }
        }
        throw new Error("This part of the recording isn't available.");
      })(),
    );
    // A failed read is not kept, so it can be tried again.
    cache.get(key)!.catch(() => cache.delete(key));
  }
  return cache.get(key) as Promise<T>;
}

const list = <T>(v: unknown, field: string): T[] => (Array.isArray(v) ? (v as T[]) : ((v as Record<string, T[]>)?.[field] ?? []));

export const staticReplay = {
  refuse: (): Promise<never> => Promise.reject(new Error(REPLAY_ONLY)),

  getDemo: () => read<DemoInfo>(STATIC_FILES.demo()),
  getAgents: () => read<AgentInfo[]>(STATIC_FILES.agents()),
  getCurrentTask: (id: string) => read<CurrentTask | CurrentTask["task"]>(STATIC_FILES.task(id)).then((t) => (t && "task" in (t as object) ? (t as CurrentTask) : { task: (t as CurrentTask["task"]) ?? null })),

  async getEvents(id: string, since: number): Promise<EventsPage> {
    const all = list<LabEvent>(await read(STATIC_FILES.events(id)), "events");
    const events = all.filter((e) => e.seq > since);
    return { events, next: events.length ? events[events.length - 1].seq : since };
  },

  async getTables(id: string, task?: string): Promise<TableInfo[]> {
    return list<TableInfo>(await read(STATIC_FILES.tables(id, task)), "tables");
  },

  async getRows(id: string, table: string, offset: number, limit: number, task?: string): Promise<Cell[][]> {
    return list<Cell[]>(await read(STATIC_FILES.rows(id, table, task)), "rows").slice(offset, offset + limit);
  },

  async getProfile(id: string, table: string, task?: string): Promise<TableProfile> {
    const p = await read<TableProfile | TableProfile["columns"]>(STATIC_FILES.profile(id, table, task));
    return Array.isArray(p) ? { table, columns: p } : p;
  },

  getMastery: (id: string) => read<Mastery>(STATIC_FILES.mastery(id)),
  getSponsors: (id: string) => read<SponsorTotals>(STATIC_FILES.sponsors(id)),
};
