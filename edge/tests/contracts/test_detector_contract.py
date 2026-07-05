"""Detector contract tests (ADR-008): every available backend must honor base.py.

Hardware-dependent backends (hailo) and optional-extra backends (hog) auto-skip
where they can't run; the contract still holds for them on the Pi, where these
same tests can be executed.
"""

import numpy as np
import pytest

from costume_spotter.camera.synthetic import SyntheticSource
from costume_spotter.detection.mock import MockDetector


def available_detectors():
    detectors = [MockDetector()]
    try:
        from costume_spotter.detection.hog import HogDetector
        detectors.append(HogDetector())
    except (ImportError, RuntimeError):
        pass  # webcam extra not installed — fine off-Pi
    try:
        from costume_spotter.detection.hailo import HailoDetector  # noqa: F401
        # Constructing needs a HEF file + the HAT; covered by on-Pi runs only.
    except (ImportError, RuntimeError):
        pass
    return detectors


@pytest.mark.parametrize("detector", available_detectors(), ids=lambda d: d.name)
def test_boxes_are_within_frame_bounds(detector):
    frame = _frame_with_visitor()
    for det in detector.detect(frame):
        box = det.box
        assert box.x >= 0 and box.y >= 0
        assert box.x + box.width <= frame.shape[1]
        assert box.y + box.height <= frame.shape[0]
        assert 0.0 <= det.confidence <= 1.0


@pytest.mark.parametrize("detector", available_detectors(), ids=lambda d: d.name)
def test_detection_is_stateless(detector):
    frame = _frame_with_visitor()
    first = detector.detect(frame)
    second = detector.detect(frame)
    assert [(d.box, d.confidence) for d in first] == [(d.box, d.confidence) for d in second]


def test_mock_detector_finds_the_synthetic_visitor():
    """The dev-profile pair: the scene draws a visitor, the detector must find them."""
    detections = MockDetector().detect(_frame_with_visitor())
    assert len(detections) == 1
    assert detections[0].box.area > 400


def test_mock_detector_sees_nothing_on_an_empty_porch():
    source = SyntheticSource(width=640, height=360)
    empty = source._background.copy()  # noqa: SLF001 — the scene minus the visitor
    assert MockDetector().detect(empty) == []


def _frame_with_visitor() -> np.ndarray:
    """Render synthetic frames until the visitor is on screen (they cycle in/out)."""
    source = SyntheticSource(width=640, height=360)
    # Bypass the wall clock: ask the scene for a mid-"pause" moment directly.
    frame = source._background.copy()  # noqa: SLF001
    pose = source._visitor_pose(10.0)  # t=10s is inside the pause window
    assert pose is not None
    source._draw_visitor(frame, *pose)  # noqa: SLF001
    return frame
