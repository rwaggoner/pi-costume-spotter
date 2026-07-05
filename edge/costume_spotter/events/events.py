"""Event and value types that flow across the bus.

These dataclasses ARE the system's internal contract: every component speaks in
these types and nothing else (see the catalogue in docs/architecture.md). They are
frozen so a subscriber can never mutate an event another subscriber also received.

Serialization note: events travel to the React dashboard over a WebSocket.
``as_wire_dict()`` produces that JSON view, and deliberately OMITS raw image
bytes — pixels reach the browser only through the MJPEG stream and the snapshot
REST endpoint, never through the event socket (it would bloat every log message
with base64).
"""

import dataclasses
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned box in pixel coordinates, (x, y) = top-left corner."""

    x: int
    y: int
    width: int
    height: int

    @property
    def area(self) -> int:
        return self.width * self.height

    def iou(self, other: "BoundingBox") -> float:
        """Intersection-over-union: the tracker's measure of 'same person?' (02-F1)."""
        ix = max(self.x, other.x)
        iy = max(self.y, other.y)
        ix2 = min(self.x + self.width, other.x + other.width)
        iy2 = min(self.y + self.height, other.y + other.height)
        inter = max(0, ix2 - ix) * max(0, iy2 - iy)
        union = self.area + other.area - inter
        return inter / union if union > 0 else 0.0


@dataclass(frozen=True)
class Detection:
    """One detector hit in one frame. Plain data — no vendor SDK types (01-F4)."""

    box: BoundingBox
    confidence: float
    label: str = "person"


@dataclass(frozen=True)
class BaseEvent:
    """Common shape for everything on the bus."""

    # kw_only lets subclasses add required fields despite this defaulted one.
    timestamp: datetime = field(default_factory=_utcnow, kw_only=True)

    @property
    def kind(self) -> str:
        """Wire name of the event, e.g. ``CostumeIdentified``."""
        return type(self).__name__

    def as_wire_dict(self) -> dict:
        """JSON-safe view for the dashboard WebSocket. Drops raw bytes (see module docs)."""
        out: dict = {"kind": self.kind}
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            if isinstance(value, bytes):
                continue  # images never ride the event socket
            out[f.name] = _jsonify(value)
        return out


def _jsonify(value):
    """Recursively convert dataclass/datetime values to JSON-friendly types."""
    if isinstance(value, datetime):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _jsonify(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    return value


# --------------------------------------------------------------------------
# The events, in pipeline order.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FrameProcessed(BaseEvent):
    """A camera frame went through detection. High-frequency (~15/s).

    Consumed by the MJPEG streamer (pixels) and the dashboard overlay (boxes).
    Subscribers that can't keep up drop old frames — that's the bus's bounded-queue
    behavior working as intended; video must never back-pressure detection.
    """

    jpeg: bytes
    detections: tuple[Detection, ...]
    fps: float


@dataclass(frozen=True)
class NewVisitorSpotted(BaseEvent):
    """The tracker decided a genuinely new person is here (02-F2). ~One per visitor.

    Carries the cropped snapshot that identification will send to Claude —
    downstream components must not need to reach back into the video pipeline.
    """

    visitor_id: int
    snapshot_jpeg: bytes
    box: BoundingBox


@dataclass(frozen=True)
class CostumeIdentified(BaseEvent):
    """The identifier produced (or fell back to) a costume + comment (03-F5/F6)."""

    sighting_id: str  # UUID, minted here; reused for idempotent cloud ingest (07-F4)
    visitor_id: int
    costume: str | None  # None = person in regular clothes (03-F3)
    confidence: str  # high | medium | low | unknown
    comment: str
    source: str  # claude | pretend | fallback — honesty in the logs
    snapshot_jpeg: bytes
    box: BoundingBox
    detector: str


@dataclass(frozen=True)
class SightingLogged(BaseEvent):
    """Storage persisted the sighting row (+ snapshot file, unless metadata-only)."""

    sighting_id: str
    costume: str | None
    comment: str
    snapshot_file: str | None


@dataclass(frozen=True)
class CommentSpoken(BaseEvent):
    """Speech finished (or failed — ``spoken=False``) saying a comment (04-F6)."""

    sighting_id: str
    text: str
    engine: str
    spoken: bool


@dataclass(frozen=True)
class SystemStatus(BaseEvent):
    """Component heartbeat/health change; feeds /api/health and the dashboard header."""

    component: str  # camera | detector | identifier | speech | storage | cloudsync
    ok: bool
    detail: str = ""
