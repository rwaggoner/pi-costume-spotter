"""CostumeIdentifier: pretend mode, output parsing, and the fallback path (03-F6/F7).

The Claude API itself is never called in tests — ``_parse`` is tested directly
with representative model outputs, and the event flow is tested in pretend mode
and with a stubbed client that always fails.
"""

import pytest

from costume_spotter.events import CostumeIdentified, EventBus, NewVisitorSpotted
from costume_spotter.events.events import BoundingBox
from costume_spotter.vision.identifier import CostumeIdentifier
from tests.conftest import drain, eventually


def make_event() -> NewVisitorSpotted:
    return NewVisitorSpotted(visitor_id=1, snapshot_jpeg=b"\xff\xd8fake",
                             box=BoundingBox(10, 10, 40, 80))


async def collect_identified(bus: EventBus) -> list:
    received: list = []

    async def handler(event):
        received.append(event)

    bus.subscribe(handler, to=(CostumeIdentified,), name="test.collector")
    return received


# -- pretend mode (03-F7) ----------------------------------------------------

async def test_pretend_mode_identifies_without_api():
    bus = EventBus()
    identifier = CostumeIdentifier(bus, api_key=None, model="x", timeout_seconds=1,
                                   detector_name="mock")
    received = await collect_identified(bus)
    await bus.start()

    bus.publish(make_event())
    await drain(bus)

    assert identifier.mode == "pretend"
    assert len(received) == 1
    assert received[0].source == "pretend"
    assert received[0].comment  # canned, but present — the pipeline flows
    assert received[0].sighting_id  # UUID minted
    await bus.stop()


async def test_fallback_when_api_is_down():  # 03-F6
    bus = EventBus()
    identifier = CostumeIdentifier(bus, api_key="sk-test", model="x", timeout_seconds=1,
                                   detector_name="mock")

    class AlwaysDown:
        class messages:  # noqa: N801 — mimics the SDK's shape
            @staticmethod
            async def create(**kwargs):
                raise ConnectionError("no internet on the porch")

    identifier._client = AlwaysDown()  # noqa: SLF001 — inject the failure
    received = await collect_identified(bus)
    await bus.start()

    bus.publish(make_event())
    # eventually, not drain: the handler is in-flight (queue empty) for the
    # whole 2s+4s retry backoff (03-F8) before it publishes the fallback.
    await eventually(lambda: len(received) == 1, timeout=30)

    assert len(received) == 1
    assert received[0].source == "fallback"
    assert received[0].costume == "mystery guest"
    await bus.stop()


# -- output parsing ----------------------------------------------------------

def test_parse_clean_json():
    costume, confidence, comment = CostumeIdentifier._parse(
        '{"costume": "witch", "confidence": "high", "comment": "Nice hat!"}'
    )
    assert (costume, confidence, comment) == ("witch", "high", "Nice hat!")


def test_parse_tolerates_surrounding_prose():
    # Models occasionally ignore "JSON only" — seatbelts (see _parse docstring).
    costume, _, _ = CostumeIdentifier._parse(
        'Sure! Here is the JSON:\n{"costume": "robot", "confidence": "medium", '
        '"comment": "Beep!"}\nHope that helps.'
    )
    assert costume == "robot"


def test_parse_null_costume_means_no_costume():  # 03-F3
    costume, _, comment = CostumeIdentifier._parse(
        '{"costume": null, "confidence": "high", "comment": "Welcome, friend!"}'
    )
    assert costume is None
    assert comment == "Welcome, friend!"


def test_parse_invalid_confidence_degrades_to_low():
    _, confidence, _ = CostumeIdentifier._parse(
        '{"costume": "cat", "confidence": "very sure!!", "comment": "Meow."}'
    )
    assert confidence == "low"


def test_parse_rejects_empty_comment():
    with pytest.raises(ValueError):
        CostumeIdentifier._parse('{"costume": "cat", "confidence": "high", "comment": ""}')


def test_parse_rejects_non_json():
    with pytest.raises(ValueError):
        CostumeIdentifier._parse("I cannot see an image here.")
