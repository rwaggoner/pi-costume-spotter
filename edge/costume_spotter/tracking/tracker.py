"""Greedy IoU visitor tracker.

The gatekeeper between cheap detection and expensive reaction: every event this
module emits triggers a Claude API call, a DB write, and speech — so the logic
here implements requirements 02 exactly (see the decision flowchart in
docs/architecture.md#is-this-a-new-visitor-decision-flow).

Why not SORT/Kalman? At porch scale (a handful of slow-moving people) greedy IoU
matching performs comparably and stays ~100 lines of dependency-free code —
the trade-off is argued in docs/requirements/02-tracking.md.

Design for testability (02-N3): this class is synchronous, does no I/O, and takes
``now`` as a parameter — tests drive it with scripted boxes and a fake clock.
"""

from dataclasses import dataclass, field

import numpy as np

from costume_spotter import imaging
from costume_spotter.events.events import BoundingBox, Detection


@dataclass
class _TrackedVisitor:
    """Internal per-person state. Never leaves this module."""

    visitor_id: int
    box: BoundingBox
    last_seen: float
    consecutive_hits: int = 1
    announced: bool = False
    # Best snapshot so far = the frame where they appeared largest (≈ closest,
    # most visible — 02-F5). Kept only until announcement, then freed.
    best_crop: np.ndarray | None = None
    best_area: int = 0


@dataclass(frozen=True)
class NewVisitor:
    """The tracker's output when someone crosses the announcement threshold."""

    visitor_id: int
    box: BoundingBox
    snapshot: np.ndarray  # RGB crop; the pipeline JPEG-encodes it


@dataclass
class VisitorTracker:
    """Matches detections across frames; announces each visitor exactly once (02-F2)."""

    iou_threshold: float = 0.3  # 02-F1: minimum overlap to be "the same person"
    min_hits: int = 5           # 02-F3: consecutive frames before announcing
    retire_seconds: float = 30.0  # 02-F4: absence before the visitor is forgotten

    _visitors: dict[int, _TrackedVisitor] = field(default_factory=dict)
    _next_id: int = 1  # session-scoped, resets on restart — deliberate (05-N2)

    def update(self, detections: list[Detection], frame: np.ndarray,
               now: float) -> list[NewVisitor]:
        """Process one frame's detections; return any visitors newly crossing the threshold."""
        self._retire_stale(now)
        announced: list[NewVisitor] = []

        # Greedy matching: pair the highest-IoU (visitor, detection) combinations
        # first. With ≤ a few people in frame this is effectively optimal.
        unmatched = list(detections)
        pairs = sorted(
            ((v.box.iou(d.box), v, d) for v in self._visitors.values() for d in unmatched),
            key=lambda t: t[0],
            reverse=True,
        )
        matched_visitors: set[int] = set()
        for iou, visitor, det in pairs:
            if iou < self.iou_threshold:
                break  # sorted descending — everything after is worse
            # Identity (not ==) check: two equal boxes must still be two detections.
            if visitor.visitor_id in matched_visitors or not any(d is det for d in unmatched):
                continue  # visitor or detection already claimed this frame
            unmatched = [d for d in unmatched if d is not det]
            matched_visitors.add(visitor.visitor_id)
            self._advance(visitor, det, frame, now)
            if self._just_became_announceable(visitor):
                announced.append(self._announce(visitor))

        # "Consecutive" means consecutive (02-F3): a candidate that skipped a frame
        # starts its stability count over. Announced visitors keep their identity
        # through brief occlusions — only the retire timeout forgets them.
        for visitor in self._visitors.values():
            if visitor.visitor_id not in matched_visitors and not visitor.announced:
                visitor.consecutive_hits = 0

        # Anything left unmatched starts life as a 1-hit candidate. A YOLO
        # flicker on a shadow dies here quietly, min_hits frames short of an event.
        for det in unmatched:
            v = _TrackedVisitor(self._next_id, det.box, now)
            self._remember_best_crop(v, det.box, frame)
            self._visitors[self._next_id] = v
            self._next_id += 1

        return announced

    # -- internals -----------------------------------------------------------

    def _advance(self, v: _TrackedVisitor, det: Detection, frame: np.ndarray, now: float) -> None:
        v.box = det.box
        v.last_seen = now
        v.consecutive_hits += 1
        if not v.announced:
            self._remember_best_crop(v, det.box, frame)

    def _remember_best_crop(self, v: _TrackedVisitor, box: BoundingBox, frame: np.ndarray) -> None:
        if box.area > v.best_area:
            v.best_area = box.area
            v.best_crop = imaging.crop_box(frame, box).copy()

    def _just_became_announceable(self, v: _TrackedVisitor) -> bool:
        return not v.announced and v.consecutive_hits >= self.min_hits

    def _announce(self, v: _TrackedVisitor) -> NewVisitor:
        v.announced = True
        assert v.best_crop is not None  # set on first sighting, by construction
        out = NewVisitor(v.visitor_id, v.box, v.best_crop)
        v.best_crop = None  # free the pixels; only the box is needed from here on
        return out

    def _retire_stale(self, now: float) -> None:
        """Drop visitors unseen for retire_seconds — bounds memory (02-N2) and
        lets a returning visitor be greeted again (02-F4)."""
        stale = [vid for vid, v in self._visitors.items()
                 if now - v.last_seen > self.retire_seconds]
        for vid in stale:
            del self._visitors[vid]

    @property
    def active_boxes(self) -> list[BoundingBox]:
        """Current visitor boxes, for anyone who wants a system snapshot (e.g. debugging)."""
        return [v.box for v in self._visitors.values()]
