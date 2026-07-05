"""The sighting-logger subscriber: CostumeIdentified → row + snapshot → SightingLogged.

One of the five independent reactions to a sighting (docs/architecture.md sequence
diagram). It only knows the bus and the storage layer — nothing about cameras,
Claude, or speech.
"""

import asyncio
import logging

from costume_spotter.events import (
    CommentSpoken,
    CostumeIdentified,
    EventBus,
    SightingLogged,
    SystemStatus,
)
from costume_spotter.events.events import BaseEvent
from costume_spotter.storage.repository import SightingRepository
from costume_spotter.storage.snapshots import SnapshotStore

logger = logging.getLogger(__name__)


class SightingLogger:
    """Persists each identified sighting; publishes SightingLogged when done."""

    def __init__(self, bus: EventBus, repository: SightingRepository,
                 snapshots: SnapshotStore) -> None:
        self._bus = bus
        self._repository = repository
        self._snapshots = snapshots
        # Generous queue: unlike video frames, sightings must not be shed —
        # a burst of 256 simultaneous trick-or-treaters would be a good problem.
        bus.subscribe(self.on_costume_identified, to=(CostumeIdentified,),
                      name="storage.sighting_logger", queue_size=256)
        bus.subscribe(self.on_comment_spoken, to=(CommentSpoken,),
                      name="storage.spoken_marker", queue_size=256)

    async def on_costume_identified(self, event: BaseEvent) -> None:
        assert isinstance(event, CostumeIdentified)
        try:
            # File + DB writes are synchronous; run off the loop (05-N4).
            snapshot_file = await asyncio.to_thread(
                self._snapshots.save, event.sighting_id, event.snapshot_jpeg
            )
            await asyncio.to_thread(
                self._repository.add,
                sighting_id=event.sighting_id,
                # SQLite stores naive datetimes; we standardize on naive-UTC in rows.
                spotted_at=event.timestamp.replace(tzinfo=None),
                costume=event.costume,
                confidence=event.confidence,
                comment=event.comment,
                spoken=False,  # speech reports back later via mark_spoken
                snapshot_file=snapshot_file,
                detector=event.detector,
                box=event.box.__dict__,
                source=event.source,
            )
        except Exception:
            logger.exception("failed to persist sighting %s", event.sighting_id)
            self._bus.publish(SystemStatus(component="storage", ok=False, detail="write failed"))
            return
        self._bus.publish(SightingLogged(
            sighting_id=event.sighting_id, costume=event.costume,
            comment=event.comment, snapshot_file=snapshot_file,
        ))

    async def on_comment_spoken(self, event: BaseEvent) -> None:
        """Flip the row's ``spoken`` flag once speech confirms playback.

        Speech takes seconds while the row write takes milliseconds, so the row
        reliably exists by the time this fires; if it somehow doesn't,
        mark_spoken is a silent no-op and the flag just stays false.
        """
        assert isinstance(event, CommentSpoken)
        if event.spoken:
            await asyncio.to_thread(self._repository.mark_spoken, event.sighting_id)

    async def prune_forever(self, interval_seconds: float = 86_400) -> None:
        """Retention job (05-F3): prune at startup, then daily. Run as an asyncio task."""
        while True:
            days = self._snapshots.retention_days
            if days > 0:
                await asyncio.to_thread(self._snapshots.prune)
                await asyncio.to_thread(self._repository.prune_older_than, days)
            await asyncio.sleep(interval_seconds)
