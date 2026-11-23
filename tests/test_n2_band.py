"""BAND room: live posting through a fake REST client, local fallback, rendering."""

import asyncio
import datetime as dt
import types

import pytest

from lab.sponsors import band
from lab.sponsors.band import BandRoom

IDS = {"vale": "11111111-aaaa-bbbb-cccc-000000000001", "ines": "11111111-aaaa-bbbb-cccc-000000000002",
       "sam": "11111111-aaaa-bbbb-cccc-000000000003"}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("BAND_ROOM_ID", "room-1")
    monkeypatch.delenv("BAND_LOCAL", raising=False)
    for a, i in IDS.items():
        monkeypatch.setenv(f"BAND_{a.upper()}_AGENT_ID", i)
        monkeypatch.setenv(f"BAND_{a.upper()}_API_KEY", f"test-key-{a}")
    return tmp_path


class FakeRest:
    """Records posts per sender; turns @Name into BAND's @[[id]] marker like the server."""

    def __init__(self, agent, store, fail=False):
        self.agent, self.store, self.fail = agent, store, fail
        self.agent_api_messages = self

    def create_agent_chat_message(self, chat_id, message, request_options=None):
        if self.fail:
            raise ConnectionError("down")
        content = message.content
        for m in message.mentions:
            content = content.replace(f"@{m.name}", f"@[[{m.id}]]", 1)
        mid = f"m{len(self.store) + 1}"
        self.store.append(dict(id=mid, sender=self.agent, content=content, mentions=[m.id for m in message.mentions]))
        return types.SimpleNamespace(data=types.SimpleNamespace(id=mid))

    def list_agent_messages(self, chat_id, **kw):
        rows = [types.SimpleNamespace(id=s["id"], sender_id=IDS[s["sender"]], sender_type="Agent", content=s["content"],
                                      inserted_at=dt.datetime(2026, 11, 23, 12, 0)) for s in reversed(self.store)]
        return types.SimpleNamespace(data=rows)


def room(env, fail=False, calls=None):
    store = []
    r = BandRoom(on_call=(calls.append if calls is not None else None), log_dir=env,
                 rest_factory=lambda a: FakeRest(a, store, fail))
    return r, store


def test_configured_from_env(env, monkeypatch):
    assert band.configured()
    monkeypatch.setenv("BAND_LOCAL", "1")
    assert not band.configured()


def test_post_as_agent_with_mention(env):
    calls = []
    r, store = room(env, calls=calls)
    msg = r.post("vale", "Grade t1 when ready.", mentions=["ines"])
    assert not msg.local and msg.id == "m1" and msg.agent == "vale"
    assert store[0]["sender"] == "vale" and store[0]["mentions"] == [IDS["ines"]]
    assert calls[0].sponsor == "band" and calls[0].ok and not calls[0].fallback
    assert calls[0].event_data()["op"] == "send_message"


def test_message_without_mention_gets_default(env):
    r, store = room(env)
    r.post("vale", "Starting.")
    r.post("sam", "Hint ready.")
    assert store[0]["mentions"] == [IDS["ines"]]
    assert store[1]["mentions"] == [IDS["vale"]]


def test_telem_and_riley_relay_through_vale(env):
    r, store = room(env)
    msg = r.post("telem", "Found a case of duplicated receipts.", mentions=["ines", "riley"])
    assert store[0]["sender"] == "vale" and msg.relayedBy == "vale" and msg.agent == "telem"
    assert "Telem: Found a case" in store[0]["content"] and "@Riley" in store[0]["content"]
    back = r.read("ines")
    assert back[0].agent == "telem" and back[0].relayedBy == "vale"
    assert back[0].text.startswith("@Ines @Riley Telem:")


def test_render_markers(env):
    r, _ = room(env)
    assert r.render(f"@[[{IDS['ines']}]] look") == "@Ines look"
    assert r.render("@[[99999999-0000-0000-0000-000000000000]] hi") == "@someone hi"


def test_failure_falls_back_to_local_then_stays_local(env):
    calls = []
    r, _ = room(env, fail=True, calls=calls)
    m1 = r.post("vale", "one", mentions=["ines"])
    assert m1.local and m1.id.startswith("local-")
    assert calls[0].ok is False and calls[0].fallback and calls[0].event_data()["failed"] is True
    assert "down" not in (calls[0].error or "")  # only the class name is kept
    r.post("vale", "two", mentions=["ines"])
    assert r.health() == "local"
    assert (env / "room-1.jsonl").read_text().count("\n") == 2


def test_local_room_same_shape(env):
    r = BandRoom(local=True, log_dir=env)
    msg = r.post("ines", "Check failed on spend range.", mentions=["vale"])
    assert msg.local and msg.text == "@Vale Check failed on spend range."
    assert set(msg.as_dict()) == {"id", "room", "agent", "text", "mentions", "at", "local", "relayedBy"}
    assert r.read()[0].id == msg.id


def test_appeal_relayed_to_ines(env):
    r, store = room(env)
    msg = r.relay_appeal("The cents column was explained in the brief.")
    assert store[0]["sender"] == "vale" and store[0]["mentions"] == [IDS["ines"]]
    assert "Learner appeal:" in msg.text


@pytest.mark.live
def test_live_ws_roundtrip():
    from lab.env import load_env

    load_env()
    if not band.configured():
        pytest.skip("BAND not configured")
    out = asyncio.run(band.ws_check())
    assert all(out["connected"].values())
    assert not out["local"] and out["wsReceived"] and out["restReceived"]
