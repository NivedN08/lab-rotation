"""BAND room for the panel: post each agent's line into the Panel room as that agent.

Our engine gets every reply from `claude -p`; this module only carries it. Vale, Ines
and Sam each post with their own key (`BAND_<NAME>_API_KEY`, `BAND_<NAME>_AGENT_ID`).
Telem and Riley have no BAND identity, so Vale relays their lines with a name prefix.
BAND requires at least one @mention per message and only delivers to those mentioned.

When BAND is not configured, `BAND_LOCAL=1`, or a post fails, a local room answers with
the same message shape and `local: True` (written to `data/band_local/<room>.jsonl`).

    room = BandRoom(on_call=engine.sponsor_call)
    msg = room.post("vale", "Grade t1 when ready.", mentions=["ines"])
    msg.id, msg.local

Live check (posts one test line, reads it back over WebSocket and REST):

    uv run python -m lab.sponsors.band check
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Iterable, Optional

from lab.sponsors.calls import DATA, Reporter, SponsorCall, Timer, report, short_error

NAMES = {"vale": "Vale", "ines": "Ines", "sam": "Sam", "telem": "Telem", "riley": "Riley",
         "learner": "Learner"}
BAND_AGENTS = ("vale", "ines", "sam")  # the panel agents with their own BAND key
RELAY = "vale"  # posts for agents without a BAND identity
TIMEOUT_S = 8
MAX_FAILS = 2  # after this many failed posts in a row, stay local for the session
MARKER = re.compile(r"@\[\[([0-9a-fA-F-]{8,})\]\]")


@dataclass
class BandMessage:
    id: str
    room: str
    agent: str  # who spoke (our agent id)
    text: str  # with @Names, as people read it
    mentions: list = field(default_factory=list)  # our agent ids
    at: float = 0.0  # unix seconds
    local: bool = False
    relayedBy: Optional[str] = None

    def as_dict(self) -> dict:
        return asdict(self)


def rest_url() -> str:
    from band.config import settings

    return os.environ.get("BAND_REST_URL") or settings.DEFAULT_REST_URL


def ws_url() -> str:
    from band.config import settings

    return os.environ.get("BAND_WS_URL") or settings.DEFAULT_WS_URL


def configured() -> bool:
    if os.environ.get("BAND_LOCAL") == "1":
        return False
    names = ["BAND_ROOM_ID"] + [f"BAND_{a.upper()}_{k}" for a in BAND_AGENTS for k in ("API_KEY", "AGENT_ID")]
    return all(os.environ.get(n) for n in names)


def _make_rest(agent: str):
    from band_rest import RestClient

    return RestClient(api_key=os.environ[f"BAND_{agent.upper()}_API_KEY"], base_url=rest_url())


class BandRoom:
    """The Panel room. Live over BAND when configured, else a local room."""

    def __init__(self, room_id: Optional[str] = None, *, on_call: Reporter = None,
                 local: Optional[bool] = None, rest_factory=None, log_dir=None):
        from lab.env import load_env

        load_env()
        self.on_call = on_call
        self.live = configured() if local is None else not local
        self.room_id = room_id or os.environ.get("BAND_ROOM_ID") or "local-panel"
        self._rest_factory = rest_factory or _make_rest
        self._rest: dict = {}
        self._fails = 0
        self.ids = {a: os.environ.get(f"BAND_{a.upper()}_AGENT_ID", "") for a in BAND_AGENTS}
        self._by_band_id = {v: k for k, v in self.ids.items() if v}
        self._names_by_band_id = {v: NAMES[k] for k, v in self.ids.items() if v}
        self.log_dir = log_dir or (DATA / "band_local")
        self.local_messages: list[BandMessage] = []

    # -- public ---------------------------------------------------------------

    def health(self) -> str:
        return "live" if self.live else "local"

    def post(self, agent: str, text: str, mentions: Iterable[str] = (), *, op: str = "send_message",
             label: Optional[str] = None) -> BandMessage:
        """Post `text` as `agent`, @mentioning `mentions` (our agent ids)."""
        mentions = [m for m in dict.fromkeys(mentions) if m != agent]
        label = label or f"{NAMES.get(agent, agent)} posted to the Panel room"
        if self.live:
            t = Timer()
            try:
                msg = self._post_live(agent, text, mentions)
                self._fails = 0
                report(self.on_call, SponsorCall("band", op, label, ok=True, ms=t.ms, by=agent))
                return msg
            except Exception as exc:  # noqa: BLE001 - fall back to the local room
                self._fails += 1
                if self._fails >= MAX_FAILS:
                    self.live = False
                report(self.on_call, SponsorCall("band", op, label, ok=False, ms=t.ms, by=agent,
                                                 fallback=True, error=short_error(exc)))
                return self._post_local(agent, text, mentions)
        msg = self._post_local(agent, text, mentions)
        report(self.on_call, SponsorCall("band", op, label + " (local room)", ok=True, ms=0, by=agent,
                                         fallback=True))
        return msg

    def relay_appeal(self, text: str, by: str = RELAY) -> BandMessage:
        """There is no human (user) key, so an agent carries the learner's appeal into the room."""
        return self.post(by, f"Learner appeal: {text}", mentions=["ines"], op="appeal",
                         label=f"{NAMES.get(by, by)} relayed the learner's appeal")

    def read(self, as_agent: str = "ines", limit: int = 20) -> list[BandMessage]:
        """Most recent messages first, as `as_agent` sees them."""
        if not self.live:
            return list(reversed(self.local_messages))[:limit]
        t = Timer()
        try:
            r = self._client(as_agent).agent_api_messages.list_agent_messages(
                chat_id=self.room_id, status="all", sort_order="desc", limit=limit,
                request_options={"timeout_in_seconds": TIMEOUT_S, "max_retries": 1})
            out = [self._from_band(m) for m in (r.data or [])]
            report(self.on_call, SponsorCall("band", "read", f"{NAMES.get(as_agent, as_agent)} read the Panel room",
                                             ms=t.ms, by=as_agent, count=1))
            return out
        except Exception as exc:  # noqa: BLE001
            report(self.on_call, SponsorCall("band", "read", "Read the Panel room", ok=False, ms=t.ms, by=as_agent,
                                             fallback=True, error=short_error(exc)))
            return list(reversed(self.local_messages))[:limit]

    def render(self, content: str) -> str:
        """Turn BAND's `@[[participant id]]` markers back into `@Name`."""
        return MARKER.sub(lambda m: "@" + self._names_by_band_id.get(m.group(1), "someone"), content)

    # -- live -----------------------------------------------------------------

    def _client(self, agent: str):
        if agent not in self._rest:
            self._rest[agent] = self._rest_factory(agent)
        return self._rest[agent]

    def _post_live(self, agent: str, text: str, mentions: list) -> BandMessage:
        from band_rest.types.chat_message_request import ChatMessageRequest
        from band_rest.types.chat_message_request_mentions_item import ChatMessageRequestMentionsItem

        sender = agent if agent in BAND_AGENTS else RELAY
        relayed = None if sender == agent else sender
        body = text if relayed is None else f"{NAMES.get(agent, agent)}: {text}"
        targets = [m for m in mentions if m in BAND_AGENTS and m != sender]
        if not targets:  # BAND needs one mention; default to the lab head, or Ines when Vale speaks
            targets = ["ines" if sender == "vale" else "vale"]
        named = " ".join(f"@{NAMES[m]}" for m in mentions if m not in targets)
        head = " ".join(f"@{NAMES[m]}" for m in targets)
        content = f"{head} {named + ' ' if named else ''}{body}"
        req = ChatMessageRequest(
            content=content,
            mentions=[ChatMessageRequestMentionsItem(id=self.ids[m], name=NAMES[m]) for m in targets])
        r = self._client(sender).agent_api_messages.create_agent_chat_message(
            chat_id=self.room_id, message=req,
            request_options={"timeout_in_seconds": TIMEOUT_S, "max_retries": 0})
        mid = getattr(getattr(r, "data", None), "id", None)
        if not mid:
            raise RuntimeError("no message id")
        return BandMessage(id=mid, room=self.room_id, agent=agent, text=content, mentions=list(mentions),
                           at=time.time(), local=False, relayedBy=relayed)

    def _from_band(self, m) -> BandMessage:
        agent = self._by_band_id.get(m.sender_id, "learner" if m.sender_type == "User" else "system")
        text = self.render(m.content)
        relayed = None
        if agent == RELAY:
            for who in ("telem", "riley"):
                if re.match(rf"^(@\w+ )*{NAMES[who]}: ", text):
                    agent, relayed = who, RELAY
        at = m.inserted_at.timestamp() if getattr(m, "inserted_at", None) else 0.0
        mentioned = [self._by_band_id[i] for i in MARKER.findall(m.content) if i in self._by_band_id]
        return BandMessage(id=m.id, room=self.room_id, agent=agent, text=text, mentions=mentioned, at=at,
                           local=False, relayedBy=relayed)

    # -- local ----------------------------------------------------------------

    def _post_local(self, agent: str, text: str, mentions: list) -> BandMessage:
        head = " ".join(f"@{NAMES.get(m, m)}" for m in mentions)
        msg = BandMessage(id=f"local-{uuid.uuid4().hex[:12]}", room=self.room_id, agent=agent,
                          text=f"{head} {text}".strip(), mentions=list(mentions), at=time.time(), local=True)
        self.local_messages.append(msg)
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            with open(self.log_dir / f"{self.room_id}.jsonl", "a") as f:
                f.write(json.dumps(msg.as_dict()) + "\n")
        except OSError:
            pass
        return msg


