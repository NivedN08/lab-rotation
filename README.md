# Lab Rotation

Your first week as a data analyst. A panel of AI scientists hands you a dataset that may hide a trap, watches how you work, and grades you against a real answer key. You read the claim, dig through the tables or write SQL, decide whether the claim holds, fails or can't be told, name the trap and cite the rows that prove it. Meanwhile the panel works around you on a pixel lab floor: the librarian looks things up, your mentor drops a hint when you're stuck, a rival AI intern works the same task blind, the panel confers in private, and the examiner runs real data-quality checks before sealing the verdict. Every move on the floor comes with the reason behind it, so you can see why the lab did what it did, and the next task aims at the trap you haven't mastered yet.

Multiplayer AI Hackathon, Track 3 "Grow with Agents".

## Run it

You need Python with [uv](https://docs.astral.sh/uv/) and Node.

1. Start Nived's server (mock mode replays a recorded session, no keys needed):

   ```sh
   LAB_MOCK=1 uv run python web/server.py --port 8790
   ```

2. Start the front end:

   ```sh
   cd web && npm install && npm run dev
   ```

3. Open **http://localhost:5173/?mock=0** to play against the server. Plain **http://localhost:5173** runs on the front end's built-in sample data instead (a "Sample data" chip says so), with no server at all.

**Hosted replay vs live play.** The hosted replay on Vercel is a recorded session built with `VITE_STATIC=1`: it works without Nived's Mac, opens on "Watch the demo" only, and has no live play or questions. Live play (Judge mode, Your rotation, Ask the lab) needs Nived's server.

**Live play at the venue.** Nived's server serves the built page and the real backend together at his address: open that address and play, no `?mock=0` needed.

`npm run build` type-checks and builds the front end into `web/dist`.

## What you can do

- **Judge mode.** One task on a 4-minute clock. A start card explains the three steps, the clock starts on Start, and the screen stays calm while you work. When the verdict arrives, a three-step debrief follows: the verdict card, how the panel decided (their private transcript), then your mastery and a real case of the same mistake. If the clock runs out, the panel records "can't tell".
- **Your rotation.** The full session: Dr. Vale brings tasks one after another, you work them in the Workspace (table browser, SQL, column profiles, chart builder, evidence picker, answer form), and each verdict card shows your answer against the key, the failing check next to your evidence, Riley's answer and the sealed record. The results card at the end shows every task and your skill on each trap. The timeline lets you replay the session once it ends.
- **Watch the demo.** A recorded rotation told as a nine-scene story (the brief, context, the rival, analysis, the question, your answer, the panel confers, the verdict, what's next), one caption at a time with Back and Next. "Explore the lab" leaves the story at any time.
- **Ask the lab.** Put a question to anyone on the panel. Each answers only from what they can see and says what they used; Telem answers with a live search and shows its links and trace.

Click anyone on the floor to see their job, what they can read, and every decision they made with its reason. The camera follows the action (turn "Follow" off to keep it still), and the side panel shrinks to a bar when you want to watch the floor.

## The cast

| Who | Job | What they do |
|---|---|---|
| **Dr. Vale** | Lab head | Picks each task with the learner model, walks the brief to your desk, and sits on the panel that rules on your answer. |
| **Telem** | Librarian | Looks up background on the claim during the brief, keeps a news monitor for the case of the day, and after the verdict brings a real case of the same mistake. |
| **Sam** | Methods reviewer | Watches how you work and, when you're stuck, asks the panel before dropping by with a hint: always a question, never the answer. |
| **Ines** | Examiner | Runs the Bruin data-quality checks at the referee bench, grades your verdict, trap and evidence against the answer key, seals the record and rules on appeals. |
| **Riley** | AI intern | Your rival: works the same task from the same tables without ever seeing yours. Both answers meet at the hatch between the rooms. |
| **You** | Rotation student | Your desk is in Team A. The workspace is yours; the panel only sees what you do there. |

## Sponsor tools

The backend (Nived's part) wires the sponsors in `lab/sponsors/`, each with a recorded fallback: **BAND** carries the panel's private room, **Telem AI** does the librarian's searches and case of the day, **Bruin** runs the trap checks behind every verdict, **Runware** gives the cast their voices and portraits and runs Riley on an open model, **Glasser** supplies real retail numbers for tasks, hints and the verdict's reality check, and **Teamily** is where the practice summary after a rotation will go (a stub that saves it locally for now). The sponsor strip above the timeline counts every call live. The routes and events are documented in `contract/api.md` and `contract/events.md`.

## How it was built

Built on our earlier pixel-lab project, with the moderators' approval; the learner's seat, workspace, panel, judge mode, demo story and backend connection were built today.
