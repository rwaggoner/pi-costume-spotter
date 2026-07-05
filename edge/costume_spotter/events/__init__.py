"""The event-driven core: event types and the asyncio pub/sub bus.

Why events instead of direct calls is the subject of
docs/decisions/003-event-bus.md; the catalogue of who publishes/consumes what
is in docs/architecture.md#event-catalogue.
"""

from costume_spotter.events.bus import EventBus
from costume_spotter.events.events import (
    BaseEvent,
    BoundingBox,
    CommentSpoken,
    CostumeIdentified,
    Detection,
    FrameProcessed,
    NewVisitorSpotted,
    SightingLogged,
    SystemStatus,
)

__all__ = [
    "BaseEvent",
    "BoundingBox",
    "CommentSpoken",
    "CostumeIdentified",
    "Detection",
    "EventBus",
    "FrameProcessed",
    "NewVisitorSpotted",
    "SightingLogged",
    "SystemStatus",
]
