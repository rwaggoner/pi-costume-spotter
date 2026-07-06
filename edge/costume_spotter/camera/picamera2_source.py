"""Raspberry Pi AI Camera adapter, via Picamera2 (pi profile only).

Install note: picamera2 comes from apt (python3-picamera2), so the venv must be
created with --system-site-packages — see docs/setup-pi.md §6.

Format gotcha worth knowing: Picamera2's pixel-format names describe byte order,
so "BGR888" is what yields R,G,B channel order in the numpy array — which is
what this codebase's frame contract requires (imaging.py). Yes, really; it's a
documented Picamera2 quirk inherited from underlying video conventions.
"""

import numpy as np

from costume_spotter.camera.base import FrameSource


class Picamera2Source(FrameSource):
    """Frames from the CSI camera (IMX500 used purely as a camera here — ADR-001)."""

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise RuntimeError(
                "CAMERA_SOURCE=picamera2 requires python3-picamera2 from apt and a "
                "venv created with --system-site-packages (docs/setup-pi.md §6)"
            ) from exc
        # Fail fast with an actionable message (01-F6): Picamera2() itself dies
        # with a bare IndexError when libcamera reports zero cameras — the
        # least-debuggable startup crash of the whole bring-up. Field-tested.
        if not Picamera2.global_camera_info():
            raise RuntimeError(
                "libcamera sees no cameras. Check, in order: "
                "(1) `rpicam-hello --list-cameras` — does the OS see it at all? "
                "(2) CSI ribbon seated at BOTH ends, correct orientation "
                "(easily disturbed while mounting the Hailo HAT); "
                "(3) `sudo apt install imx500-all` (docs/setup-pi.md §2); "
                "(4) reboot after any of the above."
            )
        self._camera = Picamera2()
        config = self._camera.create_video_configuration(
            main={"size": (width, height), "format": "BGR888"}  # = RGB in numpy; see module docs
        )
        self._camera.configure(config)
        self._camera.start()

    def read(self) -> np.ndarray:
        # capture_array blocks until the next frame — exactly the FrameSource contract.
        return self._camera.capture_array("main")

    def close(self) -> None:
        self._camera.stop()
        self._camera.close()
