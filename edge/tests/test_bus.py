"""EventBus behavior: routing, back-pressure shedding, and failure isolation.

These are the three promises bus.py makes in its module docstring — each gets a test.
"""

import pytest

from costume_spotter.events import EventBus, SystemStatus
from costume_spotter.events.events import CommentSpoken
from tests.conftest import drain


def collector(into: list):
    """An async handler that appends every event it receives to ``into``."""
    async def handler(event):
        into.append(event)
    return handler


async def test_routes_by_event_type():
    bus = EventBus()
    received = []
    bus.subscribe(collector(received), to=(SystemStatus,), name="t")
    await bus.start()

    bus.publish(SystemStatus(component="camera", ok=True))
    bus.publish(CommentSpoken(sighting_id="x", text="hi", engine="null", spoken=True))
    await drain(bus)

    assert [e.kind for e in received] == ["SystemStatus"]
    await bus.stop()


async def test_wildcard_subscription_sees_everything():
    bus = EventBus()
    received = []
    bus.subscribe(collector(received), to=None, name="t")
    await bus.start()

    bus.publish(SystemStatus(component="camera", ok=True))
    bus.publish(CommentSpoken(sighting_id="x", text="hi", engine="null", spoken=True))
    await drain(bus)

    assert len(received) == 2
    await bus.stop()


async def test_full_queue_sheds_oldest():
    """Freshness over completeness: with queue_size=2, publishing 1..5 before the
    consumer runs must deliver the newest two (4, 5) — not the oldest."""
    bus = EventBus()
    received = []
    bus.subscribe(collector(received), to=(SystemStatus,), name="t", queue_size=2)

    for i in range(1, 6):  # published before start() → nothing consumed yet
        bus.publish(SystemStatus(component=str(i), ok=True))
    await bus.start()
    await drain(bus)

    assert [e.component for e in received] == ["4", "5"]
    assert bus.stats()[0]["dropped"] == 3
    await bus.stop()


async def test_crashing_handler_does_not_stop_delivery():
    bus = EventBus()
    received = []

    async def explodes(event):
        raise RuntimeError("boom")

    bus.subscribe(explodes, to=(SystemStatus,), name="bad")
    bus.subscribe(collector(received), to=(SystemStatus,), name="good")
    await bus.start()

    bus.publish(SystemStatus(component="a", ok=True))
    bus.publish(SystemStatus(component="b", ok=True))
    await drain(bus)

    # The bad handler failed twice; the good one — and the bus — never noticed.
    assert [e.component for e in received] == ["a", "b"]
    await bus.stop()


async def test_subscribe_after_start_is_rejected():
    bus = EventBus()
    await bus.start()
    with pytest.raises(RuntimeError):
        bus.subscribe(collector([]), name="late")
    await bus.stop()
