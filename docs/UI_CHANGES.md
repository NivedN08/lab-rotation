# Lab Rotation UI: what stays, what changes, what's new

**The rule:** The original's look stays. Same pixel floor, engine, sprites, animations, colors (`styles.css` variables) and fonts (Pixelify Sans, Atkinson Hyperlegible). New panels reuse `.box`, `.side`, `.tabs`, `.tour`, `.btn` and `.chip`. Nothing that exists gets restyled or removed.

**How we track it:** before and after each item, take a playwright screenshot of `localhost:5173` into `docs/shots/<item>-before.png` and `-after.png`, tick the box here, and write one line under "Log" at the bottom.

`*` means after 3:30, only if everything above it works.

---

## Keep as is

- Pixel floor, rooms, walls, snow, camera and zoom (`world/staticLayer.ts`, `world/engine.ts`)
- Sprites and walk cycles (`world/people.ts`)
- Animations: walks, speech-bubble icons, envelopes, flying answers, floating text, hatch flash, notes to the vault (`world/engine.ts`)
- Side panel with Details and Ask tabs, and the "answers only from what it could see" rule (`ui/Panels.tsx`, `ui/Chat.tsx`)
- Lab log, bottom left (`ui/LabLog.tsx`)
- Timeline, bottom (`ui/Timeline.tsx`), for replays
- Keyboard keys and the demo clip loop

## Order of work

**Main session** (everything except `web/src/workspace/`)

- [x] 1. Names: the original name becomes "Lab Rotation" on the landing page and top bar (`ui/Landing.tsx`, `App.tsx`)
- [x] 2. Cast: Dr. Vale, Ines, Sam, Telem, Riley and You replace the random names; role labels and "what it can read" lines (`sim/replay.ts`: `NAMES`, `ROLE_LABEL`, `ROLE_READS`)
- [x] 3. Room labels for the new cast (`world/layout.ts`: `ROOMS`)
- [x] 4. Your desk and sprite in Team A; Sam at the head desk at the back of Team A (`world/layout.ts`, `world/people.ts`)
- [x] 5. Riley's desk in Team B, so both answers meet at the hatch (decided: Team B)
- [x] 6. Right-side panel gets tabs Workspace, Details, Ask and Panel room; the Workspace tab mounts `web/src/workspace/index.tsx` and the panel widens while a task runs (`App.tsx`)
- [x] 7. New events play the existing animations (table below) (`world/engine.ts`, lab log lines in `sim/replay.ts`)
- [x] 8. Top bar: study chips become Task 1, 2, 3 with passed or failed marks, plus the task timer (`App.tsx`)
- [x] 9. Verdict card, built from the results card: your verdict against the key, the failing Bruin check next to your evidence, your quoted words, Riley's answer, "sealed" (`App.tsx` or `ui/Verdict.tsx`)
- [x] 10. Sponsor strip: a thin bar above the timeline counting BAND messages, Telem searches (with trace links), Bruin checks run and failed, Runware lines and cost, Glasser calls (`ui/SponsorStrip.tsx`)
- [x] 11. Mastery chart: one bar per trap type; shown in your Details panel and on the verdict card (`ui/Mastery.tsx`, `ui/Panels.tsx`)
- [x] 12. Audio: play each voice line as it appears, with a mute button in the top bar
- [x] 13. Panel room tab in the side panel: the BAND transcript, opened after the verdict
- [ ] 14. Live updates every second instead of every 8 (`App.tsx`), or the event stream if Nived ships it
- [ ] 15.* Appeal view inside the Panel room tab
- [x] 16.* Runware portraits in the Details panel (`ui/Avatar.tsx`)
- [x] 17.* Tour rewritten for a rotation (`ui/tour.ts`); judge mode button on the landing page

**Workspace session** (only `web/src/workspace/`, own `workspace.css`)

