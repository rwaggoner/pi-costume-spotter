"""Tiny image utilities shared across the pipeline.

Frames everywhere in this codebase are ``numpy.ndarray`` of shape (H, W, 3),
dtype uint8, **RGB** order. Adapters convert at the boundary (OpenCV is BGR,
Picamera2 is configured for RGB) so the rest of the code never thinks about
channel order. JPEG work goes through Pillow so the core install needs no OpenCV
(see the dependency note in edge/pyproject.toml).
"""

import io

import numpy as np
from PIL import Image, ImageOps

from costume_spotter.events.events import BoundingBox


def encode_jpeg(frame: np.ndarray, quality: int = 80) -> bytes:
    """RGB ndarray -> JPEG bytes. Quality 80 ≈ visually fine, ~half the bytes of 95."""
    buf = io.BytesIO()
    Image.fromarray(frame).save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def crop_box(frame: np.ndarray, box: BoundingBox, pad_fraction: float = 0.25) -> np.ndarray:
    """Crop a detection from a frame, with padding so the costume isn't cut at the box edge.

    Detection boxes hug the person's body; a witch's hat brim, wings, a cape, or
    a sword or wand held out often sit outside it, and those are exactly the
    clues that tell one costume from another. 25% padding keeps them in the
    shot (03-F1) at small byte cost.
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


def sharpness(region: np.ndarray) -> float:
    """How sharp an image region is: variance of the Laplacian of its grayscale.

    Motion blur (a visitor mid-stride) and focus blur both flatten edges, which
    drops this number. Computed on a ~160 px subsample, so it's cheap enough to
    run on every frame while a visitor is being tracked (02-N1), and roughly
    comparable between big and small crops.
    """
    h, w = region.shape[:2]
    step = max(1, max(h, w) // 160)
    gray = region[::step, ::step].astype(np.float32).mean(axis=2)
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    lap = (gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:]
           - 4 * gray[1:-1, 1:-1])
    return float(lap.var())


def enhance_for_identification(crop: np.ndarray) -> np.ndarray:
    """Make a porch snapshot easier to read: stretch contrast, lift dark shots.

    Halloween happens at night: webcam frames under a porch light are dim and
    flat, and costume colors and details sink into the shadows. Contrast is
    stretched on brightness only (``preserve_tone``), so costume colors stay
    true, and dark images get a gamma lift. A well-lit snapshot is barely changed.
    """
    image = ImageOps.autocontrast(Image.fromarray(crop), cutoff=1, preserve_tone=True)
    mean = float(np.asarray(image.convert("L")).mean())
    if mean < 90:  # dark: brighten the midtones without blowing out the porch light
        gamma = 0.6 if mean < 50 else 0.8
        lut = [round(255 * (i / 255) ** gamma) for i in range(256)]
        image = image.point(lut * 3)
    return np.asarray(image)
