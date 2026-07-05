"""Mock detector for the dev profile: finds the synthetic scene's visitor by color.

Deliberately NOT a stub returning canned coordinates: it thresholds actual pixels
for the reserved magenta that ``camera/synthetic.py`` paints its visitor with, and
derives a bounding box from the resulting mask. That means the dev pipeline runs
the same code path as production — frames in, boxes out, computed from image
content — so bugs in cropping, box math, or tracking show up on a laptop instead
of on the Pi's porch.
"""

import numpy as np

from costume_spotter.camera.synthetic import VISITOR_COLOR
from costume_spotter.detection.base import Detector
from costume_spotter.events.events import BoundingBox, Detection

# How far a pixel may deviate per channel and still count as "the visitor".
_TOLERANCE = 40
# Blobs smaller than this many pixels are noise, not a person.
_MIN_AREA_PX = 400


class MockDetector(Detector):
    """Color-blob detection tuned to the synthetic scene's visitor."""

    name = "mock"

    def detect(self, frame: np.ndarray) -> list[Detection]:
        target = np.array(VISITOR_COLOR, dtype=np.int16)
        # Per-pixel max channel deviation from the target color.
        diff = np.abs(frame.astype(np.int16) - target).max(axis=2)
        mask = diff < _TOLERANCE
        if int(mask.sum()) < _MIN_AREA_PX:
            return []
        ys, xs = np.nonzero(mask)
        box = BoundingBox(
            x=int(xs.min()),
            y=int(ys.min()),
            width=int(xs.max() - xs.min() + 1),
            height=int(ys.max() - ys.min() + 1),
        )
        # Confidence is how "solidly" the box is filled with visitor pixels —
        # a real (if crude) measure, so threshold plumbing (01-F5) is exercised too.
        fill = float(mask.sum()) / box.area if box.area else 0.0
        return [Detection(box=box, confidence=round(min(0.99, 0.5 + fill / 2), 2))]