# -- WebSocket ----------------------------------------------------------------

def make_link(agent: str):
    """A BandLink (WebSocket + REST) for one panel agent. One process per listening agent."""
    from band.platform.link import BandLink

    return BandLink(agent_id=os.environ[f"BAND_{agent.upper()}_AGENT_ID"],
                    api_key=os.environ[f"BAND_{agent.upper()}_API_KEY"], ws_url=ws_url(), rest_url=rest_url())


async def ws_check(sender: str = "vale", reader: str = "ines", wait_s: float = 20) -> dict:
    """Connect the three panel agents over WebSocket, post one test line, read it back.

    Returns {connected: {agent: bool}, messageId, wsReceived, restReceived, ms}. Posts one
    short line into the Panel room, so call it only for a go/no-go.
    """
    import asyncio

    from band.platform.event import MessageEvent

    from lab.env import load_env

    load_env()
    room = os.environ["BAND_ROOM_ID"]
    t = Timer()
    links = {a: make_link(a) for a in BAND_AGENTS}
    connected = {}
    try:
        for a, link in links.items():
            await link.connect()
            await link.subscribe_room(room)
            connected[a] = link.is_connected
        rm = BandRoom(room)
        msg = await asyncio.to_thread(rm.post, sender, f"BAND link test at {time.strftime('%H:%M:%S')}. No reply needed.",
                                      [reader])

        async def wait():
            async for ev in links[reader]:
                if isinstance(ev, MessageEvent) and ev.payload and ev.payload.id == msg.id:
                    return True

        try:
            ws_ok = await asyncio.wait_for(wait(), timeout=wait_s)
        except asyncio.TimeoutError:
            ws_ok = False
        back = await asyncio.to_thread(rm.read, reader, 5)
        return {"connected": connected, "messageId": msg.id, "local": msg.local, "wsReceived": bool(ws_ok),
                "restReceived": any(m.id == msg.id for m in back), "ms": t.ms}
    finally:
        for link in links.values():
            try:
                await link.disconnect()
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    import asyncio
    import sys

    if sys.argv[1:] == ["check"]:
        print(json.dumps(asyncio.run(ws_check()), indent=2))
    else:
        print("usage: python -m lab.sponsors.band check")
