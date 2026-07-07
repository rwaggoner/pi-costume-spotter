"""Hailo-8 person detection: YOLOv8s on the AI HAT+ (pi profile; ADR-001).

Uses Picamera2's ``Hailo`` helper rather than raw HailoRT: it's the path
Raspberry Pi documents and ships examples for, it manages the VDevice/stream
plumbing, and it decodes the NMS postprocess that the model-zoo ``yolov8s.hef``
has compiled in — so what comes back is already "boxes with scores per class".

The model expects a square input (typically 640×640); frames are letterboxed —
scaled preserving aspect ratio, padded with YOLO's conventional gray — and the
result boxes mapped back through the same geometry (issue #9; the earlier
squish-resize cost recall on wide/bulky costumes). The geometry lives in
module-level pure functions so it's unit-tested without Hailo hardware.
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image

from costume_spotter.detection.base import Detector
from costume_spotter.events.events import BoundingBox, Detection

_PERSON_CLASS = 0  # COCO class index for "person" — the only class we act on


def person_rows(results) -> np.ndarray:
    """Normalize the Hailo helper's per-class results to an (N, 5) array.

    The helper's shape varies with content (issue #7, found on the very first
    on-Pi frame): an empty class can be ``[]`` (a bare Python list — and
    ``np.atleast_2d([])`` is the (1, 0) trap that crashed the pipeline),
    a single detection can arrive as a flat ``(5,)`` row, and the normal case
    is ``(N, 5)``. This funnels all of them into ``(N, 5)`` with N possibly 0.

    Module-level (not a method) so it's unit-testable on machines without
    Hailo hardware — the class constructor needs the real device.
    """
    if len(results) <= _PERSON_CLASS:
        return np.empty((0, 5), dtype=np.float32)
    rows = np.asarray(results[_PERSON_CLASS], dtype=np.float32)
    if rows.size == 0:
        return np.empty((0, 5), dtype=np.float32)
    return rows.reshape(-1, 5)


# YOLO's conventional letterbox padding gray (what the models saw in training).
_PAD_GRAY = 114


@dataclass(frozen=True)
class LetterboxParams:
    """Geometry of one frame-size → model-size letterbox."""

    scale: float   # applied to the frame before padding
    scaled_w: int  # frame size after scaling, before padding
    scaled_h: int
    pad_x: int     # padding added left (same again right, +/- a rounding pixel)
    pad_y: int     # padding added top


def letterbox_params(frame_w: int, frame_h: int, model_w: int, model_h: int) -> LetterboxParams:
    """Fit frame into model canvas preserving aspect ratio, centered."""
    scale = min(model_w / frame_w, model_h / frame_h)
    scaled_w, scaled_h = round(frame_w * scale), round(frame_h * scale)
    return LetterboxParams(scale, scaled_w, scaled_h,
                           (model_w - scaled_w) // 2, (model_h - scaled_h) // 2)


def map_normalized_box(y0: float, x0: float, y1: float, x1: float,
                       p: LetterboxParams, frame_w: int, frame_h: int,
                       model_w: int, model_h: int) -> BoundingBox:
    """Model-space normalized box → frame-pixel BoundingBox, clamped to frame.

    Inverse of the letterbox: normalized → model pixels → subtract padding →
    divide by scale. Boxes reaching into the gray bars clamp to the frame edge.
    """
    fx0 = (x0 * model_w - p.pad_x) / p.scale
    fy0 = (y0 * model_h - p.pad_y) / p.scale
    fx1 = (x1 * model_w - p.pad_x) / p.scale
    fy1 = (y1 * model_h - p.pad_y) / p.scale
    fx0, fx1 = max(0.0, min(frame_w, fx0)), max(0.0, min(frame_w, fx1))
    fy0, fy1 = max(0.0, min(frame_h, fy0)), max(0.0, min(frame_h, fy1))
    return BoundingBox(x=int(fx0), y=int(fy0),
                       width=int(fx1 - fx0), height=int(fy1 - fy0))


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
        p = letterbox_params(frame_w, frame_h, self._model_w, self._model_h)
        # Scale preserving aspect, paste centered onto the gray canvas.
        # np.full also conveniently yields WRITABLE memory — HailoRT's
        # set_buffer rejects read-only arrays (found on-device, PR #8).
        resized = Image.fromarray(frame).resize((p.scaled_w, p.scaled_h), Image.BILINEAR)
        canvas = np.full((self._model_h, self._model_w, 3), _PAD_GRAY, dtype=np.uint8)
        canvas[p.pad_y:p.pad_y + p.scaled_h, p.pad_x:p.pad_x + p.scaled_w] = np.asarray(resized)
        # With NMS compiled into the HEF, run() returns per-class results of
        # [y0, x0, y1, x1, score] rows, coordinates normalized to 0..1 —
        # in content-dependent shapes; person_rows() normalizes them.
        results = self._hailo.run(canvas)
        detections: list[Detection] = []
        for y0, x0, y1, x1, score in person_rows(results):
            if score < self._threshold:  # 01-F5, at the source
                continue
            detections.append(Detection(
                box=map_normalized_box(y0, x0, y1, x1, p, frame_w, frame_h,
                                       self._model_w, self._model_h),
                confidence=round(float(score), 2),
            ))
        return detections

    def close(self) -> None:
        self._hailo.close()
