"""CostumeIdentifier: one call per group, pretend mode, parsing, and the fallback
path (03-F6/F7/F9, 04-F9).

The Claude API itself is never called in tests: ``_parse`` is tested directly
with representative model outputs, the request shape with a recording stub, and
the event flow in pretend mode and with a stubbed client that always fails.
"""

import pytest

from costume_spotter.events import (
    CostumeIdentified,
    EventBus,
    GreetingReady,
    GroupSpotted,
    SpottedVisitor,
)
from costume_spotter.events.events import BoundingBox
from costume_spotter.vision import prompts
from costume_spotter.vision.identifier import (
    CostumeIdentifier,
    GroupReading,
    PersonReading,
)
from tests.conftest import drain, eventually


def make_group(size: int = 1, kinds: tuple[str, ...] = ()) -> GroupSpotted:
    kinds = kinds or ("person",) * size
    return GroupSpotted(group_id="g1", visitors=tuple(
        SpottedVisitor(visitor_id=i, snapshot_jpeg=b"\xff\xd8fake",
                       box=BoundingBox(10, 10, 40, 80), visitor_type=kind)
        for i, kind in enumerate(kinds, start=1)))


def make_identifier(bus: EventBus, api_key: str | None = None) -> CostumeIdentifier:
    return CostumeIdentifier(bus, api_key=api_key, model="x", timeout_seconds=1,
                             detector_name="mock")


async def collect(bus: EventBus) -> tuple[list, list]:
    identified: list = []
    greetings: list = []

    async def on_identified(event):
        identified.append(event)

    async def on_greeting(event):
        greetings.append(event)

    bus.subscribe(on_identified, to=(CostumeIdentified,), name="test.identified")
    bus.subscribe(on_greeting, to=(GreetingReady,), name="test.greetings")
    return identified, greetings


# -- key validation (issue #1) ------------------------------------------------

def test_non_ascii_api_key_is_rejected_at_startup():
    """The pasted-placeholder key ('sk-ant-…', real Unicode ellipsis) must fail
    loudly at construction, not as three doomed retries per visitor."""
    with pytest.raises(ValueError, match="non-ASCII"):
        make_identifier(EventBus(), api_key="sk-ant-…")


# -- pretend mode (03-F7) ----------------------------------------------------

async def test_pretend_mode_identifies_a_lone_visitor():
    bus = EventBus()
    identifier = make_identifier(bus)
    identified, greetings = await collect(bus)
    await bus.start()

    bus.publish(make_group(1))
    await drain(bus)

    assert identifier.mode == "pretend"
    assert len(identified) == 1 and len(greetings) == 1
    assert identified[0].source == "pretend"
    assert identified[0].sighting_id  # UUID minted
    assert greetings[0].text == identified[0].comment  # alone: greeting = comment
    assert greetings[0].sighting_ids == (identified[0].sighting_id,)
    await bus.stop()


async def test_a_group_gets_one_greeting_and_a_sighting_each():  # 03-F9, 04-F9
    bus = EventBus()
    make_identifier(bus)
    identified, greetings = await collect(bus)
    await bus.start()

    bus.publish(make_group(3))
    await drain(bus)

    assert len(identified) == 3 and len(greetings) == 1
    assert {e.group_id for e in identified} == {"g1"}
    assert all(e.group_size == 3 for e in identified)
    assert greetings[0].sighting_ids == tuple(e.sighting_id for e in identified)
    # 3 people ≤ shout_out_max_group: each shout-out is part of what's spoken.
    for event in identified:
        assert event.comment in greetings[0].text
    await bus.stop()


