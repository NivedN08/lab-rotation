// A fake session that plays one full task, served through getEvents like the real server will.
// Add ?mockspeed=10 to the URL to play it ten times faster while testing.

import raw from "./mock/mock_session.jsonl?raw";
import taskJson from "./mock/task.json";
import type { EventsPage, LabEvent } from "./types";

type Step = LabEvent;

// The contract's own mock session (contract/mock_session.jsonl, copied into ./mock/), so sample data has the real format.
// `upgrade` brings it up to the contract's latest announced shape where the copied file is older. Each step does
// nothing once the file already has the change, so syncing a newer contract file is safe.
const rawEvents = raw
  .split("\n")
  .filter((l) => l.trim())
  .map((l) => JSON.parse(l) as LabEvent);

function upgrade(events: LabEvent[]): LabEvent[] {
  const list: (LabEvent & { orig?: number })[] = events.map((e) => ({ ...e, orig: e.seq }));
  const verdict = list.find((e) => e.k === "verdict");
  const taskId = (verdict?.data as { taskId?: string } | undefined)?.taskId;

  // task.picked carries the data dictionary, the same as GET /task.
  const picked = list.find((e) => e.k === "task.picked");
  if (picked?.data && !("dictionary" in picked.data)) picked.data = { ...picked.data, dictionary: (taskJson as { dictionary?: string }).dictionary };

  // Whisper words move out of panel.whisper into a panel.transcript sent right after the verdict.
  if (verdict && !list.some((e) => e.k === "panel.transcript")) {
    const whispers = list
      .filter((e) => e.k === "panel.whisper" && (e.data as { text?: string } | undefined)?.text)
      .map((e) => ({ seq: e.orig as number, agent: e.agent, to: e.to, text: (e.data as { text: string }).text }));
    for (const e of list) {
      if (e.k === "panel.whisper" && e.data) {
        const { text: _t, ...rest } = e.data as Record<string, unknown>;
        e.data = rest;
      }
    }
    list.push({
      seq: 0,
      t: verdict.t + 0.1,
      k: "panel.transcript",
      agent: "system",
      why: "the verdict is in, so the panel's private messages can be shown",
      task: taskId,
      data: { whispers },
    });
  }

  // Telem's real-world case comes after the verdict. Before the answer he only talks about the topic.
  if (verdict && !list.some((e) => e.k === "search" && e.t > verdict.t)) {
    const early = list.find((e) => e.k === "search" && e.t < verdict.t);
    const earlyCall = list.find((e) => e.k === "sponsor.call" && (e.data as { sponsor?: string; op?: string }).sponsor === "telem" && (e.data as { op?: string }).op === "search");
    const earlySay = list.find((e) => e.k === "agent.say" && e.agent === "telem" && e.t < verdict.t);
    if (early && earlySay) {
      const realCase = { ...(early.data as Record<string, unknown>) };
      const caseText = earlySay.text;
      // Before the answer: background on the topic, no case, nothing that points at a trap.
      early.text = "Telem looked up how spend per visit is usually compared.";
      early.why = "background on the topic helps the learner frame the task, without pointing at a trap";
      early.data = {
        query: "how average spend per visit is compared between customer groups",
        cached: false,
        trace: (realCase.trace as string) ?? "https://app.telem.ai/traces/mock-1",
        results: [{ title: "Background: comparing average spend across customer groups", url: "https://example.com/mock-topic-spend", snippet: "Retail teams usually compare spend per visit as an average for each group..." }],
      };
      if (earlyCall) {
        earlyCall.why = "the librarian looks up background on the topic with Telem AI";
        earlyCall.data = { ...(earlyCall.data as object), label: "searched for background on the topic" };
      }
      earlySay.why = "share some background on the topic, with its source, and nothing about what might be wrong";
      earlySay.text = "Some background for you: comparisons like this usually average spend per visit for each customer group. The source and trace are on the card.";
      for (const e of list) if (e.k === "agent.move" && e.agent === "telem" && e.t < verdict.t && /real case/i.test(e.why)) e.why = "look up background on the topic of this claim";
      const voiceOfEarly = list.find((e) => e.k === "voice.line" && e.agent === "telem" && e.t < verdict.t);
      if (voiceOfEarly) voiceOfEarly.why = "speak the background in the agent's own voice";

      // After the verdict: a second search finds the real case, and Telem brings it over.
      const V = verdict.t;
      const trace2 = "https://app.telem.ai/traces/mock-2";
      list.push({ seq: 0, t: V + 1.8, k: "agent.move", agent: "telem", to: "learner", task: taskId, why: "the verdict is in, so Telem can bring a real case", data: { from: "shelves", place: "learner_desk" } });
      list.push({ seq: 0, t: V + 2.5, k: "sponsor.call", agent: "system", why: "the librarian finds real cases with Telem AI", data: { sponsor: "telem", label: "searched for real cases", count: 1, op: "search", by: "telem", ms: 1380, fallback: false, trace: trace2 } });
      list.push({
        seq: 0, t: V + 4, k: "search", agent: "telem", task: taskId,
        why: "now that the learner has an answer, a real case shows what this kind of trap looks like outside the lab",
        text: "Telem found a real case of a unit mix-up in sales data.",
        data: { ...realCase, trace: trace2 },
      });
      list.push({
        seq: 0, t: V + 5, k: "agent.say", agent: "telem", to: "learner", task: taskId, orig: -1,
        why: "share one real case with its source, now that the verdict is in",
        text: caseText?.replace("A real case for you:", "A real case, now that you have your verdict:") ?? "A real case: a chain once restated a region's sales because its export used cents.",
      });
      list.push({ seq: 0, t: V + 5.4, k: "voice.line", agent: "telem", task: taskId, why: "speak the line in the agent's own voice", data: { file: "mock-telem-case.mp3", lineOf: -1, seconds: 8.9, cost: 0.0012, provider: "runware" } });
      list.push({ seq: 0, t: V + 5.4, k: "sponsor.call", agent: "system", why: "every spoken line is a Runware voice", data: { sponsor: "runware", label: "voice line for telem", count: 1, op: "tts", by: "telem", ms: 820, fallback: false, cost: 0.0012 } });
      list.push({ seq: 0, t: V + 13, k: "agent.move", agent: "telem", task: taskId, why: "back to the shelves", data: { from: "learner_desk", place: "shelves" } });
    }
  }

  // A few more walks, so every place on the floor is used: the learner comes in and leaves, the panel breaks up.
  const move = (t: number, agent: LabEvent["agent"], from: string, place: string, why: string, to?: LabEvent["agent"]) =>
    list.push({ seq: 0, t, k: "agent.move", agent, to, task: taskId, why, data: { from, place } });
  if (!list.some((e) => e.k === "agent.move" && e.agent === "learner")) {
    move(0.8, "learner", "door", "learner_desk", "the learner walks in and sits down to start the task");
    move(214, "vale", "panel_table", "vale_office", "the panel is done, so Vale goes back to the office");
    move(214.2, "sam", "panel_table", "whiteboard", "the panel is done, so Sam goes back to the whiteboard");
    move(254, "learner", "learner_desk", "door", "the rotation is over, so the learner leaves");
  }

  // Number the events in time order and keep the references between events pointing at the right ones.
  const sorted = list.map((e, i) => ({ e, i })).sort((x, y) => x.e.t - y.e.t || x.i - y.i).map((x) => x.e);
  const seqOf = new Map<number, number>();
  sorted.forEach((e, i) => {
    e.seq = i + 1;
    if (e.orig !== undefined) seqOf.set(e.orig, e.seq);
  });
  for (const e of sorted) {
    const d = e.data as { lineOf?: number; whispers?: { seq: number }[] } | undefined;
    if (d?.lineOf !== undefined) d.lineOf = seqOf.get(d.lineOf) ?? d.lineOf;
    if (e.k === "panel.transcript" && d?.whispers) for (const w of d.whispers) w.seq = seqOf.get(w.seq) ?? w.seq;
    delete e.orig;
  }
  return sorted;
}

export const SCRIPT: Step[] = upgrade(rawEvents);

/** The whole script as a finished, recorded session: every event, from the beginning. */
export function recordedEvents(): EventsPage {
  const events = SCRIPT;
  return { events, next: events.length };
}
