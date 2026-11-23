import type { LabEvent } from "../api/types";
import { MasteryChart, PanelRoom } from "../panels";
import { plainNumbers } from "../sim/replay";
import { Safe } from "./Safe";

// Judge mode's debrief, one card at a time, centered: (1) the verdict card, then these two:
// (2) how the panel decided, (3) your mastery and Telem's real case.

type Props = { step: 1 | 2; events: LabEvent[]; onBack: () => void; onNext: () => void; onDone: () => void };

export function Debrief({ step, events, onBack, onNext, onDone }: Props) {
  if (step === 1) {
    return (
      <div className="tour box verdict" role="dialog" aria-label="How the panel decided">
        <span className="count">Debrief 2 of 3</span>
        <h2>How the panel decided</h2>
        <p>Dr. Vale, Sam and Ines talked it over in private before ruling. Here is what they said.</p>
        <div style={{ marginTop: 12 }}>
          <Safe name="The panel room">
            <PanelRoom />
          </Safe>
        </div>
        <div className="row">
          <button className="btn" onClick={onBack}>
            Back
          </button>
          <button className="btn gold" onClick={onNext} autoFocus>
            Next
          </button>
        </div>
      </div>
    );
  }
  // Telem's real case of the same mistake comes after the verdict.
  const verdictAt = events.find((e) => e.k === "verdict")?.t ?? Infinity;
  const after = events.filter((e) => e.agent === "telem" && e.t >= verdictAt && e.text);
  const realCase = after.find((e) => e.k === "agent.say") ?? after.find((e) => e.k === "search");
  return (
    <div className="tour box verdict" role="dialog" aria-label="What's next">
      <span className="count">Debrief 3 of 3</span>
      <h2>What's next</h2>
      <p>Your skill on each kind of trap, after this task. The next task aims at what you have not mastered yet.</p>
      <section className="section">
        <h3>Your mastery</h3>
        <Safe name="The mastery chart">
          <MasteryChart compact />
        </Safe>
      </section>
      {realCase && (
        <section className="section">
          <h3>Telem brings a real case of this mistake</h3>
          <div className="quote">{plainNumbers(realCase.text ?? "")}</div>
        </section>
      )}
      <div className="row">
        <button className="btn" onClick={onBack}>
          Back
        </button>
        <button className="btn gold" onClick={onDone} autoFocus>
          Explore the lab
        </button>
      </div>
    </div>
  );
}
