// A short guided tour of your rotation: the cast, your learner profile, the Workspace and how
// to read the floor.

import type { Replay } from "../sim/replay";
import type { Target } from "../world/engine";

/** A rotation tour step: who or what to look at, and whether to open the Workspace. */
export type RotationStep = { title: string; text: string; focus: Target | null; select?: Target; workspace?: boolean };

/** A short tour of your rotation: the cast, your profile, the Workspace and how to read the floor. */
export function buildRotationTour(R: Replay): RotationStep[] {
  const has = (id: string) => R.agents.has(id);
  const n = (id: string) => R.name(id);
  const who = (id: string): Target => ({ type: "agent", id });
  const steps: RotationStep[] = [
    {
      title: "Your rotation",
      text: "Six people work this floor. You are the student in Team A; everyone else is an AI agent with one job. Here is who they are.",
      focus: null,
    },
  ];
  if (has("vale"))
    steps.push({ title: `${n("vale")} runs the lab`, text: `${n("vale")} picks each task, walks it over to your desk, and sits on the panel that rules on your answer.`, focus: who("vale"), select: who("vale") });
  if (has("telem"))
    steps.push({ title: `${n("telem")} searches for you`, text: `Before you answer, ${n("telem")} looks up the topic and tells you what to watch for. After the verdict, he brings a real case of the same mistake.`, focus: who("telem"), select: who("telem") });
  if (has("learner"))
    steps.push({
      title: "This is you",
      text: `Your desk is in Team A.${has("sam") ? ` ${n("sam")}, your mentor, sits at the back of the room and can drop by with a hint, never the answer.` : ""}`,
      focus: who("learner"),
      select: who("learner"),
    });
  if (has("riley"))
    steps.push({ title: `${n("riley")} works the same task, blind`, text: `${n("riley")} sits on the other side of the wall. When you both answer, the two answers meet at the hatch, and it flashes green when they match.`, focus: { type: "fixture", id: "hatch" }, select: who("riley") });
  if (has("ines"))
    steps.push({ title: `${n("ines")} runs the Bruin checks`, text: `${n("ines")} gets both answers without knowing whose is whose, runs the checks at the referee table, and seals the verdict.`, focus: who("ines"), select: who("ines") });
  steps.push(
    { title: "Your learner profile", text: "After each verdict a note flies from your desk to the vault, and your score on that trap goes up or down. Your Details panel shows it.", focus: { type: "fixture", id: "vault" } },
    { title: "The Workspace", text: "Read the tables, run SQL, click rows to cite them as evidence, and send your answer before the timer runs out.", focus: null, workspace: true },
    { title: "Every move has a reason", text: "The lab log says what happened and why. Drag the timeline to go back, press Live to return to now, and turn Follow off to keep the camera still.", focus: null },
  );
  return steps;
}
