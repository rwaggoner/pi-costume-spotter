"""Publishes each sighting to GCP Pub/Sub for the cloud tier (07-F1/F2).

Privacy note, enforced here in code: the message is built from an explicit
allow-list of TEXT fields. ``snapshot_jpeg`` exists on the event but can never
leak into the payload because nothing here references it (05-N1).

Failure philosophy (07-F2): the Pub/Sub client library retries internally with
backoff; if a publish still fails, we log it and move on. The cloud tier is an
enhancement — a porch with no internet keeps working, and SQLite still has the
sighting.
"""

import asyncio
import json
import logging

from costume_spotter.events import CostumeIdentified, EventBus, SystemStatus
from costume_spotter.events.events import BaseEvent

logger = logging.getLogger(__name__)


class PubSubPublisher:
    """CostumeIdentified → JSON message on the sightings topic."""

    def __init__(self, bus: EventBus, *, project_id: str | None, topic: str,
                 device_id: str) -> None:
        if not project_id:
            raise ValueError("CLOUD_SYNC_ENABLED=true requires GCP_PROJECT_ID")
        try:
            from google.cloud import pubsub_v1
        except ImportError as exc:
            raise RuntimeError(
                "cloud sync needs the gcp extra: pip install -e \".[gcp]\""
            ) from exc
        self._bus = bus
        self._device_id = device_id
        self._publisher = pubsub_v1.PublisherClient()
        self._topic_path = self._publisher.topic_path(project_id, topic)
        bus.subscribe(self.on_costume_identified, to=(CostumeIdentified,),
                      name="cloudsync.publisher", queue_size=256)

    async def on_costume_identified(self, event: BaseEvent) -> None:
        assert isinstance(event, CostumeIdentified)
        # Allow-list serialization: text metadata only, never pixels (05-N1).
        payload = json.dumps({
            "id": event.sighting_id,
            "spotted_at": event.timestamp.isoformat(),
            "costume": event.costume,
            "confidence": event.confidence,
            "comment": event.comment,
            "device_id": self._device_id,
        }).encode("utf-8")
        try:
            # publish() returns a concurrent future; .result() blocks through the
            # client's internal retries — so it runs in a worker thread.
            future = self._publisher.publish(self._topic_path, payload)
            await asyncio.to_thread(future.result, 30)
            self._bus.publish(SystemStatus(component="cloudsync", ok=True))
        except Exception as exc:
            logger.warning("pub/sub publish failed for %s: %s (sighting is still in "
                           "the local DB)", event.sighting_id, exc)
            self._bus.publish(SystemStatus(component="cloudsync", ok=False, detail=str(exc)))
