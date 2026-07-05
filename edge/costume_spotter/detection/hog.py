"""HOG person detector: real detection of real people on a laptop webcam.

OpenCV's classic HOG+SVM pedestrian detector — decades old, CPU-only, and far
less accurate than YOLO, but it needs no accelerator and no model download,
which makes it the honest middle rung between the synthetic mock and the Pi's
Hailo backend. Requires the ``webcam`` extra.
"""

import numpy as np

from costume_spotter.detection.base import Detector
from costume_spotter.events.events import BoundingBox, Detection


class HogDetector(Detector):
    """People via cv2.HOGDescriptor with the built-in pedestrian SVM."""

    name = "hog"

    def __init__(self, confidence_threshold: float = 0.5) -> None:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError(
                "DETECTOR=hog needs OpenCV: pip install -e \".[webcam]\""
            ) from exc
        self._cv2 = cv2
        self._threshold = confidence_threshold
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, frame: np.ndarray) -> list[Detection]:
        # HOG works on grayscale internally; give it BGR as OpenCV expects.
        bgr = self._cv2.cvtColor(frame, self._cv2.COLOR_RGB2BGR)
        rects, weights = self._hog.detectMultiScale(bgr, winStride=(8, 8), scale=1.05)
        detections = []
        for (x, y, w, h), weight in zip(rects, np.asarray(weights).flatten()):
            # HOG SVM scores are unbounded; squash to (0,1) so downstream
            # thresholds mean the same thing across every backend (01-F5).
            confidence = float(1 / (1 + np.exp(-weight)))
            if confidence < self._threshold:
                continue
            detections.append(
                Detection(box=BoundingBox(int(x), int(y), int(w), int(h)),
                          confidence=round(confidence, 2))
            )
        return detections
