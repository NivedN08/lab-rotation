import type { LabEvent } from "../api/types";
import { BenchCard, CaseCard } from "../panels";
import { caseEvent, isCase, plainLine, plainNumbers } from "../sim/replay";
import { Safe } from "./Safe";

// The demo as a guided story: one scene at a time, following the task as the recording has it.
// Scene starts come from the recording's own events; the words under each come from those events
// (their text and why), with one plain line per scene saying what is going on.

type Mark = { t: number; k: string; agent: string };

/** `after`: the scene only starts once that scene has (the panel confers about your answer, not before it). */
type SceneDef = { id: string; title: string; intro: string; starts: (m: Mark) => boolean; after?: string };

const SCENES: SceneDef[] = [
  { id: "brief", title: "The brief", intro: "Dr. Vale picks your task and brings it to your desk.", starts: (m) => m.k === "task.picked" },
  { id: "context", title: "Context", intro: "Telem looks up the topic, so you know what to watch for. She keeps the real case for later.", starts: (m) => m.agent === "telem" },
  { id: "rival", title: "The rival", intro: "Riley sits down next door to work the same task, without ever seeing yours.", starts: (m) => m.agent === "riley" },
  { id: "analysis", title: "Analysis", intro: "You query the tables to test the claim.", starts: (m) => m.k === "learner.query" },
  { id: "question", title: "The question", intro: "Sam sees where you are stuck and drops by with one question, never the answer.", starts: (m) => m.agent === "sam" && m.k === "agent.say" },
  { id: "answer", title: "Your answer", intro: "You send your verdict and evidence, and Riley's answer meets yours at the hatch.", starts: (m) => m.k === "learner.answer" },
  { id: "panel", title: "The panel confers", intro: "Dr. Vale, Sam and Ines talk it over in private before anyone rules.", starts: (m) => m.k === "panel.whisper", after: "answer" },
  { id: "verdict", title: "The verdict", intro: "Ines runs the Bruin checks on your answer and seals the verdict.", starts: (m) => m.k === "check.result" || m.k === "verdict", after: "answer" },
  { id: "case", title: "A real case", intro: "With the verdict in, Telem brings a real case of the same mistake, and Dr. Vale says whether the morning's news shaped the pick.", starts: (m) => m.agent === "telem", after: "verdict" },
  { id: "next", title: "What's next", intro: "Your mastery of this trap moves, and that shapes the task you get next.", starts: (m) => m.k === "mastery.update", after: "verdict" },
];

export type Scene = { id: string; title: string; intro: string; start: number };

/** Each scene starts at its first event after the brief, in the order the recording has them. */
export function buildScenes(timeline: Mark[]): Scene[] {
  const brief = timeline.find((m) => m.k === "task.picked")?.t ?? 0;
  const found: Scene[] = [];
  for (const s of SCENES) {
    const from = Math.max(brief, (s.after && found.find((f) => f.id === s.after)?.start) || 0);
    const m = timeline.find((x) => x.t >= from && s.starts(x));
    if (m) found.push({ id: s.id, title: s.title, intro: s.intro, start: m.t });
  }
  return found.sort((a, b) => a.start - b.start);
}

/** The scene playing at time t. */
export function sceneAt(scenes: Scene[], t: number): number {
  let i = 0;
  for (let j = 0; j < scenes.length; j++) if (scenes[j].start <= t + 0.01) i = j;
  return i;
}

/** The scene's key moment: its first event with words, for the caption's second line and its why. */
function keyEvent(events: LabEvent[], from: number, to: number): LabEvent | undefined {
  // Whispers never speak in a caption: before the verdict they are private, and after it the panel room has them.
  const inScene = events.filter((e) => e.t >= from && e.t < to && e.k !== "sponsor.call" && e.k !== "meter.update" && e.k !== "panel.whisper");
  return inScene.find((e) => e.text && e.k !== "learner.query") ?? inScene.find((e) => e.why);
}

/** One caption, in one place: which scene, what is happening, and why. */
export function StoryCaption({ scenes, index, events, onBack, onNext }: { scenes: Scene[]; index: number; events: LabEvent[]; onBack: () => void; onNext: () => void }) {
  const s = scenes[index];
  if (!s) return null;
  const end = scenes[index + 1]?.start ?? Infinity;
  // The story ends on how far to trust the examiners: their benchmark score.
  const last = index === scenes.length - 1;
  const key = keyEvent(events, s.start, end);
  // After the verdict, Telem brings a real case of the same mistake.
  const verdictAt = events.find((e) => e.k === "verdict")?.t;
  const realCase =
    (s.id === "verdict" || s.id === "case" || s.id === "next") && verdictAt !== undefined
      ? caseEvent(events, Math.max(s.start, verdictAt), end)
      : undefined;
  return (
    <div className={`tour box${realCase || last ? " verdict" : ""}`} role="region" aria-label="The story so far" aria-live="polite">
      <span className="count">
        Scene {index + 1} of {scenes.length}
      </span>
      <h2>{s.title}</h2>
      <p>{s.intro}</p>
      {key && (
        <p style={{ marginTop: 6 }}>
          {key.text && key.k !== "learner.query" ? <span style={{ color: "var(--snow)" }}>{plainLine(key)} </span> : null}
          {!/\d\.\d|meter|bandit/i.test(key.why) && <span className="why">Why: {key.why}</span>}
        </p>
      )}
      {realCase && (
        <div style={{ marginTop: 8 }}>
          <p>
            <span style={{ color: "var(--snow)" }}>Telem brings a real case of this mistake.</span>
          </p>
          {isCase(realCase) ? (
            <Safe name="The case card">
              <CaseCard event={realCase} />
            </Safe>
          ) : (
            <p className="why">{plainNumbers(realCase.text ?? "")}</p>
          )}
        </div>
      )}
      {last && (
        <section className="section">
          <h3>How good are the examiners?</h3>
          <Safe name="The benchmark card">
            <BenchCard />
          </Safe>
        </section>
      )}
      <div className="row">
        <button className="btn" onClick={onBack} disabled={index === 0}>
          Back
        </button>
        <button className="btn gold" onClick={onNext} disabled={index >= scenes.length - 1}>
          Next
        </button>
      </div>
    </div>
  );
}
