// The floor for a rotation: the people come from the backend's agent list, nothing else.
// It has no recorded history; everything that happens arrives as live events.

import type { AgentInfo } from "../api/types";
import type { Role, Run } from "../data/types";

const ROLES = new Set<string>(["director", "library", "team-a", "team-b", "team-c", "referee", "solo", "head", "other"]);

/** Shape the backend's agent list as a run the floor can draw: everyone present from the start. */
export function rotationRun(listed: AgentInfo[]): Run {
  // The agent list names the panel; you, the learner, are on the floor too (id "learner",
  // your desk in Team A), whether or not the list includes you.
  const agents = listed.some((a) => a.id === "learner")
    ? listed
    : [...listed, { id: "learner", name: "You", role: "team-a", reads: "Everything you open in the workspace.", portrait: null } as AgentInfo];
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
      title: a.title,
      reads: a.reads,
      portrait: a.portrait,
    })),
    events: [],
    notes: {},
    searches: [],
    totals: null,
  };
}
