"""Webcam adapter for laptop demos, via OpenCV.

Requires the ``webcam`` extra (``pip install -e ".[webcam]"``). The import of cv2
is inside the class so the core install never touches it — the pattern every
hardware adapter in this repo follows (ADR-008).
"""

import numpy as np

from costume_spotter.camera.base import FrameSource


class WebcamSource(FrameSource):
    """Frames from a local webcam (device 0 by default)."""

    def __init__(self, width: int = 1280, height: int = 720, device_index: int = 0) -> None:
        try:
            import cv2
        except ImportError as exc:  # fail fast with the fix, not a bare traceback (01-F6)
            raise RuntimeError(
                "CAMERA_SOURCE=webcam needs OpenCV: pip install -e \".[webcam]\""
            ) from exc
        self._cv2 = cv2
        self._cap = cv2.VideoCapture(device_index)
        if not self._cap.isOpened():
            raise RuntimeError(f"webcam device {device_index} could not be opened")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def read(self) -> np.ndarray:
        ok, frame_bgr = self._cap.read()
        if not ok:
            raise RuntimeError("webcam read failed (unplugged?)")
        # Boundary rule from imaging.py: everything past this line is RGB.
        return self._cv2.cvtColor(frame_bgr, self._cv2.COLOR_BGR2RGB)

    def close(self) -> None:
        self._cap.release()
