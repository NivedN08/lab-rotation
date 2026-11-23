// The floor for a rotation: the people come from the backend's agent list, nothing else.
// It has no recorded history; everything that happens arrives as live events.

import type { AgentInfo } from "../api/types";
import type { Role, Run } from "../data/types";

const ROLES = new Set<string>(["director", "library", "team-a", "team-b", "team-c", "referee", "solo", "head", "other"]);

/** Shape the backend's agent list as a run the floor can draw: everyone present from the start. */
export function rotationRun(agents: AgentInfo[]): Run {
  return {
    run: "rotation",
    label: "Your rotation",
    started: new Date().toISOString(),
    duration: 0,
    lab_end: null,
    finished: false,
    config: {},
    studies: [],
    agents: agents.map((a) => ({
      id: a.id,
      role: (ROLES.has(a.role) ? a.role : "other") as Role,
      study: null,
      model: null,
      // The learner walks in when the session starts; everyone else is already at their desk.
      sessions: a.id === "learner" ? [] : [{ phase: "rotation", study: null, start: 0, end: null }],
      cost: 0,
      name: a.name,
      title: (a as AgentInfo & { title?: string }).title,
      reads: a.reads,
      portrait: a.portrait,
    })),
    events: [],
    notes: {},
    searches: [],
    totals: null,
  };
}