- [x] W1. Table browser: tabs per table, rows with a row cap
- [x] W2. SQL box: runs on the server (Nived's runner), shows results and errors
- [x] W3. Evidence picker: click rows, columns or cells to cite them
- [x] W4. Answer form: holds / fails / can't tell, the trap you found, your evidence, submit
- [x] W5. Timer and the empty, loading and error states
- [x] W6.* Column profile (one click per column)
- [x] W7.* Chart builder
- [x] W8.* Voice input (browser speech to text into the answer form)

## Who sits where (same floor, new cast)

| Room | the original | Lab Rotation |
|---|---|---|
| Lobby | Arrivals | You arrive |
| Director's office | Director | Dr. Vale |
| Library | Librarians | Telem |
| Team A | Team A scientists | Your desk; Sam at the head desk at the back |
| Team B | Team B scientists | Riley |
| Hatch (A/B wall) | Compares the two teams' answers | Compares your answer with Riley's |
| Referee | Referee | Ines, and the Bruin terminal (the referee table) |
| Memory vault | Department notes | Your learner profile: mastery updates fly here |
| Team C, Solo agents | Third team, solo baselines | Unused. Decide: leave empty, dim, or label "closed" |

## New events, existing animations

No new animation types are needed. Each new event reuses one that the original already has.

| New event | What you see | Reuses the original's |
|---|---|---|
| `session.start` | You walk in from the lobby to your desk | `agent.start` arrive |
| `task.picked` | Vale walks to your desk carrying a paper | `relay.briefing` (director visit) |
| `search` | Telem: search bubble and shelf flash, then carries a scroll to your desk | `web.search`, the librarian's scroll walk |
| `monitor.hit` | Alert bubble over Telem | `say` alert |
| `learner.query` | Write bubble over you | `say` write |
| `learner.evidence` | Paper bubble over you | `say` paper |
| `agent.say` (Sam's hint) | Sam walks to your desk with a question bubble | Head visit / director visit with question |
| `panel.whisper` | Envelope flies between Vale, Ines and Sam | `memory.pass_down` envelope |
| `learner.answer`, `rival.answer` | Both answers fly to the hatch; it flashes green or red | `candidate` and `compare` |
| `check.result` | Check bubble over Ines; red floating text "duplicates check failed" | `head.review` bubble, `floater` |
| `verdict` | Gavel bubble and floating result over the referee table | `referee.verdict` |
| `mastery.update` | A note flies from your desk to the vault | `memory.write` to the vault |
| `appeal.open`, `appeal.message` | Envelope from your desk to the panel | `memory.pass_down` envelope |
| `appeal.ruling` | Gavel bubble over Ines | `referee.verdict` |
| `voice.line` | Speech bubble plus audio | `say` |
| `sponsor.call` | The sponsor strip counter ticks (no floor animation) | none |

## Log

<!-- One line per finished item: number, what changed, screenshot names. -->

- 6: side panel tabs are now Workspace, Details, Ask, Panel room; Workspace mounts `web/src/workspace/index.tsx` (default or `Workspace` export, props in `ui/WorkspaceTab.tsx`), stays mounted across tab switches, widens to 720px while `onTaskChange(true)`; Workspace button in the top bar opens it. Shots: `06-before.png`, `06-after.png`.
- 1: the original name is "Lab Rotation" on the landing wordmark, top bar, error screen and browser tab title. Shots: `01-before.png`, `01-after.png`, `01-before-topbar.png`, `01-after-topbar.png`.
- 2: cast names by role (first agent per role): director Dr. Vale, head of Team A Sam, librarian Telem, referee Ines, Team A You, Team B Riley; others keep random names. New role labels and "what it can read" lines. No shots (screenshots dropped from the process).
- 3: room plaques now read Dr. Vale's office, Telem's library, Team A: You and Sam, Team B: Riley, Referee: Ines, Your learner profile; the room panels say what each room means for the rotation. Team C and Solo agents are dimmed and labelled "Closed" (decided).
- 4: You wear a gold badge and an always-on "You" name tag, your desk plate reads "Your desk" when zoomed in; Sam's head desk at the back of Team A is always drawn, and Sam sits there when the backend sends him.
- 5: Riley sits at the Team B desk nearest the hatch, plate reads "Riley's desk" when zoomed in; both answers fly to the hatch between the rooms.
- 9: verdict card built from the results card opens when a task's verdict event arrives: your verdict and trap against the key, the Bruin checks next to your cited evidence, your own words when the answer carries them, Riley's answer, sealed. "Open the panel room" or "Back to the lab" closes it. Landing button now reads "Start your rotation".
- Timeline in your rotation: play/pause, scrub back through the session, speed, previous/next moment (task picked, hints, answers, checks, verdict, ruling), and a Live button that jumps to now and follows the session in real time. The lab log follows the scrubbed time.
- Demo: "Watch the demo" on the opening screen, a Demo button in the top bar and a Demo entry in the run picker play the backend's recorded session (getDemo, via the shared demo player) on a loop. The floor follows the player's clock and redraws after a seek or loop; the timeline drives the player; at the end it holds on the verdict card with "Watch again", replaying after 12 s unless you leave the card. The Sample data chip shows while it runs on fake data.
- Framing and motion: the rotation and demo floors frame the rooms in use (Dr. Vale's office, library, Team A, Team B, referee, vault); the whole-lab button and the 0 key still show everything. Between events people at their desks show small working bubbles (reading, writing, searching, checking) and type; `agent.move` walks a person to where it says and they stay there.
- Follow the action: in the rotation and the demo the camera glides slowly in to the room(s) where the latest event happens, holds while things happen, and drifts back out after 6 quiet seconds. It never moves while you drag, zoom, pinch or follow a person (and waits 4 s after); a Follow toggle above the zoom buttons turns it off.
- 10-13: mounted the Workspace session's panels: the sponsor strip just above the timeline in the rotation and demo (the lab log, zoom buttons and side panel sit above it), the mastery chart in your Details panel, the panel room as the Panel room tab, and voice lines with a mute button in the top bar.
- 17 (tour): a 9-step tour of your rotation (the cast one by one, your learner profile, the Workspace, how to read the floor), from the Tour button or the welcome card; the camera holds still during it. Judge mode button still to do.
- Contract: the floor, log and verdict card now follow contract/events.md (verdict result and answer key, check lines, agent.move places, whisper cc, appeal upheld means the grade stands; unknown kinds show their text or why). Panels and the verdict card are wrapped so one failing on unexpected data hides itself instead of blanking the floor.
- Results card: after the last task (every task has a result, or session.end), the results card shows each task passed or failed and the mastery chart, with "Explore the lab" and "Watch again" (replays your session from the start, or restarts the demo). Each person's own station in agent.move (Dr. Vale's office, Ines's terminal) is their seat.
- Old research runs removed: the run picker offers only Your rotation and Demo; web/public/runs (every recorded run and the old demo clip), the runs loader and the old run tour are deleted.
- Demo as a guided story: "Watch the demo" (and the Demo button and picker entry) plays straight away with no welcome box, as 9 scenes in the order the recording has them (brief, context, rival, analysis, question, your answer, panel, verdict, what's next). One caption at a time, bottom center, "Scene N of 9" with Back and Next, plain words plus the event's why; each caption stays at least 5 s (the story speeds through quiet stretches and waits at scene changes). "Explore the lab" in the top left leaves the story. During the demo, bubbles and floating texts queue and show one at a time.
- Floor places (Nived's list): door = lobby door, vale_office = Vale's desk, learner_desk / riley_desk = those desks, shelves = library shelves, terminal = the Bruin terminal (Ines now sits at the bench under the Bruin sign), panel_table = the referee table with a set spot per person, whiteboard = a new easel whiteboard by Sam's desk. Every agent.move walks from `from` to `place`. Whispers show as envelopes only; their words and reason stay hidden in the lab log, Details and captions until the verdict, replays included. Idle: people now and then get up for a short wander near their desk.
- Bruin terminal: Ines's seat at the referee bench now has a bigger screen on a green base.
- 17 (judge mode): "Judge mode" next to "Start your rotation" on the opening screen starts a session with mode judge: one task on its 4-minute clock, a Judge mode chip in the top bar, the Workspace open straight away, and at the verdict the full debrief (verdict card with your mastery chart, and the Panel room transcript beside it). No session starts until the visitor picks rotation, judge mode or the demo.
- 16: when the agents function sends a portrait URL, the Details panel shows it in the portrait frame; with none (or a broken link) it keeps the pixel sprite. Events without their own line read in plain words there ("Walks to the whiteboard", "Says it out loud").
- First-time fixes: the verdict, results, story and tour cards sit over the floor beside the side panel, never on it, and Esc closes the card before the panel. The workspace panel is 600px wide while a task runs and can shrink to a slim bar of tabs to watch the floor. In a live rotation the bottom bar shows only the elapsed time until the session is 30 s old and has a moment to go back to; the clock reads time into the session, the speed shows only when replaying, and replays default to 4x. The lab log prefers each event's own line, uses a reason only when it reads like a sentence, and leaves out system events with no line, voice lines and walks. Telem's real case now arrives after the verdict: the demo's verdict or "What's next" scene says "Telem brings a real case of this mistake".
- Judge mode, step by step: "Judge mode" opens a start card (4 minutes, three steps) and the session and clock start on its Start button. While playing: no run picker, Demo, Tour, sponsor strip or bottom timeline, one clock (the workspace's), Follow off, and a one-line lab log whose reason opens on click. At the verdict, a three-card debrief: the verdict card alone and centered, then how the panel decided (the transcript), then your mastery and Telem's real case; the lab log hides meanwhile, and Esc ends it. If the clock runs out: "Time's up. The panel recorded 'can't tell'." until the verdict. Scores read as percentages or plain words everywhere (no "Passed: 0.9", no meter numbers), and queries read as words, not SQL. New opening tagline. A live session shows only its elapsed time until it ends; then the full timeline for replaying.
- 8: top bar shows Task 1, 2, 3 with passed/failed marks and the time left, all read from the shared rotation state (same clock as the workspace timer); clicking a task opens the Workspace tab. Falls back to the study chips when there is no rotation.
- 7: every rotation event from the shared poll plays one of the floor's existing animations on the cast (table above); the lab log shows the backend's own line for each event. Live animations keep moving while the replay is paused. The hatch shows "answers match" or "answers differ" by comparing the two answers as sent.
- Rotation floor: the floor opens on your rotation, built from the backend's agent list and matched by id (vale, ines, sam, telem, riley, learner); recorded runs stay in the run picker with their timeline, tour and demo. Every event's why shows under its lab log line and in a person's Details panel ("Decisions, and why").
