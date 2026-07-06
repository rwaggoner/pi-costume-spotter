"""The frame pipeline: camera → detector → tracker → events.

This is the only *producer* loop in the system; everything else reacts to what it
publishes. It runs as a single asyncio task, but the blocking work (camera reads,
inference, JPEG encoding) happens in worker threads via ``asyncio.to_thread`` so
the event loop — which also serves the API — stays responsive.

Pacing: the loop aims at ``target_fps`` and sleeps off any surplus. If a frame
takes longer than its budget (slow inference), the loop simply runs at whatever
rate it can — frames are pulled, never queued, so there is no growing backlog.
"""

import asyncio
import logging
import time

from costume_spotter import imaging
from costume_spotter.camera.base import FrameSource
from costume_spotter.detection.base import Detector
from costume_spotter.events import EventBus, FrameProcessed, NewVisitorSpotted, SystemStatus
from costume_spotter.tracking import VisitorTracker

logger = logging.getLogger(__name__)


class FramePipeline:
    """Owns the capture/detect/track loop and publishes its findings."""

    def __init__(self, bus: EventBus, source: FrameSource, detector: Detector,
                 tracker: VisitorTracker, *, target_fps: float,
                 confidence_threshold: float) -> None:
        self._bus = bus
        self._source = source
        self._detector = detector
        self._tracker = tracker
        self._frame_budget = 1.0 / target_fps
        self._threshold = confidence_threshold
        self._fps = 0.0

    async def run(self) -> None:
        """The loop. Cancelled at shutdown; camera/detector cleanup happens here."""
        logger.info("pipeline starting: %s -> %s", type(self._source).__name__,
                    self._detector.name)
        self._bus.publish(SystemStatus(component="camera", ok=True))
        self._bus.publish(SystemStatus(component="detector", ok=True,
                                       detail=self._detector.name))
        try:
            while True:
                started = time.monotonic()
                await self._process_one_frame()
                # Sleep off whatever's left of this frame's time budget.
                elapsed = time.monotonic() - started
                await asyncio.sleep(max(0.0, self._frame_budget - elapsed))
                # Exponential moving average smooths the dashboard's fps readout.
                inst_fps = 1.0 / max(elapsed, self._frame_budget)
                self._fps = self._fps * 0.9 + inst_fps * 0.1
        except Exception:
            # This task is fire-and-forget from main.py's lifespan; without this
            # handler its exception would be silently discarded and the app
            # would keep serving an API over a dead camera (issue #6 — exactly
            # what happened on the first on-Pi run). Shout, mark unhealthy so
            # the dashboard header goes red, and re-raise.
            # (CancelledError is BaseException, so normal shutdown skips this.)
            logger.exception("pipeline crashed — detection and the live feed are DOWN")
            self._bus.publish(SystemStatus(component="detector", ok=False,
                                           detail="pipeline crashed; see app logs"))
            self._bus.publish(SystemStatus(component="camera", ok=False,
                                           detail="pipeline crashed; see app logs"))
            raise
        finally:
            self._source.close()
            self._detector.close()
            logger.info("pipeline stopped")

    async def _process_one_frame(self) -> None:
        frame = await asyncio.to_thread(self._source.read)
        detections = await asyncio.to_thread(self._detector.detect, frame)
        # Belt-and-braces threshold (01-F5): backends already filter, but the
        # pipeline is where the guarantee lives, not each adapter's discipline.
        detections = [d for d in detections if d.confidence >= self._threshold]

        # Tracking is fast pure math (02-N1) — no thread hop needed.
        new_visitors = self._tracker.update(detections, frame, now=time.monotonic())

        for visitor in new_visitors:
            snapshot_jpeg = await asyncio.to_thread(imaging.encode_jpeg, visitor.snapshot, 90)
            logger.info("new visitor #%d (box %dx%d)", visitor.visitor_id,
                        visitor.box.width, visitor.box.height)
            self._bus.publish(NewVisitorSpotted(
                visitor_id=visitor.visitor_id,
                snapshot_jpeg=snapshot_jpeg,
                box=visitor.box,
            ))

        # Publish the frame for the MJPEG stream + overlay. Quality 80 halves
        # bandwidth vs 95 with no visible difference at dashboard sizes.
        jpeg = await asyncio.to_thread(imaging.encode_jpeg, frame, 80)
        self._bus.publish(FrameProcessed(jpeg=jpeg, detections=tuple(detections),
                                         fps=round(self._fps, 1)))
