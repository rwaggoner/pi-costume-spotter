"""Shared live state for the API layer, fed by bus subscriptions.

The API needs two things the bus can't answer retroactively: "what's the latest
frame?" (for MJPEG connections that join mid-stream) and "what's the current
health of each component?". This module holds both, updated by subscribers wired
in app.py. It's the read-side cache of the event stream — nothing here is the
source of truth.
"""

import asyncio
from datetime import UTC, datetime

from costume_spotter.events.events import FrameProcessed, SystemStatus


class LatestFrame:
    """Holds the newest JPEG; MJPEG connections await each arrival.

    An asyncio.Condition (not a queue) because every viewer should get the SAME
    latest frame — late viewers must not consume frames out from under others.
    """

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._jpeg: bytes | None = None
        self.fps: float = 0.0

    async def update(self, event) -> None:
        assert isinstance(event, FrameProcessed)
        async with self._condition:
            self._jpeg = event.jpeg
            self.fps = event.fps
            self._condition.notify_all()

    async def next_frame(self) -> bytes:
        """Block until a frame newer than 'now' arrives, then return it."""
        async with self._condition:
            await self._condition.wait()
            assert self._jpeg is not None
            return self._jpeg


class HealthRegistry:
    """Latest SystemStatus per component, for /api/health and the dashboard header."""

    def __init__(self) -> None:
        self._components: dict[str, dict] = {}

    async def update(self, event) -> None:
        assert isinstance(event, SystemStatus)
        self._components[event.component] = {
            "ok": event.ok,
            "detail": event.detail,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    def snapshot(self) -> dict[str, dict]:
        return dict(self._components)
