"""Shared test helpers.

The recurring pattern in these tests: build a bus, wire the subscriber under
test, publish synthetic events, ``drain`` until the bus is quiet, then assert.
No hardware, no network, no clock dependencies anywhere (02-N3 and friends).
"""

import asyncio

import numpy as np
import pytest

from costume_spotter.events import EventBus
from costume_spotter.events.events import BoundingBox, Detection


async def drain(bus: EventBus, timeout: float = 5.0) -> None:
    """Wait until every subscriber queue is empty and handlers have run."""
    async def _quiet() -> None:
        while any(s["queued"] for s in bus.stats()):
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)  # let in-flight handlers finish their last event

    await asyncio.wait_for(_quiet(), timeout)


async def eventually(condition, timeout: float = 10.0) -> None:
    """Poll until ``condition()`` is true. For asserting on slow handlers —
    ``drain`` can't see an in-flight handler (its queue is already empty)."""
    async def _poll() -> None:
        while not condition():
            await asyncio.sleep(0.02)

    await asyncio.wait_for(_poll(), timeout)


@pytest.fixture
async def bus():
    b = EventBus()
    # Tests wire their subscribers, then call started_bus() to start consumers.
    yield b
    if b._started:  # noqa: SLF001 — test teardown may peek
        await b.stop()


def frame(width: int = 320, height: int = 240) -> np.ndarray:
    """A blank RGB frame."""
    return np.zeros((height, width, 3), dtype=np.uint8)


def detection(x: int, y: int, w: int = 40, h: int = 80, confidence: float = 0.9) -> Detection:
    return Detection(box=BoundingBox(x, y, w, h), confidence=confidence)