async def test_fallback_when_api_is_down():  # 03-F6
    bus = EventBus()
    identifier = make_identifier(bus, api_key="sk-test")

    class AlwaysDown:
        class messages:  # noqa: N801 — mimics the SDK's shape
            @staticmethod
            async def create(**kwargs):
                raise ConnectionError("no internet on the porch")

    identifier._client = AlwaysDown()  # noqa: SLF001 — inject the failure
    identified, greetings = await collect(bus)
    await bus.start()

    bus.publish(make_group(2))
    # eventually, not drain: the handler is in-flight (queue empty) for the
    # whole retry backoff (03-F8) before it publishes the fallback.
    await eventually(lambda: len(greetings) == 1, timeout=10)

    assert [e.source for e in identified] == ["fallback", "fallback"]
    assert identified[0].costume == "mystery guest"
    assert greetings[0].text  # the porch still says something
    await bus.stop()


async def test_one_request_carries_every_photo_labeled_in_order():  # 03-F9
    bus = EventBus()
    identifier = make_identifier(bus, api_key="sk-test")
    calls: list = []

    class Recorder:
        class messages:  # noqa: N801
            @staticmethod
            async def create(**kwargs):
                calls.append(kwargs)

                class Response:
                    content = [type("Block", (), {"text": (
                        '{"greeting": "Hi all!", "people": ['
                        '{"costume": "ghost", "confidence": "high", "shout_out": "Boo!"},'
                        '{"costume": "cat", "confidence": "medium", "shout_out": "Meow!"}]}'
                    )})()]
                return Response()

    identifier._client = Recorder()  # noqa: SLF001
    identified, greetings = await collect(bus)
    await bus.start()
    bus.publish(make_group(kinds=("person", "dog")))
    await eventually(lambda: len(greetings) == 1)

    assert len(calls) == 1
    blocks = calls[0]["messages"][0]["content"]
    assert [b["type"] for b in blocks] == ["text", "image", "text", "image", "text"]
    assert blocks[0]["text"] == "Visitor 1 (person):" and blocks[2]["text"] == "Visitor 2 (dog):"
    assert [e.visitor_type for e in identified] == ["person", "dog"]
    assert [e.costume for e in identified] == ["ghost", "cat"]
    assert greetings[0].text == "Hi all! Boo! Meow!"
    await bus.stop()


# -- what gets spoken (04-F9) ------------------------------------------------

def reading(*shout_outs: str) -> GroupReading:
    return GroupReading("Hello, crew!",
                        tuple(PersonReading("x", "high", s) for s in shout_outs))


def test_lone_visitor_hears_only_the_greeting():
    assert make_identifier(EventBus()).spoken_text(reading("unused")) == "Hello, crew!"


def test_small_group_hears_greeting_then_shout_outs():
    text = make_identifier(EventBus()).spoken_text(reading("Boo!", "Meow!", "Rawr!"))
    assert text == "Hello, crew! Boo! Meow! Rawr!"


def test_big_group_hears_only_the_greeting():
    text = make_identifier(EventBus()).spoken_text(reading("a", "b", "c", "d"))
    assert text == "Hello, crew!"


# -- output parsing ----------------------------------------------------------

def test_parse_group_json():
    result = CostumeIdentifier._parse(
        '{"greeting": "Spooky squad!", "people": ['
        '{"costume": "witch", "confidence": "high", "shout_out": "Nice hat!"},'
        '{"costume": "robot", "confidence": "medium", "shout_out": "Beep!"}]}', count=2)
    assert result.greeting == "Spooky squad!"
    assert [(p.costume, p.shout_out) for p in result.people] == [("witch", "Nice hat!"),
                                                                 ("robot", "Beep!")]


def test_parse_tolerates_surrounding_prose():
    # Models occasionally ignore "JSON only" — seatbelts (see _parse docstring).
    result = CostumeIdentifier._parse(
        'Sure! Here is the JSON:\n{"greeting": "Beep!", "people": '
        '[{"costume": "robot", "confidence": "medium", "shout_out": ""}]}\nHope that helps.')
    assert result.people[0].costume == "robot"


def test_parse_accepts_the_single_visitor_legacy_shape():
    result = CostumeIdentifier._parse(
        '{"costume": "witch", "confidence": "high", "comment": "Nice hat!"}')
    assert result.greeting == "Nice hat!"
    assert result.people[0].costume == "witch"


