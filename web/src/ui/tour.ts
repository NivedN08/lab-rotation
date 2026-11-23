// A short guided tour through one run, built from the run's own events so every number in a
// caption comes from the log.

import type { Ev } from "../data/types";
import type { Replay } from "../sim/replay";
import type { Target } from "../world/engine";

export type TourStep = { t: number; title: string; text: string; focus: Target | null; select?: Target; zoom?: number };

function clip(s: string, n: number) {
  const c = s.replace(/\s+/g, " ").trim();
  return c.length > n ? c.slice(0, n).replace(/\s+\S*$/, "") + "…" : c;
}

export function buildTour(R: Replay): TourStep[] {
  const ev = R.run.events;
  const find = (f: (e: Ev) => boolean) => ev.find(f);
  const steps: TourStep[] = [];
  const studies = R.run.studies.length;
  const lab = R.run.agents.filter((a) => a.role !== "solo").length;
  const solo = R.run.agents.filter((a) => a.role === "solo").length;

  const libStart = find((e) => e.k === "agent.start" && e.phase === "library");
  steps.push({
    t: (libStart?.t ?? 0) + 6,
    title: `${studies === 8 ? "Eight" : studies} studies start at once`,
    text: `${lab} lab agents work through ${studies} biology analyses side by side. Each study gets a librarian and two teams that never see each other's work.${solo ? ` In the room on the right, ${solo} solo agents tackle the same studies alone, for comparison.` : ""}`,
    focus: null,
  });

  const libs = R.run.agents.filter((a) => a.role === "library");
  const busiest = libs.sort((a, b) => R.searches(b.id, 1e9).length - R.searches(a.id, 1e9).length)[0];
  if (busiest) {
    const ss = R.searches(busiest.id, 1e9);
    const notes = R.notesBy(busiest.id, 1e9).length;
    const study = R.studies.get(busiest.study ?? "");
    steps.push({
      t: (ss[2]?.t ?? ss[0]?.t ?? 60) + 1,
      title: "The library reads up first",
      text: `${R.name(busiest.id)} runs ${ss.length} web searches on how to study ${study?.title.toLowerCase() ?? "the problem"} and what usually goes wrong, then writes ${notes} notes to memory. Click a librarian to see the articles.`,
      focus: { type: "agent", id: busiest.id },
      select: { type: "agent", id: busiest.id },
    });
  }

  const brief = find((e) => e.k === "relay.briefing");
  if (brief) {
    steps.push({
      t: brief.t - 3,
      title: "Only Team A is briefed",
      text: "The librarian carries its findings to the director, who passes the useful ones to Team A only. Team B starts from the data alone, so the two teams don't begin with the same ideas.",
      focus: { type: "agent", id: "director" },
    });
  }

  const dis = find((e) => e.k === "compare" && e.agree === false);
  if (dis) {
    const f = Object.values(dis.fields ?? {});
    steps.push({
      t: dis.t - 4,
      title: "Answers meet only at the hatch",
      text: `There is no door between Team A and Team B. Their answers meet at this hatch, where the lab compares them field by field. In ${dis.s}, the first answers differ on ${f.filter((x) => !x).length} of ${f.length} fields.`,
      focus: { type: "fixture", id: "hatch" },
    });
    const q = find((e) => e.k === "relay.leak_check" && e.passed === true && e.s === dis.s);
    if (q) {
      steps.push({
        t: q.t - 3,
        title: "Warning signs become questions",
        text: `The director never tells a team the other's answer. It turns what the other team noticed into a question: “${clip((q.q ?? "").replace(/^QUESTION FROM THE DIRECTOR:\s*/, ""), 170)}”`,
        focus: { type: "agent", id: q.to! },
        select: { type: "agent", id: q.to! },
      });
    }
  }

  const chal = find((e) => e.k === "agent.finish" && e.a === "director" && e.phase === "challenge");
  const chalStudy = chal?.s ? R.studies.get(chal.s) : null;
  if (chal && chalStudy?.challenge?.verdict) {
    steps.push({
      t: chal.t + 1,
      title: "Agreement has to survive a challenge",
      text: `When both teams agree, the director tries to break the answer before it is reported. On ${chalStudy.id}: “${clip(chalStudy.challenge.verdict, 180)}”`,
      focus: { type: "agent", id: "director" },
      select: { type: "study", id: chalStudy.id },
    });
  }

  const verdicts = ev.filter((e) => e.k === "referee.verdict" && e.pick !== "neither");
  const v = verdicts.find((e) => R.studies.get(e.s ?? "")?.grade?.lab) ?? verdicts[0];
  if (v?.s) {
    const s = R.studies.get(v.s)!;
    steps.push({
      t: v.t - 2,
      title: "A referee must test, not vote",
      text: `If the teams still disagree, a referee gets both answers as X and Y, not knowing whose is whose, and has to run a test. In ${s.id} it picked ${v.pick}: “${clip(s.referee?.reason ?? s.referee?.difference ?? "", 160)}”`,
      focus: { type: "agent", id: `${v.s}-referee` },
      select: { type: "agent", id: `${v.s}-referee` },
    });
  }

  const tot = R.run.totals;
  steps.push({
    t: R.end,
    title: "Graded after everyone left",
    text: tot
      ? `No agent ever sees a score. Once every agent had exited, the benchmark's own grader checked each answer: the lab passed ${tot.lab_passed} of ${tot.lab_studies} studies. Solo attempts passed ${tot.baseline_attempts_passed} of ${tot.baseline_attempts}, and a vote over them ${tot.vote_passed} of ${tot.vote_studies}. Click a study at the top to see how it went.`
      : "This run has not been graded yet. Answers are graded once, after every agent has left the lab.",
    focus: null,
  });
  return steps;
}

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
    steps.push({ title: `${n("telem")} searches for you`, text: `When a task needs a method, ${n("telem")} searches papers and the web from the library terminal and carries what it finds to your desk.`, focus: who("telem"), select: who("telem") });
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
