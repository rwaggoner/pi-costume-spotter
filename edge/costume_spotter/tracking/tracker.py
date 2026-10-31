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

import logging
from dataclasses import dataclass, field

import numpy as np

from costume_spotter import imaging
from costume_spotter.events.events import BoundingBox, Detection

logger = logging.getLogger(__name__)

# Re-greet guard (02-F9). A "new" visitor is really someone already greeted
# when they look alike (colour signature) and either reappear close to where
# they were lost, soon after, or look very alike within the cooldown.
_SOON_SECONDS = 5.0
_ALIKE_NEARBY = 0.55  # histogram intersection, 0-1
_ALIKE_ANYWHERE = 0.85


@dataclass
class _TrackedVisitor:
    """Internal per-person state. Never leaves this module."""

    visitor_id: int
    box: BoundingBox
    last_seen: float
    label: str = "person"  # person | dog | cat (01-F7)
    consecutive_hits: int = 1
    # Frames missed since the last hit. A detector blinks on capes, masks and
    # odd poses; a candidate survives up to max_misses blinks before its count
    # restarts (02-F3).
    misses: int = 0
    announced: bool = False
    # Best snapshot so far (02-F5): the frame scoring highest on size (≈ closest)
    # times sharpness (not blurred mid-stride). Plus the FIRST sighting, so the
    # identifier gets more than one look (02-F8). Kept only until announcement.
    best_crop: np.ndarray | None = None
    best_score: float = -1.0
    best_frame: int = 0  # which sighting produced best_crop, for de-duplication
    first_crop: np.ndarray | None = None
    frames_seen: int = 0
    first_seen: float = 0.0
    first_box: BoundingBox | None = None
    signature: np.ndarray | None = None  # colour signature, set when announced (02-F9)


@dataclass(frozen=True)
class NewVisitor:
    """The tracker's output when someone crosses the announcement threshold."""

    visitor_id: int
    box: BoundingBox
    snapshot: np.ndarray  # primary RGB crop (best); the pipeline JPEG-encodes it
    visitor_type: str = "person"  # person | dog | cat
    # Up to two more distinct moments of the same visitor (02-F8), for the
    # identifier only; storage keeps just the primary.
    extra_snapshots: tuple[np.ndarray, ...] = ()


