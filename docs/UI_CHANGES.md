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
- [ ] 9. Verdict card, built from the results card: your verdict against the key, the failing Bruin check next to your evidence, your quoted words, Riley's answer, "sealed" (`App.tsx` or `ui/Verdict.tsx`)
- [ ] 10. Sponsor strip: a thin bar above the timeline counting BAND messages, Telem searches (with trace links), Bruin checks run and failed, Runware lines and cost, Glasser calls (`ui/SponsorStrip.tsx`)
- [ ] 11. Mastery chart: one bar per trap type; shown in your Details panel and on the verdict card (`ui/Mastery.tsx`, `ui/Panels.tsx`)
- [ ] 12. Audio: play each voice line as it appears, with a mute button in the top bar
- [ ] 13. Panel room tab in the side panel: the BAND transcript, opened after the verdict
- [ ] 14. Live updates every second instead of every 8 (`App.tsx`), or the event stream if Nived ships it
- [ ] 15.* Appeal view inside the Panel room tab
- [ ] 16.* Runware portraits in the Details panel (`ui/Avatar.tsx`)
- [ ] 17.* Tour rewritten for a rotation (`ui/tour.ts`); judge mode button on the landing page

**Workspace session** (only `web/src/workspace/`, own `workspace.css`)

- [x] W1. Table browser: tabs per table, rows with a row cap
- [x] W2. SQL box: runs on the server (Nived's runner), shows results and errors
- [x] W3. Evidence picker: click rows, columns or cells to cite them
- [x] W4. Answer form: holds / fails / can't tell, the trap you found, your evidence, submit
- [x] W5. Timer and the empty, loading and error states
- [ ] W6.* Column profile (one click per column)
- [ ] W7.* Chart builder
- [ ] W8.* Voice input (browser speech to text into the answer form)

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
- 9 (layout only, not ticked): verdict card component built from the results card; takes the verdict, check.result and answer event data as props. Wired up once the shared rotation state lands.
- 8: top bar shows Task 1, 2, 3 with passed/failed marks and the time left, all read from the shared rotation state (same clock as the workspace timer); clicking a task opens the Workspace tab. Falls back to the study chips when there is no rotation.
- 7: every rotation event from the shared poll plays one of the floor's existing animations on the cast (table above); the lab log shows the backend's own line for each event. Live animations keep moving while the replay is paused. The hatch shows "answers match" or "answers differ" by comparing the two answers as sent.
- Rotation floor: the floor opens on your rotation, built from the backend's agent list and matched by id (vale, ines, sam, telem, riley, learner); recorded runs stay in the run picker with their timeline, tour and demo. Every event's why shows under its lab log line and in a person's Details panel ("Decisions, and why").
