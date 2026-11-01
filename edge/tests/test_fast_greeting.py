"""03-F15: the greeting is spoken as soon as it streams in, before Claude has
finished the per-visitor clues and shout-outs; storage copes with a greeting
that finishes before its sighting row is written."""

import asyncio

from costume_spotter.events import (
    CommentSpoken,
    CostumeIdentified,
    EventBus,
    GreetingReady,
    GroupSpotted,
    SpottedVisitor,
)
from costume_spotter.events.events import BoundingBox
from costume_spotter.storage import SightingRepository
from costume_spotter.storage.logger import SightingLogger
from costume_spotter.storage.snapshots import SnapshotStore
from costume_spotter.vision.identifier import CostumeIdentifier
from tests.conftest import drain, eventually

LONE = ('{"greeting": "A pumpkin king! \\"Long live the king.\\"", "people": '
        '[{"clues": "orange, crown", "age": "little kid", "costume": "Pumpkin king",'
        ' "confidence": "high", "shout_out": "Royal gourd!"}]}')
PAIR = ('{"greeting": "Spooky squad!", "people": ['
        '{"clues": "cape", "age": "big kid", "costume": "Vampire", "confidence": "high",'
        ' "shout_out": "Fangs out!"},'
        '{"clues": "hat", "age": "little kid", "costume": "Witch", "confidence": "high",'
        ' "shout_out": "Great hat!"}]}')


class StreamingClient:
    """Mimics AsyncAnthropic().messages.stream(): yields the reply in chunks and
    can pause right after the greeting, so tests see what happens mid-reply."""

    def __init__(self, reply: str, fail_after_greeting: bool = False) -> None:
        self.reply = reply
        self.fail_after_greeting = fail_after_greeting
        self.paused = asyncio.Event()
        self.resume = asyncio.Event()
        self.calls: list[dict] = []
        client = self

        class Messages:
            def stream(self, **request):
                client.calls.append(request)
                return client._Stream(client)

        self.messages = Messages()

    class _Stream:
        def __init__(self, client) -> None:
            self.client = client

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        @property
        async def text_stream(self):
            reply = self.client.reply
            cut = reply.index('"people"')
            for i in range(0, cut, 7):  # the greeting, a few characters at a time
                yield reply[i:min(i + 7, cut)]
            self.client.paused.set()
            await self.client.resume.wait()
            if self.client.fail_after_greeting:
                raise ConnectionError("dropped mid-reply")
            yield reply[cut:]


def group(*kinds: str) -> GroupSpotted:
    return GroupSpotted(group_id="g1", visitors=tuple(
        SpottedVisitor(visitor_id=i, snapshot_jpeg=b"\xff\xd8fake",
                       box=BoundingBox(10, 10, 40, 80), visitor_type=kind)
        for i, kind in enumerate(kinds, start=1)))


async def wired(client: StreamingClient, shout_out_max_group: int = 1):
    bus = EventBus()
    identifier = CostumeIdentifier(bus, api_key="sk-test", model="x", timeout_seconds=5,
                                   detector_name="mock", sarcasm_rate=0,
                                   shout_out_max_group=shout_out_max_group)
    identifier._client = client  # noqa: SLF001
    greetings: list = []
    identified: list = []

    async def on_greeting(event):
        greetings.append(event)

    async def on_identified(event):
        identified.append(event)

    bus.subscribe(on_greeting, to=(GreetingReady,), name="t.greet")
    bus.subscribe(on_identified, to=(CostumeIdentified,), name="t.id")
    await bus.start()
    return bus, greetings, identified


async def test_a_lone_visitor_hears_the_greeting_before_claude_finishes():
    client = StreamingClient(LONE)
    bus, greetings, identified = await wired(client)
    bus.publish(group("person"))
    await asyncio.wait_for(client.paused.wait(), 5)
    await eventually(lambda: len(greetings) == 1)
    assert greetings[0].text == 'A pumpkin king! "Long live the king."'  # unescaped
    assert identified == []  # Claude is still writing the clues
    client.resume.set()
    await eventually(lambda: len(identified) == 1)
    await drain(bus)
    assert len(greetings) == 1  # nothing more to say for one visitor
    assert identified[0].costume == "Pumpkin king"
    assert greetings[0].sighting_ids == (identified[0].sighting_id,)
    system = client.calls[0]["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}  # prompt caching
    await bus.stop()


async def test_a_group_hears_one_greeting_for_everyone():  # 04-F11
    client = StreamingClient(PAIR)
    client.resume.set()
    bus, greetings, identified = await wired(client)
    bus.publish(group("person", "person"))
    await eventually(lambda: len(identified) == 2)
    await drain(bus)
    assert [g.text for g in greetings] == ["Spooky squad!"]
    await bus.stop()


async def test_shout_outs_follow_the_greeting_when_turned_on():
    client = StreamingClient(PAIR)
    client.resume.set()
    bus, greetings, identified = await wired(client, shout_out_max_group=3)
    bus.publish(group("person", "person"))
    await eventually(lambda: len(greetings) == 2 and len(identified) == 2)
    assert [g.text for g in greetings] == ["Spooky squad!", "Fangs out! Great hat!"]
    assert greetings[0].sighting_ids == greetings[1].sighting_ids
    await bus.stop()


async def test_a_failure_after_the_greeting_is_not_retried():
    client = StreamingClient(LONE, fail_after_greeting=True)
    client.resume.set()
    bus, greetings, identified = await wired(client)
    bus.publish(group("person"))
    await eventually(lambda: len(identified) == 1)
    await drain(bus)
    assert len(client.calls) == 1  # a retry would greet them twice
    assert len(greetings) == 1
    assert identified[0].source == "fallback"
    await bus.stop()


async def test_spoken_before_the_row_exists_still_marks_it_spoken(tmp_path):
    bus = EventBus()
    repo = SightingRepository(tmp_path / "t.db")
    SightingLogger(bus, repo, SnapshotStore(tmp_path / "snaps", retention_days=7))
    await bus.start()
    bus.publish(CommentSpoken(sighting_id="s1", text="Boo!", engine="x", spoken=True))
    await drain(bus)
    bus.publish(CostumeIdentified(
        sighting_id="s1", visitor_id=1, costume="ghost", confidence="high",
        comment="Boo!", source="claude", snapshot_jpeg=b"\xff\xd8", box=BoundingBox(1, 1, 2, 2),
        detector="mock"))
    await drain(bus)
    assert repo.get("s1").spoken is True
    await bus.stop()