@dataclass
class VisitorTracker:
    """Matches detections across frames; announces each visitor exactly once (02-F2)."""

    iou_threshold: float = 0.3  # 02-F1: minimum overlap to be "the same person"
    min_hits: int = 3           # 02-F3: frames a person must be seen before announcing
    max_misses: int = 2         # 02-F3: missed frames tolerated while building those hits
    max_snapshots: int = 3      # 02-F8: photos per visitor (best + other moments); 1 = best only
    retire_seconds: float = 30.0  # 02-F4: absence before the visitor is forgotten
    # 02-F9: someone already greeted who "reappears" within this many seconds
    # (lost behind a door, bent over the candy bowl, detector blinked) is
    # recognised and not greeted again. 0 = off.
    regreet_seconds: float = 60.0

    _visitors: dict[int, _TrackedVisitor] = field(default_factory=dict)
    # Greeted visitors that were retired, kept for the re-greet guard (02-F9).
    _greeted: list[_TrackedVisitor] = field(default_factory=list)
    _next_id: int = 1  # session-scoped, resets on restart — deliberate (05-N2)

    def update(self, detections: list[Detection], frame: np.ndarray,
               now: float) -> list[NewVisitor]:
        """Process one frame's detections; return any visitors newly crossing the threshold."""
        self._retire_stale(now)
        announced: list[NewVisitor] = []

        # Greedy matching: pair the highest-IoU (visitor, detection) combinations
        # first. With ≤ a few people in frame this is effectively optimal.
        unmatched = list(detections)
        # Only same-kind pairs: a dog at a kid's feet overlaps the kid's box,
        # and must never be mistaken for the kid (or vice versa).
        pairs = sorted(
            ((v.box.iou(d.box), v, d) for v in self._visitors.values() for d in unmatched
             if v.label == d.label),
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
                previous = self._seen_before(visitor, det, frame, now, matched_visitors)
                if previous is not None:
                    self._merge(previous, visitor, det, now)
                    matched_visitors.add(previous.visitor_id)
                else:
                    announced.append(self._announce(visitor, det, frame))

        # Stability with tolerance (02-F3): a candidate may miss up to max_misses
        # frames in a row and keep its count; one more and it starts over. A
        # one-frame detector blink no longer costs a whole restart, which was the
        # main source of slow greetings for costumes YOLO finds unevenly.
        # Announced visitors keep their identity through occlusions — only the
        # retire timeout forgets them.
        for visitor in self._visitors.values():
            if visitor.visitor_id not in matched_visitors and not visitor.announced:
                visitor.misses += 1
                if visitor.misses > self.max_misses:
                    visitor.consecutive_hits = 0

        # Anything left unmatched starts life as a 1-hit candidate. A YOLO
        # flicker on a shadow dies here quietly, min_hits frames short of an event.
        for det in unmatched:
            v = _TrackedVisitor(self._next_id, det.box, now, label=det.label,
                                first_seen=now, first_box=det.box)
            self._remember_best_crop(v, det.box, frame)
            self._visitors[self._next_id] = v
            self._next_id += 1

        return announced

    # -- internals -----------------------------------------------------------

    def _advance(self, v: _TrackedVisitor, det: Detection, frame: np.ndarray, now: float) -> None:
        v.box = det.box
        v.last_seen = now
        v.misses = 0
        v.consecutive_hits += 1
        if not v.announced:
            self._remember_best_crop(v, det.box, frame)

    def _remember_best_crop(self, v: _TrackedVisitor, box: BoundingBox, frame: np.ndarray) -> None:
        """Keep the crop most likely to be identified correctly (02-F5).

        Bigger is better (closer, more detail) and sharper is better (a blurred
        mid-stride frame hides the very details that name a costume). sqrt
        softens sharpness so it breaks near-ties in size rather than dominating:
        a crop 4x blurrier must be 2x bigger to win.
        """
        crop = imaging.crop_box(frame, box)
        v.frames_seen += 1
        if v.first_crop is None:
            v.first_crop = crop.copy()
        score = box.area * (imaging.sharpness(crop) + 1.0) ** 0.5
        if score > v.best_score:
            v.best_score = score
            v.best_crop = crop.copy()
            v.best_frame = v.frames_seen

    def _seen_before(self, candidate: _TrackedVisitor, det: Detection, frame: np.ndarray,
                     now: float, matched: set[int]) -> "_TrackedVisitor | None":
        """An already-greeted visitor this candidate is probably the same person
        as (02-F9), or None. Only greeted visitors NOT seen in this frame count:
        two lookalike vampires standing side by side are two visitors."""
        if self.regreet_seconds <= 0:
            return None
        signature = _signature(frame, det.box)
        best, best_alike = None, 0.0
        for old in [*self._visitors.values(), *self._greeted]:
            if (not old.announced or old.label != candidate.label
                    or old.visitor_id in matched or old.visitor_id == candidate.visitor_id
                    or old.signature is None or now - old.last_seen > self.regreet_seconds):
                continue
            alike = float(np.minimum(signature, old.signature).sum())
            gone = candidate.first_seen - old.last_seen
            nearby = _close(old.box, candidate.first_box or det.box)
            if (alike >= _ALIKE_ANYWHERE
                    or (alike >= _ALIKE_NEARBY and nearby and gone <= _SOON_SECONDS)):
                if alike > best_alike:
                    best, best_alike = old, alike
        if best is not None:
            gone = max(0.0, candidate.first_seen - best.last_seen)
            logger.info("%s #%d looks like #%d again (%.2f alike, gone %.1f s) - not "
                        "greeting twice", candidate.label, candidate.visitor_id,
                        best.visitor_id, best_alike, gone)
        return best

    def _merge(self, old: _TrackedVisitor, candidate: _TrackedVisitor, det: Detection,
               now: float) -> None:
        """The candidate was the greeted visitor all along: keep the old identity."""
        del self._visitors[candidate.visitor_id]
        if old in self._greeted:
            self._greeted.remove(old)
        old.box, old.last_seen, old.misses = det.box, now, 0
        self._visitors[old.visitor_id] = old

    def _just_became_announceable(self, v: _TrackedVisitor) -> bool:
        return not v.announced and v.consecutive_hits >= self.min_hits

    def _announce(self, v: _TrackedVisitor, det: Detection, frame: np.ndarray) -> NewVisitor:
        """Announce with the best crop first, then up to two other distinct
        moments: the announcement frame and the first sighting (02-F8). One
        blurred or half-turned frame no longer sinks the identification."""
        v.announced = True
        v.signature = _signature(frame, det.box)
        assert v.best_crop is not None and v.first_crop is not None  # set at first sighting
        # De-duplicate by sighting number: the best crop may BE the latest or first.
        by_frame: dict[int, np.ndarray] = {v.best_frame: v.best_crop}
        by_frame.setdefault(v.frames_seen, imaging.crop_box(frame, det.box).copy())
        by_frame.setdefault(1, v.first_crop)
        primary, *extras = by_frame.values()
        out = NewVisitor(v.visitor_id, v.box, primary, visitor_type=v.label,
                         extra_snapshots=tuple(extras[:max(0, self.max_snapshots - 1)]))
        v.best_crop = v.first_crop = None  # free the pixels; only the box is needed now
        return out

    def _retire_stale(self, now: float) -> None:
        """Drop visitors unseen for retire_seconds — bounds memory (02-N2) and
        lets a returning visitor be greeted again (02-F4)."""
        stale = [vid for vid, v in self._visitors.items()
                 if now - v.last_seen > self.retire_seconds]
        for vid in stale:
            visitor = self._visitors.pop(vid)
            if visitor.announced and self.regreet_seconds > self.retire_seconds:
                self._greeted.append(visitor)  # remembered a while longer (02-F9)
        self._greeted = [v for v in self._greeted
                         if now - v.last_seen <= self.regreet_seconds]

    def pending_count(self) -> int:
        """People in view right now who are on their way to being announced.

        The group assembler (grouping.py) waits for these before closing a group,
        so friends arriving a step apart are greeted together. Counts only
        candidates seen in the latest frame with at least 2 hits — a single-frame
        blink on a shadow must not hold a group open.
        """
        return sum(1 for v in self._visitors.values()
                   if not v.announced and v.misses == 0 and v.consecutive_hits >= 2)

    @property
    def active_boxes(self) -> list[BoundingBox]:
        """Current visitor boxes, for anyone who wants a system snapshot (e.g. debugging)."""
        return [v.box for v in self._visitors.values()]


def _signature(frame: np.ndarray, box: BoundingBox) -> np.ndarray:
    """A visitor's colour signature: a 64-bin RGB histogram (sums to 1) of the
    middle of their box, which is mostly costume rather than background."""
    crop = imaging.crop_box(frame, box, pad_fraction=0.0)
    h, w = crop.shape[:2]
    core = crop[int(h * 0.1):max(int(h * 0.9), 1), int(w * 0.2):max(int(w * 0.8), 1)]
    if core.size == 0:
        core = crop
    bins = (core[..., :3].reshape(-1, 3) // 64).astype(np.int32)
    hist = np.bincount(bins[:, 0] * 16 + bins[:, 1] * 4 + bins[:, 2], minlength=64)
    return hist / max(hist.sum(), 1)


def _close(a: BoundingBox, b: BoundingBox) -> bool:
    """Centres within one body-height of each other."""
    ax, ay = a.x + a.width / 2, a.y + a.height / 2
    bx, by = b.x + b.width / 2, b.y + b.height / 2
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 <= max(a.height, b.height)
