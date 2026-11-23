import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { demo as demoPlayer, getAgents, startDemo, stopDemo, subscribeEvents, subscribeJump, useDemo, useRotation, type LabEvent } from "./api/client";
import { SampleBadge } from "./api/SampleBadge";
import { MasteryChart, MuteButton, PanelRoom, SponsorStrip, Voice } from "./panels";
import type { Run } from "./data/types";
import { Replay } from "./sim/replay";
import { rotationRun } from "./sim/rotation";
import { Chat, type Msg } from "./ui/Chat";
import { Landing } from "./ui/Landing";
import { LabLog } from "./ui/LabLog";
import { FixturePanel, PersonPanel, RoomPanel, RotationPersonPanel, StudyPanel } from "./ui/Panels";
import { TaskChips } from "./ui/TaskChips";
import { Safe } from "./ui/Safe";
import { buildScenes, sceneAt, StoryCaption } from "./ui/Story";
import { VerdictCard, verdictFromEvents } from "./ui/Verdict";
import { Timeline } from "./ui/Timeline";
import { WorkspaceTab } from "./ui/WorkspaceTab";
import { buildRotationTour } from "./ui/tour";
import { LabEngine, type Target } from "./world/engine";

type View = "landing" | "leaving" | "lab";

/** The run picker's values: your own rotation, and the demo (a recorded rotation). */
const ROTATION = "rotation";
const DEMO = "demo";

