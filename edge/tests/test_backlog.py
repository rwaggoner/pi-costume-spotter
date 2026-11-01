"""04-F11 (no backlog of greetings) and 03-F16 (shared costume themes)."""

import asyncio
from datetime import UTC, datetime, timedelta

from costume_spotter.events import (
    CommentSpoken,
    CostumeIdentified,
    EventBus,
    GreetingReady,
    GroupSpotted,
    SpottedVisitor,
)
from costume_spotter.events.events import BoundingBox
from costume_spotter.speech import SpeechService
from costume_spotter.speech.base import AudioPlayer
from costume_spotter.speech.null import NullTtsEngine
from costume_spotter.vision import prompts
from costume_spotter.vision.identifier import CostumeIdentifier
from tests.conftest import drain, eventually

OZ = ('{"theme": "The Wizard of Oz", "greeting": "Follow the yellow brick road, Dorothy '
      'and friends!", "people": [{"clues": "blue gingham, red shoes", "age": "little kid",'
      ' "costume": "Dorothy", "confidence": "high"}, {"clues": "straw, hat", "age": '
      '"big kid", "costume": "Scarecrow", "confidence": "high"}]}')


def group(group_id: str, size: int, spotted_at: datetime | None = None) -> GroupSpotted:
    kwargs = {"timestamp": spotted_at} if spotted_at else {}
    return GroupSpotted(group_id=group_id, visitors=tuple(
        SpottedVisitor(visitor_id=i, snapshot_jpeg=b"\xff\xd8x", box=BoundingBox(1, 1, 9, 9))
        for i in range(size)), **kwargs)


# -- themes (03-F16) ---------------------------------------------------------------

def test_prompt_asks_for_a_theme_before_the_greeting():
    text = prompts.SYSTEM_PROMPT
    assert text.index('"theme"') < text.index('"greeting": "the greeting"')
    assert "Themes:" in text and "Never invent a theme" in text
    assert "Don't greet group members one by one" in text
    assert "spot any theme" in prompts.user_prompt(3)
    assert "shout-out" not in prompts.user_prompt(3)
    assert "shout-out" in prompts.user_prompt(3, shout_outs=True)


def test_parse_reads_the_theme():
    reading = CostumeIdentifier._parse(OZ, count=2)
    assert reading.theme == "The Wizard of Oz"
    for empty in ("null", '"none"'):
        reply = '{"theme": ' + empty + ', "greeting": "Hi!", "people": []}'
        assert CostumeIdentifier._parse(reply).theme == ""


async def test_the_theme_rides_along_with_each_sighting():
    bus = EventBus()
    identifier = CostumeIdentifier(bus, api_key="sk-test", model="x", timeout_seconds=5,
                                   detector_name="mock", sarcasm_rate=0)

    class Client:
        class messages:  # noqa: N801
            @staticmethod
            async def create(**kwargs):
                return type("R", (), {"content": [type("B", (), {"text": OZ})()]})()

    identifier._client = Client()  # noqa: SLF001
    identified: list = []
    greetings: list = []

    async def on_identified(e):
        identified.append(e)

    async def on_greeting(e):
        greetings.append(e)

    bus.subscribe(on_identified, to=(CostumeIdentified,), name="t.i")
    bus.subscribe(on_greeting, to=(GreetingReady,), name="t.g")
    await bus.start()
    bus.publish(group("oz", 2))
    await eventually(lambda: len(identified) == 2)
    await drain(bus)
    assert {e.theme for e in identified} == {"The Wizard of Oz"}
    assert [g.text for g in greetings] == ["Follow the yellow brick road, Dorothy and friends!"]
    await bus.stop()


# -- identification runs side by side (04-F11) -----------------------------------

async def test_groups_are_identified_side_by_side():
    bus = EventBus()
    identifier = CostumeIdentifier(bus, api_key="sk-test", model="x", timeout_seconds=5,
                                   detector_name="mock", sarcasm_rate=0, max_concurrent=3)
    in_flight, most, release = [0], [0], asyncio.Event()

    class SlowClient:
        class messages:  # noqa: N801
            @staticmethod
            async def create(**kwargs):
                in_flight[0] += 1
                most[0] = max(most[0], in_flight[0])
                await release.wait()
                in_flight[0] -= 1
                return type("R", (), {"content": [type("B", (), {
                    "text": '{"greeting": "Hi!", "people": [{"costume": "ghost"}]}'})()]})()

    identifier._client = SlowClient()  # noqa: SLF001
    greetings: list = []

    async def on_greeting(e):
        greetings.append(e)

    bus.subscribe(on_greeting, to=(GreetingReady,), name="t.g")
    await bus.start()
    for n in range(4):
        bus.publish(group(f"g{n}", 1))
    await eventually(lambda: most[0] == 3)  # three calls at once, the fourth waits its turn
    release.set()
    await eventually(lambda: len(greetings) == 4)
    assert most[0] == 3
    await bus.stop()


# -- late greetings are skipped (04-F11) --------------------------------------------

class Recording(AudioPlayer):
    def __init__(self) -> None:
        self.played = 0

    def play(self, wav_bytes: bytes) -> None:
        self.played += 1


async def test_a_greeting_for_people_who_have_left_is_skipped():
    bus = EventBus()
    player = Recording()
    SpeechService(bus, NullTtsEngine(), player, max_delay_seconds=12)
    spoken: list = []

    async def on_spoken(e):
        spoken.append(e)

    bus.subscribe(on_spoken, to=(CommentSpoken,), name="t.s")
    await bus.start()
    now = datetime.now(UTC)
    bus.publish(GreetingReady(group_id="old", text="Hello, ghost!", sighting_ids=("a",),
                              spotted_at=now - timedelta(seconds=30)))
    bus.publish(GreetingReady(group_id="new", text="Hello, witch!", sighting_ids=("b",),
                              spotted_at=now))
    await drain(bus)
    assert player.played == 1
    assert {(e.sighting_id, e.spoken, e.skipped_late) for e in spoken} == {
        ("a", False, True), ("b", True, False)}
    await bus.stop()


async def test_zero_means_never_skip():
    bus = EventBus()
    player = Recording()
    SpeechService(bus, NullTtsEngine(), player, max_delay_seconds=0)
    await bus.start()
    bus.publish(GreetingReady(group_id="old", text="Hi", sighting_ids=("a",),
                              spotted_at=datetime.now(UTC) - timedelta(minutes=5)))
    await drain(bus)
    assert player.played == 1
    await bus.stop()
