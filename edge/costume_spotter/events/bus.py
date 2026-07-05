"""A small asyncio publish/subscribe event bus.

This ~100-line class is the spine of the whole edge application
(docs/decisions/003-event-bus.md). Design goals, in priority order:

1. **A slow subscriber must never stall a fast publisher.** The camera loop
   publishes ~15 events/second; the Claude API subscriber takes seconds per event.
   So every subscription gets its own bounded ``asyncio.Queue`` and its own
   consumer task. ``publish()`` only enqueues — it never awaits a handler.

2. **A full queue drops the OLDEST item, not the newest.** For this system's
   events, fresh beats complete: an MJPEG viewer wants the latest frame, not a
   backlog. (Subscribers that must not miss events — e.g. the sighting logger —
   simply size their queue above any realistic burst.)

3. **A crashing handler must not take down the bus.** Each delivery is wrapped;
   failures are logged and the consumer keeps consuming.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from costume_spotter.events.events import BaseEvent

logger = logging.getLogger(__name__)

# A handler is any async function taking the event. Type alias for readability.
Handler = Callable[[BaseEvent], Awaitable[None]]


class _Subscription:
    """One subscriber's queue + the metadata needed to route and debug it."""

    def __init__(self, name: str, event_types: tuple[type[BaseEvent], ...] | None,
                 handler: Handler, queue_size: int) -> None:
        self.name = name
        self.event_types = event_types  # None means "wildcard: everything"
        self.handler = handler
        self.queue: asyncio.Queue[BaseEvent] = asyncio.Queue(maxsize=queue_size)
        self.dropped = 0  # count of events shed under back-pressure, for /api/health

    def wants(self, event: BaseEvent) -> bool:
        return self.event_types is None or isinstance(event, self.event_types)


class EventBus:
    """In-process pub/sub. Create one, share it everywhere, ``start()`` it once."""

    def __init__(self) -> None:
        self._subscriptions: list[_Subscription] = []
        self._tasks: list[asyncio.Task] = []
        self._started = False

    def subscribe(
        self,
        handler: Handler,
        *,
        to: tuple[type[BaseEvent], ...] | None = None,
        name: str | None = None,
        queue_size: int = 64,
    ) -> None:
        """Register ``handler`` for events of the types in ``to`` (or all, if None).

        Must be called before ``start()`` — the subscriber set is fixed at startup,
        which keeps the wiring auditable in one place (main.py, the composition root).
        """
        if self._started:
            raise RuntimeError("subscribe() after start(); wire all subscribers in main.py")
        sub = _Subscription(name or handler.__qualname__, to, handler, queue_size)
        self._subscriptions.append(sub)

    def publish(self, event: BaseEvent) -> None:
        """Fan the event out to every interested subscriber's queue. Never blocks.

        Synchronous on purpose: publishers (like the frame pipeline) call this from
        tight loops and must not yield to arbitrary handler code mid-frame.
        """
        for sub in self._subscriptions:
            if not sub.wants(event):
                continue
            if sub.queue.full():
                # Shed the oldest: freshness beats completeness here (see module docs).
                sub.queue.get_nowait()
                sub.dropped += 1
            sub.queue.put_nowait(event)

    async def start(self) -> None:
        """Spawn one consumer task per subscription."""
        self._started = True
        for sub in self._subscriptions:
            self._tasks.append(asyncio.create_task(self._consume(sub), name=f"bus:{sub.name}"))
        logger.info("event bus started with %d subscribers", len(self._subscriptions))

    async def stop(self) -> None:
        """Cancel consumers; used by the app's lifespan shutdown and by tests."""
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._started = False

    async def _consume(self, sub: _Subscription) -> None:
        while True:
            event = await sub.queue.get()
            try:
                await sub.handler(event)
            except Exception:  # noqa: BLE001 — isolation is the point (goal #3)
                logger.exception("subscriber %r failed handling %s", sub.name, event.kind)

    def stats(self) -> list[dict]:
        """Queue depth / drop counts per subscriber, surfaced at /api/health."""
        return [
            {"subscriber": s.name, "queued": s.queue.qsize(), "dropped": s.dropped}
            for s in self._subscriptions
        ]
