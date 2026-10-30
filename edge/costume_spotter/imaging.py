"""Tiny image utilities shared across the pipeline.

Frames everywhere in this codebase are ``numpy.ndarray`` of shape (H, W, 3),
dtype uint8, **RGB** order. Adapters convert at the boundary (OpenCV is BGR,
Picamera2 is configured for RGB) so the rest of the code never thinks about
channel order. JPEG work goes through Pillow so the core install needs no OpenCV
(see the dependency note in edge/pyproject.toml).
"""

import io

import numpy as np
from PIL import Image

from costume_spotter.events.events import BoundingBox


def encode_jpeg(frame: np.ndarray, quality: int = 80) -> bytes:
    """RGB ndarray -> JPEG bytes. Quality 80 ≈ visually fine, ~half the bytes of 95."""
    buf = io.BytesIO()
    Image.fromarray(frame).save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def crop_box(frame: np.ndarray, box: BoundingBox, pad_fraction: float = 0.15) -> np.ndarray:
    """Crop a detection from a frame, with padding so the costume isn't cut at the box edge.

    Detection boxes hug the person tightly; a witch's hat brim or held prop often
    sits just outside. 15% padding keeps identification accuracy up (03-F1) at
    negligible byte cost.
    """
    h, w = frame.shape[:2]
    pad_x = int(box.width * pad_fraction)
    pad_y = int(box.height * pad_fraction)
    x1 = max(0, box.x - pad_x)
    y1 = max(0, box.y - pad_y)
    x2 = min(w, box.x + box.width + pad_x)
    y2 = min(h, box.y + box.height + pad_y)
    return frame[y1:y2, x1:x2]


def shrink(frame: np.ndarray, max_side: int) -> np.ndarray:
    """Downscale so the longest side is at most ``max_side`` (never upscales).

    Snapshots go to Claude: a 512-px crop identifies a costume as well as a
    full-resolution one, but uploads faster and costs fewer image tokens, so
    the greeting arrives sooner.
    """
    h, w = frame.shape[:2]
    if max(h, w) <= max_side:
        return frame
    scale = max_side / max(h, w)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    return np.asarray(Image.fromarray(frame).resize(size, Image.LANCZOS))
