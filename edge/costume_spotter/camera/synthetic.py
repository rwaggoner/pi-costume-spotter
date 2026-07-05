"""A synthetic camera: renders a fake porch scene with a visitor who comes and goes.

This is what makes the zero-hardware quick start (docs/setup-dev.md) feel alive.
Every ~24 seconds a blocky magenta "visitor" walks into frame, approaches the
camera, pauses, and leaves. The visitor is drawn in a reserved magenta so the
MockDetector (detection/mock.py) can find them by color — meaning the dev
pipeline exercises real detection logic on real pixels rather than being handed
scripted coordinates. The two modules share only that color constant.
"""

import time

import numpy as np

from costume_spotter.camera.base import FrameSource

# The color contract between the synthetic scene and the mock detector.
# Chosen because nothing else in the rendered scene (or in nature, much) is
# fully saturated magenta.
VISITOR_COLOR = (230, 20, 230)

# Timeline of one visitor cycle, in seconds.
_ENTER_END = 8.0   # walking in from the left, growing as they approach
_PAUSE_END = 12.0  # standing at the "door"
_LEAVE_END = 16.0  # walking back out
_CYCLE = 24.0      # then an empty porch until the next visitor


class SyntheticSource(FrameSource):
    """Deterministic animated scene, driven by the wall clock."""

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self._w = width
        self._h = height
        self._background = self._render_background()
        self._t0 = time.monotonic()

    def read(self) -> np.ndarray:
        frame = self._background.copy()
        elapsed = time.monotonic() - self._t0
        t = elapsed % _CYCLE
        # Alternate entry side each cycle. This matters for the demo: the
        # tracker (rightly) refuses to re-announce someone who returns to the
        # same spot within its retirement window (02-F4), so a visitor who
        # always walked the same path would be greeted exactly once per run.
        # Entering from the other side gives zero box overlap → a new track.
        from_the_right = int(elapsed // _CYCLE) % 2 == 1
        pose = self._visitor_pose(t)
        if pose is not None:
            x, feet_y, height = pose
            if from_the_right:
                x = self._w - x
            self._draw_visitor(frame, x, feet_y, height)
        return frame

    # -- scene construction --------------------------------------------------

    def _render_background(self) -> np.ndarray:
        """Night-sky gradient, a few stars, a porch floor. Rendered once."""
        h, w = self._h, self._w
        # Vertical gradient: deep navy at the top to dusk purple at the horizon.
        top = np.array([12, 12, 40], dtype=np.float32)
        bottom = np.array([60, 35, 70], dtype=np.float32)
        ramp = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
        sky = (top * (1 - ramp) + bottom * ramp).astype(np.uint8)
        frame = np.broadcast_to(sky, (h, w, 3)).copy()
        # Stars: fixed seed so the scene is stable across frames and runs.
        rng = np.random.default_rng(42)
        ys = rng.integers(0, int(h * 0.6), 80)
        xs = rng.integers(0, w, 80)
        frame[ys, xs] = (220, 220, 200)
        # Porch floor: bottom 15%.
        frame[int(h * 0.85):, :] = (45, 35, 30)
        return frame

    def _visitor_pose(self, t: float) -> tuple[int, int, int] | None:
        """Where the visitor is at cycle-time ``t``: (center_x, feet_y, height_px)."""
        if t >= _LEAVE_END:
            return None  # empty porch
        far_h, near_h = int(self._h * 0.25), int(self._h * 0.62)
        entry_x, door_x = int(self._w * 0.08), int(self._w * 0.55)
        if t < _ENTER_END:  # approaching: interpolate position and apparent size
            p = t / _ENTER_END
        elif t < _PAUSE_END:  # standing still (long enough to be tracked + announced)
            p = 1.0
        else:  # leaving: run the approach backwards
            p = 1.0 - (t - _PAUSE_END) / (_LEAVE_END - _PAUSE_END)
        x = int(entry_x + (door_x - entry_x) * p)
        height = int(far_h + (near_h - far_h) * p)
        feet_y = int(self._h * 0.85) + int(height * 0.05)  # slightly onto the porch
        return x, feet_y, height

    def _draw_visitor(self, frame: np.ndarray, cx: int, feet_y: int, height: int) -> None:
        """A torso rectangle + head square in VISITOR_COLOR. Blocky is fine —
        the mock detector needs a blob, and the pretend identifier needs nothing."""
        body_w = height // 3
        head = height // 4
        color = np.array(VISITOR_COLOR, dtype=np.uint8)

        def fill(y1: int, y2: int, x1: int, x2: int) -> None:
            y1, y2 = max(0, y1), min(self._h, y2)
            x1, x2 = max(0, x1), min(self._w, x2)
            if y1 < y2 and x1 < x2:
                frame[y1:y2, x1:x2] = color

        fill(feet_y - height + head, feet_y, cx - body_w // 2, cx + body_w // 2)  # torso+legs
        fill(feet_y - height, feet_y - height + head, cx - head // 2, cx + head // 2)  # head
