"""Hailo-8 person detection: YOLOv8s on the AI HAT+ (pi profile; ADR-001).

Uses Picamera2's ``Hailo`` helper rather than raw HailoRT: it's the path
Raspberry Pi documents and ships examples for, it manages the VDevice/stream
plumbing, and it decodes the NMS postprocess that the model-zoo ``yolov8s.hef``
has compiled in — so what comes back is already "boxes with scores per class".

The model expects a square input (typically 640×640); we letterbox-free resize
the full frame down and scale box coordinates back up. At porch distances the
slight aspect distortion measurably doesn't hurt person recall and keeps the
code simple.
"""

import numpy as np
from PIL import Image

from costume_spotter.detection.base import Detector
from costume_spotter.events.events import BoundingBox, Detection

_PERSON_CLASS = 0  # COCO class index for "person" — the only class we act on


class HailoDetector(Detector):
    """People via yolov8s.hef on the Hailo-8 (docs/setup-pi.md §3)."""

    name = "hailo"

    def __init__(self, hef_path, confidence_threshold: float = 0.5) -> None:
        try:
            from picamera2.devices import Hailo
        except ImportError as exc:
            raise RuntimeError(
                "DETECTOR=hailo requires the hailo-all apt package and a venv with "
                "--system-site-packages (docs/setup-pi.md §3/§6)"
            ) from exc
        self._threshold = confidence_threshold
        self._hailo = Hailo(str(hef_path))  # fails loudly if the HAT is absent (01-F6)
        h, w = self._hailo.get_input_shape()[:2]
        self._model_h, self._model_w = int(h), int(w)

    def detect(self, frame: np.ndarray) -> list[Detection]:
        frame_h, frame_w = frame.shape[:2]
        # Resize down to the model's input size (see module docs re: aspect ratio).
        small = np.asarray(
            Image.fromarray(frame).resize((self._model_w, self._model_h), Image.BILINEAR)
        )
        # With NMS compiled into the HEF, run() returns one list per class of
        # [y0, x0, y1, x1, score] rows, coordinates normalized to 0..1.
        results = self._hailo.run(small)
        detections: list[Detection] = []
        for y0, x0, y1, x1, score in np.atleast_2d(results[_PERSON_CLASS]):
            if score < self._threshold:  # 01-F5, at the source
                continue
            detections.append(Detection(
                box=BoundingBox(
                    x=int(x0 * frame_w),
                    y=int(y0 * frame_h),
                    width=int((x1 - x0) * frame_w),
                    height=int((y1 - y0) * frame_h),
                ),
                confidence=round(float(score), 2),
            ))
        return detections

    def close(self) -> None:
        self._hailo.close()