export function App() {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("landing");
  // The demo replays a recorded session through the same rotation state; it gets its own floor.
  const demoState = useDemo();
  const demoOn = demoState.status !== "off";
  const demoRef = useRef(demoState);
  demoRef.current = demoState;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const replay = useMemo(() => (run ? new Replay(run) : null), [run, demoOn]);
  const rotation = useRotation(); // the one shared session, clock and event poll
  const rotationEvents = useRef<LabEvent[]>([]);
  rotationEvents.current = rotation.events;
  const isRotation = run?.run === ROTATION;
  const [demoEnded, setDemoEnded] = useState(false); // the demo reached its end and holds there
  const [demoHeld, setDemoHeld] = useState(false); // the visitor left the end card: stop looping
  // The verdict card opens when a task's verdict arrives, until you close it.
  const [closedVerdicts, setClosedVerdicts] = useState<string[]>([]);
  const verdictTask = [...rotation.events].reverse().find((e) => e.k === "verdict" && e.task)?.task ?? null;
  // In the demo it waits for the end of the recording, the way the old clip ended on its results.
  // After the last task: every task has its result, or the session says it ended.
  const sessionOver =
    rotation.events.some((e) => e.k === "session.end") || (rotation.tasks.length > 0 && rotation.tasks.every((x) => rotation.results[x.id]));
  const [resultsHeld, setResultsHeld] = useState(false); // the visitor left the results card
  const resultsShown = isRotation && sessionOver && !resultsHeld && (demoOn ? demoEnded && !demoHeld : !!verdictTask && closedVerdicts.includes(verdictTask));
  const verdictShown = demoOn ? demoEnded && !demoHeld && !sessionOver : !!verdictTask && !closedVerdicts.includes(verdictTask);
  const verdictCard = isRotation && verdictTask && verdictShown ? verdictFromEvents(rotation.events, verdictTask) : null;
  const verdictTitle = (() => {
    const i = rotation.tasks.findIndex((x) => x.id === verdictTask);
    return i >= 0 ? `Task ${i + 1}` : rotation.tasks.find((x) => x.id === verdictTask)?.title ?? "Your task";
  })();

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const engineRef = useRef<LabEngine | null>(null);
  const tRef = useRef(0);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [liveOn, setLiveOn] = useState(false);
  const [followOn, setFollowOn] = useState(true); // the camera glides to where things happen
  const followRef = useRef(followOn);
  followRef.current = followOn;
  const [speed, setSpeed] = useState(12);
  const [selected, setSelected] = useState<Target | null>(null);
  const [panel, setPanel] = useState<"workspace" | "details" | "chat" | "room" | null>(null);
  const [taskRunning, setTaskRunning] = useState(false); // the workspace has a task open: widen the panel
  const [filter, setFilter] = useState<string | null>(null);
  const [chatAgent, setChatAgent] = useState("guide");
  const [chats, setChats] = useState<Record<string, Msg[]>>({});
  const [tour, setTour] = useState<number | null>(null);
  const [welcome, setWelcome] = useState(false);
  const tourList = useMemo(() => (replay ? buildRotationTour(replay) : []), [replay]);
  const lo = 0;
  const hi = replay?.end ?? 0;

  // ---- Loading ----------------------------------------------------------------------------------
  // The floor holds the people the backend lists, matched by their ids.
  useEffect(() => {
    let stop = false;
    getAgents()
      .then((agents) => !stop && setRun(rotationRun(agents)))
      .catch((e) => !stop && setError(`Could not load the lab's people: ${(e as Error).message}`));
    return () => {
      stop = true;
    };
  }, []);

  // ---- The engine -------------------------------------------------------------------------------
  useEffect(() => {
    if (!replay || !canvasRef.current) return;
    const engine = new LabEngine(canvasRef.current, replay, {
      onTick: (time, p) => {
        tRef.current = time;
        setT(time);
        setPlaying(p);
        setLiveOn(!!engineRef.current?.live);
      },
      onSelect: (target) => {
        if (!target) {
          setSelected(null);
          setPanel((p) => (p === "details" ? null : p));
          return;
        }
        setSelected(target);
        setPanel("details");
      },
      onHover: () => {},
    });
    engine.setSpeed(speed);
    engineRef.current = engine;
    engine.followAction = followRef.current;
    if (replay.run.run === ROTATION) {
      // Frame the rooms in use; the closed ones stay out of view until you zoom out.
      engine.setFrame(["director", "library", "team-a", "team-b", "referee", "vault"]);
      engine.fit(false);
      // Your rotation: take in everything so far and follow it live. The demo follows its own clock.
      const d = demoRef.current;
      if (d.status === "ready") replay.setRecording(d.timeline, d.end);
      engine.addLive(rotationEvents.current);
      if (d.status !== "off") {
        engine.seek(d.position);
        engine.followClock(d.position, d.speed, d.playing);
      } else engine.goLive();
    }
    if (import.meta.env.DEV) (window as unknown as { __lab: LabEngine }).__lab = engine;
    engine.interactive = view === "lab";
    return () => engine.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replay]);

  // The rotation's events reach the floor as they arrive; each plays, with the animations the
  // floor already has, when the floor's clock reaches it.
  useEffect(() => subscribeEvents((events) => engineRef.current?.addLive(events)), []);
  // A demo seek or loop: the floor starts over from everything up to that moment.
  useEffect(() => subscribeJump((time, events) => engineRef.current?.jumpTo(time, events)), []);

  // The demo's whole recording marks the timeline, and the floor follows the demo's clock.
  useEffect(() => {
    if (demoState.status === "ready" && replay) replay.setRecording(demoState.timeline, demoState.end);
  }, [replay, demoState.status, demoState.timeline, demoState.end]);
  useEffect(() => {
    if (demoState.status === "ready") engineRef.current?.followClock(demoState.position, demoState.speed, demoState.playing);
  }, [replay, demoState.status, demoState.position, demoState.speed, demoState.playing]);

  // At the end of the demo, hold on the verdict card, then play it again, the way the old clip did.
  useEffect(() => {
    if (demoState.status !== "ready") return setDemoEnded(false);
    // Stop one player tick (0.2 s of real time) before the end, before the player loops by itself.
    const near = demoState.end - Math.max(1, demoState.speed * 0.3);
    if (demoState.playing && demoState.position >= near) {
      demoPlayer.pause();
      setDemoEnded(true);
    } else if (demoState.position < near) setDemoEnded(false);
  }, [demoState.status, demoState.playing, demoState.position, demoState.end]);
  // ---- The demo as a guided story ----------------------------------------------------------------
  // One scene at a time, one caption at a time. Each caption stays at least 5 s: the story speeds
  // through quiet stretches, slows near the next scene, and waits there until the caption has had its time.
  const [story, setStory] = useState(false);
  const scenes = useMemo(() => buildScenes(demoState.timeline), [demoState.timeline]);
  const sceneIdx = sceneAt(scenes, demoState.position);
  const sceneShownAt = useRef(Date.now());
  useEffect(() => {
    sceneShownAt.current = Date.now();
  }, [sceneIdx]);
  const storyWait = useRef(0);
  useEffect(() => {
    if (!story || demoState.status !== "ready" || !demoState.playing) return;
    const cur = scenes[sceneIdx];
    const next = scenes[sceneIdx + 1];
    if (!cur) return;
    const shown = Date.now() - sceneShownAt.current;
    if (next && demoState.position + Math.max(0.3, demoState.speed * 0.3) >= next.start && shown < 5000) {
      demoPlayer.pause();
      window.clearTimeout(storyWait.current);
      storyWait.current = window.setTimeout(() => demoPlayer.play(), 5000 - shown);
      return;
    }
    const want = demoState.position - cur.start < 6 || (next && next.start - demoState.position < 3) ? 1 : 6;
    if (demoState.speed !== want) demoPlayer.setSpeed(want);
  }, [story, scenes, sceneIdx, demoState.status, demoState.playing, demoState.position, demoState.speed]);
  useEffect(() => () => window.clearTimeout(storyWait.current), []);
  const goScene = (i: number) => {
    const s = scenes[i];
    if (!s) return;
    window.clearTimeout(storyWait.current);
    setDemoEnded(false);
    setDemoHeld(false);
    demoPlayer.seek(Math.max(demoState.start, s.start)); // the scene's own first moment
    demoPlayer.play();
  };
  const startStory = () => {
    setStory(true);
    setWelcome(false);
    setSelected(null);
    setPanel(null);
    startDemo();
  };
  const leaveDemo = () => {
    setStory(false);
    window.clearTimeout(storyWait.current);
    stopDemo();
  };
  useEffect(() => {
    if (engineRef.current) engineRef.current.oneAtATime = demoOn;
  }, [demoOn, replay]);

  const watchAgain = () => {
    setDemoHeld(false);
    setDemoEnded(false);
    demoPlayer.seek(demoRef.current.start);
    demoPlayer.play();
  };
  useEffect(() => {
    if (!demoEnded || demoHeld || panel || view !== "lab") return;
    const timer = window.setTimeout(watchAgain, 12000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demoEnded, demoHeld, panel, view]);

  useEffect(() => {
    const e = engineRef.current;
    if (!e) return;
    e.setSelected(selected);
  }, [selected]);

  useEffect(() => {
    engineRef.current?.setFilter(filter);
  }, [filter]);

  const engine = () => engineRef.current;

  // ---- Actions ------------------------------------------------------------------------------------
  const select = useCallback((target: Target, focus = true) => {
    if (target.type === "study") {
      setFilter(target.id);
    }
    setSelected(target);
    setPanel("details");
    if (focus && target.type !== "study") engine()?.focus(target);
  }, []);

  const talk = useCallback((agent: string) => {
    setChatAgent(agent);
    setPanel("chat");
  }, []);

  const chooseStudy = (id: string | null) => {
    setFilter(id);
    if (id) {
      setSelected({ type: "study", id });
      setPanel("details");
    } else if (selected?.type === "study") {
      setSelected(null);
      setPanel(null);
    }
  };

  const enter = (asStory = false) => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setView("leaving");
    const e = engine();
    if (e) {
      e.interactive = true;
      const z = e.fitZoom();
      e.setCamera(52 * 16, 9 * 16, z * 3.2);
      e.focus(null);
    }
    window.setTimeout(() => {
      setView("lab");
      setWelcome(!asStory); // the story starts straight away, with no welcome box
      const en = engine();
      if (en && !en.playing && en.t < (replay?.end ?? 0) - 1) en.setPlaying(true);
    }, reduced ? 0 : 1050);
  };

  const goTour = (i: number | null) => {
    const e = engine();
    setWelcome(false);
    setTour(i);
    if (e) e.followAction = i === null && followOn; // the camera holds still during the tour
    if (i === null || !e) return;
    // The tour looks at people and places; it leaves the clock alone.
    const s = tourList[i];
    if (!s) return;
    e.focus(s.focus);
    if (s.workspace) {
      setSelected(null);
      setPanel("workspace");
    } else if (s.select) {
      setSelected(s.select);
      setPanel("details");
    } else {
      setSelected(null);
      setPanel(null);
    }
  };

  const nextMoment = (dir: 1 | -1) => {
    const e = engine();
    if (!e || !replay) return;
    if (demoOn) {
      const cur = e.t;
      const list = replay.moments;
      const m = dir === 1 ? list.find((x) => x.t > cur + 1) : [...list].reverse().find((x) => x.t < cur - 3);
      if (!m) return;
      setDemoEnded(false);
      demoPlayer.seek(Math.max(demoState.start, m.t - 4));
      demoPlayer.play();
      return;
    }
    const list = replay.moments.filter((m) => (!filter || !m.study || m.study === filter) && m.t >= lo && m.t <= hi);
    const cur = e.t;
    const m = dir === 1 ? list.find((x) => x.t > cur + 1) : [...list].reverse().find((x) => x.t < cur - 3);
    if (!m) return;
    e.seek(Math.max(lo, m.t - 4));
    e.setPlaying(true);
  };


  // Keyboard: space plays, arrows step between moments, escape closes.
  useEffect(() => {
    if (view !== "lab") return;
    const onKey = (ev: KeyboardEvent) => {
      const tag = (ev.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (ev.target as HTMLElement)?.getAttribute("role") === "slider") return;
      const e = engine();
      if (!e) return;
      if (ev.key === " ") {
        ev.preventDefault();
        if (demoOn) demoPlayer.toggle();
        else e.setPlaying(!e.playing);
      } else if (ev.key === "ArrowRight") nextMoment(1);
      else if (ev.key === "ArrowLeft") nextMoment(-1);
      else if (ev.key === "Escape") {
        if (tour !== null) setTour(null);
        else {
          setPanel(null);
          setSelected(null);
        }
      } else if (ev.key === "+" || ev.key === "=") e.zoomBy(1.25);
      else if (ev.key === "-") e.zoomBy(0.8);
      else if (ev.key === "0") e.showWhole();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (error) {
    return (
      <div style={{ padding: 40 }}>
        <h1 className="wordmark" style={{ fontSize: 48 }}>
          Lab Rotation
        </h1>
        <p>{error}</p>
      </div>
    );
  }

  const R = replay;
  const status = !run ? "Loading the lab…" : rotation.current ? `Your rotation: ${rotation.current.title} is waiting` : "Your rotation is ready";

  const chatPeople = R
    ? Array.from(
        new Set(
          [
            "director",
            selected?.type === "agent" ? selected.id : "",
            ...(filter ? R.run.agents.filter((a) => a.study === filter && a.role !== "solo").map((a) => a.id) : []),
            ...Object.keys(chats),
            chatAgent,
          ].filter((id) => id && id !== "guide" && R.agents.has(id)),
        ),
      )
    : [];

  const nav = R ? { R, t, select, talk, filter: chooseStudy, live: rotation.events } : null;

  return (
    <>
      <div className={`lab${isRotation ? " with-strip" : ""}`} inert={view !== "lab" ? true : undefined}>
        <canvas ref={canvasRef} className="floor" aria-label="The lab floor. Click a person to see what they are working on." />
        {R && view !== "landing" && (
          <>
            <header className="topbar">
              <button className="brand" onClick={() => location.reload()} title="Back to the start">
                <b>Lab Rotation</b>
              </button>
              <label className="sr-only" htmlFor="run">
                Run
              </label>
              <select
                id="run"
                className="run-pick"
                value={demoOn ? DEMO : ROTATION}
                onChange={(e) => {
                  tRef.current = 0;
                  setSelected(null);
                  setPanel(null);
                  setTour(null);
                  if (e.target.value === DEMO) startStory();
                  else leaveDemo();
                }}
              >
                <option value={ROTATION}>Your rotation</option>
                <option value={DEMO}>Demo</option>
              </select>
              {isRotation ? (
                <TaskChips rotation={rotation} onOpen={() => setPanel("workspace")} />
              ) : (
                <nav className="chips" aria-label="Studies">
                  <button className="chip" aria-pressed={filter === null} onClick={() => chooseStudy(null)}>
                    All studies
                  </button>
                  {R.run.studies.map((s) => {
                    const fin = R.finalEvent(s.id, t);
                    const working = R.run.agents.some((a) => a.study === s.id && a.role !== "solo" && R.status(a.id, t).working);
                    const graded = R.graded(t) && s.grade;
                    return (
                      <button key={s.id} className="chip" aria-pressed={filter === s.id} onClick={() => chooseStudy(filter === s.id ? null : s.id)} title={s.title}>
                        <span className={`dot ${working ? "working" : fin ? "done" : ""}`} title={working ? "Agents working" : fin ? "Finished" : "Waiting"} />
                        {s.id}
                        {graded && <span className={`mark ${s.grade!.lab ? "pass" : "fail"}`}>{s.grade!.lab ? "passed" : "failed"}</span>}
                      </button>
                    );
                  })}
                </nav>
              )}
              {isRotation && (
                <button
                  className="btn quiet hide-sm"
                  aria-pressed={demoOn}
                  onClick={() => (demoOn ? leaveDemo() : startStory())}
                  title={demoOn ? "Leave the demo and go back to your rotation" : "Watch a recorded rotation from start to verdict"}
                >
                  {demoOn ? "Your rotation" : "Demo"}
                </button>
              )}
              <button className="btn quiet hide-sm" onClick={() => goTour(0)}>
                Tour
              </button>
              {isRotation && (
                <Safe name="The mute button">
                  <MuteButton />
                </Safe>
              )}
              <button className="btn quiet hide-sm" aria-pressed={panel === "workspace"} onClick={() => setPanel(panel === "workspace" ? null : "workspace")}>
                Workspace
              </button>
              <button className="btn gold" onClick={() => talk(chatAgent)}>
                Ask the lab
              </button>
            </header>

            {panel && nav && (
              <aside
                className={`side box${taskRunning && panel === "workspace" ? " wide" : ""}`}
                aria-label={{ workspace: "Workspace", details: "Details", chat: "Ask the lab", room: "Panel room" }[panel]}
              >
                <div className="side-head">
                  <div className="tabs" role="tablist">
                    <button className="tab" role="tab" aria-selected={panel === "workspace"} onClick={() => setPanel("workspace")}>
                      Workspace
                    </button>
                    {selected && (
                      <button className="tab" role="tab" aria-selected={panel === "details"} onClick={() => setPanel("details")}>
                        Details
                      </button>
                    )}
                    <button className="tab" role="tab" aria-selected={panel === "chat"} onClick={() => setPanel("chat")}>
                      Ask
                    </button>
                    <button className="tab" role="tab" aria-selected={panel === "room"} onClick={() => setPanel("room")}>
                      Panel room
                    </button>
                  </div>
                  <button className="btn quiet icon" onClick={() => setPanel(null)} aria-label="Close panel" title="Close (Esc)">
                    <svg width="12" height="12" viewBox="0 0 6 6" shapeRendering="crispEdges" aria-hidden="true">
                      <path d="M0 0h1v1H0zM1 1h1v1H1zM2 2h2v2H2zM4 1h1v1H4zM5 0h1v1H5zM1 4h1v1H1zM0 5h1v1H0zM4 4h1v1H4zM5 5h1v1H5z" fill="currentColor" />
                    </svg>
                  </button>
                </div>
                {/* Stays mounted while the panel is open, so switching tabs never loses a task in progress. */}
                <div className="ws-slot" hidden={panel !== "workspace"}>
                  <WorkspaceTab onTaskChange={setTaskRunning} />
                </div>
                {panel === "workspace" ? null : panel === "room" ? (
                  <div className="side-body">
                    <Safe name="The panel room">
                      <PanelRoom />
                    </Safe>
                  </div>
                ) : panel === "chat" ? (
                  <Chat R={R} t={t} server={false} agent={chatAgent} setAgent={setChatAgent} people={chatPeople} chats={chats} setChats={setChats} select={(x) => select(x)} />
                ) : (
                  <div className="side-body">
                    {selected?.type === "agent" && (isRotation ? <RotationPersonPanel id={selected.id} {...nav} /> : <PersonPanel id={selected.id} {...nav} />)}
                    {selected?.type === "study" && <StudyPanel id={selected.id} {...nav} />}
                    {selected?.type === "room" && <RoomPanel id={selected.id} {...nav} />}
                    {selected?.type === "fixture" && <FixturePanel id={selected.id} {...nav} />}
                  </div>
                )}
              </aside>
            )}

            <div className="mapctl">
              {isRotation && (
                <button
                  className="btn"
                  aria-pressed={followOn}
                  onClick={() => {
                    const on = !followOn;
                    setFollowOn(on);
                    if (engine()) engine()!.followAction = on;
                  }}
                  title={followOn ? "The camera follows the action. Click to keep it still." : "The camera stays where you put it. Click to follow the action."}
                >
                  <span className={`dot ${followOn ? "working" : ""}`} aria-hidden="true" />
                  Follow
                </button>
              )}
              <button className="btn icon" onClick={() => engine()?.zoomBy(1.3)} aria-label="Zoom in" title="Zoom in (+)">
                +
              </button>
              <button className="btn icon" onClick={() => engine()?.zoomBy(1 / 1.3)} aria-label="Zoom out" title="Zoom out (-)">
                −
              </button>
              <button className="btn icon" onClick={() => engine()?.showWhole()} aria-label="Show the whole lab" title="Whole lab (0)">
                <svg width="14" height="14" viewBox="0 0 7 7" shapeRendering="crispEdges" aria-hidden="true">
                  <path d="M0 0h3v1H1v2H0zM4 0h3v3H6V1H4zM0 4h1v2h2v1H0zM6 4h1v3H4V6h2z" fill="currentColor" />
                </svg>
              </button>
            </div>

            {story && demoOn && (
              <button className="btn story-exit" onClick={() => setStory(false)} title="Leave the story and look around the lab yourself">
                Explore the lab
              </button>
            )}

            {story && demoOn && !demoEnded && tour === null && (
              <StoryCaption scenes={scenes} index={sceneIdx} events={rotation.events} onBack={() => goScene(sceneIdx - 1)} onNext={() => goScene(sceneIdx + 1)} />
            )}

            {tour === null && !welcome && !(story && demoOn) && <LabLog R={R} t={t} filter={filter} select={(x) => select(x)} live={rotation.events} />}

            {welcome && tour === null && (
              <div className="tour box" role="dialog" aria-label="Welcome">
                <h2>Welcome to the lab floor</h2>
                <p>
                  {demoOn
                    ? "You're watching a recorded rotation, from the first task to the verdict. Everyone here is an AI agent; you are the student in Team A. Click anyone to see what they did and why."
                    : "This is your rotation. Dr. Vale will bring you a task; open the Workspace to dig into the data. Telem, Sam, Riley and Ines are all at work around you. Click anyone to see what they're doing and why."}
                </p>
                <div className="row">
                  <button className="btn" onClick={() => setWelcome(false)}>
                    Explore on my own
                  </button>
                  {isRotation && (
                    <button className="btn" onClick={() => goTour(0)}>
                      Take the tour
                    </button>
                  )}
                  {isRotation ? (
                    <button
                      className="btn gold"
                      onClick={() => {
                        setWelcome(false);
                        setPanel("workspace");
                      }}
                      autoFocus
                    >
                      Open the Workspace
                    </button>
                  ) : (
                    <button className="btn gold" onClick={() => goTour(0)} autoFocus>
                      Take the 1-minute tour
                    </button>
                  )}
                </div>
              </div>
            )}

            {tour !== null && tourList[tour] && (
              <div className="tour box" role="dialog" aria-label="Tour">
                <span className="count">
                  {tour + 1} of {tourList.length}
                </span>
                <h2>{tourList[tour].title}</h2>
                <p>{tourList[tour].text}</p>
                <div className="row">
                  <button className="btn quiet" onClick={() => goTour(null)}>
                    End tour
                  </button>
                  {tour > 0 && (
                    <button className="btn" onClick={() => goTour(tour - 1)}>
                      Back
                    </button>
                  )}
                  {tour < tourList.length - 1 ? (
                    <button className="btn gold" onClick={() => goTour(tour + 1)} autoFocus>
                      Next
                    </button>
                  ) : (
                    <button className="btn gold" onClick={() => goTour(null)} autoFocus>
                      Explore the lab
                    </button>
                  )}
                </div>
              </div>
            )}

            {verdictCard && verdictTask && tour === null && !welcome && (
              <Safe name="The verdict card">
                <VerdictCard
                  taskTitle={verdictTitle}
                  {...verdictCard}
                  onClose={() => (demoOn ? setDemoHeld(true) : setClosedVerdicts((c) => [...c, verdictTask]))}
                  onPanelRoom={() => {
                    if (demoOn) setDemoHeld(true);
                    else setClosedVerdicts((c) => [...c, verdictTask]);
                    setPanel("room");
                  }}
                  onAgain={demoOn ? watchAgain : undefined}
                />
              </Safe>
            )}

            {resultsShown && tour === null && !welcome && (
              <div className="tour box" role="dialog" aria-label="Results">
                <span className="count">Results</span>
                <h2>
                  You passed {rotation.tasks.filter((x) => rotation.results[x.id] === "passed").length} of {rotation.tasks.length} tasks
                </h2>
                <p>Ines checked every answer with the Bruin checks, and each verdict is sealed. Here is how your skill on each trap stands now.</p>
                <div className="chips" style={{ marginTop: 12, flexWrap: "wrap" }}>
                  {rotation.tasks.map((x, i) => (
                    <span key={x.id} className="chip" title={x.title}>
                      Task {i + 1}
                      {rotation.results[x.id] && (
                        <span className={`mark ${rotation.results[x.id] === "passed" ? "pass" : "fail"}`}>{rotation.results[x.id]}</span>
                      )}
                    </span>
                  ))}
                </div>
                <div style={{ marginTop: 12 }}>
                  <Safe name="The mastery chart">
                    <MasteryChart compact />
                  </Safe>
                </div>
                <div className="row">
                  <button
                    className="btn"
                    onClick={() => {
                      if (demoOn) setDemoHeld(true);
                      else setResultsHeld(true);
                    }}
                  >
                    Explore the lab
                  </button>
                  <button
                    className="btn gold"
                    onClick={() => {
                      if (demoOn) return watchAgain();
                      // Your own session, from the start, at 4x.
                      setResultsHeld(true);
                      const e = engine();
                      if (!e) return;
                      e.seek(0);
                      e.setSpeed(4);
                      setSpeed(4);
                      e.setPlaying(true);
                    }}
                    autoFocus
                  >
                    Watch again
                  </button>
                </div>
              </div>
            )}

            {isRotation && (
              <div className="strip-slot">
                <Safe name="The sponsor strip">
                  <SponsorStrip />
                </Safe>
              </div>
            )}

            <Timeline
              R={R}
              t={t}
              playing={demoOn ? demoState.playing : playing}
              speed={demoOn ? demoState.speed : speed}
              filter={filter}
              lo={demoOn ? demoState.start : lo}
              hi={demoOn ? demoState.end : hi}
              onPlay={() => {
                if (demoOn) {
                  if (demoEnded) watchAgain();
                  else demoPlayer.toggle();
                } else engine()?.setPlaying(!engine()!.playing);
              }}
              onSeek={(x) => {
                if (demoOn) {
                  setDemoEnded(false);
                  demoPlayer.seek(x);
                } else engine()?.seek(x);
              }}
              onSpeed={(s) => {
                if (demoOn) return demoPlayer.setSpeed(s);
                setSpeed(s);
                engine()?.setSpeed(s);
              }}
              onNext={nextMoment}
              live={isRotation && !demoOn ? { on: liveOn, go: () => engine()?.goLive() } : undefined}
              session={isRotation}
            />
          </>
        )}
      </div>
      <SampleBadge />
      <Safe name="Voice lines">
        <Voice />
      </Safe>
      {view !== "lab" && (
        <Landing
          onEnter={enter}
          onDemo={() => {
            startStory();
            enter(true);
          }}
          ready={!!replay}
          status={status}
          live={false}
          leaving={view === "leaving"}
        />
      )}
    </>
  );
}
