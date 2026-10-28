"""Webcam adapter for laptops and the Windows profile, via OpenCV.

Requires the ``webcam`` extra (``pip install -e ".[webcam]"``). The import of cv2
is inside the class so the core install never touches it — the pattern every
hardware adapter in this repo follows (ADR-008).

Windows notes (ADR-010): OpenCV's default Windows backend, Media Foundation,
can take 5-10 s to open a camera and sometimes ignores the requested
resolution. DirectShow opens in about a second and honors it, so ``auto``
picks DirectShow on Windows. A camera blocked by Windows privacy settings
"opens" but returns no frames, so the first read is checked at startup.
"""

import sys

import numpy as np

from costume_spotter.camera.base import FrameSource

# Config value -> name of the cv2.CAP_* constant (resolved after importing cv2).
_BACKENDS = {
    "any": "CAP_ANY",
    "dshow": "CAP_DSHOW",
    "msmf": "CAP_MSMF",
    "v4l2": "CAP_V4L2",
}


def resolve_backend(name: str, platform: str = sys.platform) -> str:
    """Map CAMERA_BACKEND to a cv2 constant name; ``auto`` depends on the OS."""
    name = name.lower()
    if name == "auto":
        return "CAP_DSHOW" if platform == "win32" else "CAP_ANY"
    if name not in _BACKENDS:
        raise ValueError(
            f"unknown CAMERA_BACKEND {name!r} — use one of: auto, {', '.join(_BACKENDS)}"
        )
    return _BACKENDS[name]


class WebcamSource(FrameSource):
    """Frames from a local webcam (CAMERA_INDEX, default 0)."""

    def __init__(self, width: int = 1280, height: int = 720, device_index: int = 0,
                 backend: str = "auto") -> None:
        try:
            import cv2
        except ImportError as exc:  # fail fast with the fix, not a bare traceback (01-F6)
            raise RuntimeError(
                "CAMERA_SOURCE=webcam needs OpenCV: pip install -e \".[webcam]\""
            ) from exc
        self._cv2 = cv2
        backend_const = resolve_backend(backend)
        self._cap = cv2.VideoCapture(device_index, getattr(cv2, backend_const))
        if not self._cap.isOpened():
            raise RuntimeError(
                f"webcam {device_index} could not be opened ({backend_const}). Try another "
                "CAMERA_INDEX (1, 2, ...) or CAMERA_BACKEND=msmf; close other apps using "
                "the camera."
            )
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        # Fail fast (01-F6): on Windows a camera denied by privacy settings opens
        # fine and then never delivers a frame.
        ok, _ = self._cap.read()
        if not ok:
            self._cap.release()
            hint = (" On Windows, check Settings > Privacy & security > Camera > "
                    "'Let desktop apps access your camera'.") if sys.platform == "win32" else ""
            raise RuntimeError(f"webcam {device_index} opened but returned no frame.{hint}")

    def read(self) -> np.ndarray:
        ok, frame_bgr = self._cap.read()
        if not ok:
            raise RuntimeError("webcam read failed (unplugged?)")
        # Boundary rule from imaging.py: everything past this line is RGB.
        return self._cv2.cvtColor(frame_bgr, self._cv2.COLOR_BGR2RGB)

    def close(self) -> None:
        self._cap.release()