def test_parse_null_costume_means_no_costume():  # 03-F3
    result = CostumeIdentifier._parse(
        '{"greeting": "Welcome, friend!", "people": [{"costume": null, "confidence": "high"}]}')
    assert result.people[0].costume is None


def test_parse_invalid_confidence_degrades_to_low():
    result = CostumeIdentifier._parse(
        '{"greeting": "Meow.", "people": [{"costume": "cat", "confidence": "very sure!!"}]}')
    assert result.people[0].confidence == "low"


def test_parse_pads_and_trims_people_to_the_group_size():
    short = CostumeIdentifier._parse(
        '{"greeting": "Hi!", "people": [{"costume": "cat", "confidence": "high"}]}', count=3)
    assert [p.costume for p in short.people] == ["cat", "mystery guest", "mystery guest"]
    long = CostumeIdentifier._parse(
        '{"greeting": "Hi!", "people": [{"costume": "a"}, {"costume": "b"}]}', count=1)
    assert len(long.people) == 1


def test_parse_rejects_empty_greeting():
    with pytest.raises(ValueError):
        CostumeIdentifier._parse(
            '{"greeting": "", "people": [{"costume": "cat"}, {"costume": "dog"}]}', count=2)


def test_parse_rejects_non_json():
    with pytest.raises(ValueError):
        CostumeIdentifier._parse("I cannot see an image here.")


async def test_pretend_mode_greets_pets_as_pets():  # 01-F7
    bus = EventBus()
    make_identifier(bus)
    identified, greetings = await collect(bus)
    await bus.start()
    bus.publish(make_group(kinds=("dog",)))
    await drain(bus)
    assert identified[0].visitor_type == "dog"
    assert identified[0].costume in {c for c, *_ in prompts.PRETEND_PETS}
    await bus.stop()


def test_prompt_tells_claude_about_pets():  # 03-F11
    assert "Pets:" in prompts.SYSTEM_PROMPT
    assert prompts.photo_label(2, "cat") == "Visitor 2 (cat):"
    assert prompts.photo_label(1, "") == "Visitor 1:"


def test_parse_keeps_the_clues_claude_saw():  # 03-F12
    result = CostumeIdentifier._parse(
        '{"greeting": "Rawr!", "people": [{"clues": "green onesie with spikes, hood with eyes",'
        ' "costume": "Dinosaur onesie", "confidence": "medium", "shout_out": "Rawr!"}]}')
    assert result.people[0].clues.startswith("green onesie")
    assert result.people[0].costume == "Dinosaur onesie"


def test_prompt_forbids_no_costume_when_costume_pieces_are_visible():  # 03-F12
    text = prompts.SYSTEM_PROMPT
    assert '"clues"' in text  # clues come before the costume in the JSON shape
    assert text.index('"clues"') < text.index('"costume": "short costume name or null"')
    assert "ONLY for everyday clothes" in text and "MUST name a costume" in text


async def test_the_next_call_hears_tonights_costumes():  # 03-F13
    bus = EventBus()
    identifier = make_identifier(bus, api_key="sk-test")
    prompts_sent: list[str] = []

    class Recorder:
        class messages:  # noqa: N801
            @staticmethod
            async def create(**kwargs):
                prompts_sent.append(kwargs["messages"][0]["content"][-1]["text"])

                class Response:
                    content = [type("Block", (), {"text": (
                        '{"greeting": "Hi!", "people": [{"costume": "Vampire",'
                        ' "confidence": "high", "shout_out": "Fangs!"}]}')})()]
                return Response()

    identifier._client = Recorder()  # noqa: SLF001
    _, greetings = await collect(bus)
    await bus.start()
    bus.publish(make_group(1))
    await eventually(lambda: len(greetings) == 1)
    bus.publish(make_group(1))
    await eventually(lambda: len(greetings) == 2)

    assert "already greeted" not in prompts_sent[0]
    assert "Vampire" in prompts_sent[1] and "fresh" in prompts_sent[1]
    await bus.stop()
