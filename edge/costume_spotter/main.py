"""The composition root: the ONE place where adapters are chosen and wired.

Reading this file top to bottom tells you the entire shape of the running
system — which is why there is no dependency-injection framework here
(ADR-008): explicit construction *is* the documentation.

Startup order matters and is encoded in ``_lifespan``:
bus consumers first (so no early event is dropped), then the frame pipeline,
then the retention job. Shutdown is the reverse.
"""

import asyncio
import contextlib
import logging

import uvicorn
from fastapi import FastAPI

from costume_spotter.api.app import create_app
from costume_spotter.camera.base import FrameSource
from costume_spotter.config import Profile, Settings
from costume_spotter.detection.base import Detector
from costume_spotter.events import EventBus, SystemStatus
from costume_spotter.pipeline import FramePipeline
from costume_spotter.speech import SpeechService
from costume_spotter.speech.base import AudioPlayer, TtsEngine
from costume_spotter.storage import SightingRepository, SnapshotStore
from costume_spotter.storage.logger import SightingLogger
from costume_spotter.tracking import VisitorTracker
from costume_spotter.vision import CostumeIdentifier

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Adapter selection: config value -> concrete class. Imports live inside each
# branch so a laptop never imports Pi SDKs and vice versa (ADR-008).
# --------------------------------------------------------------------------

def build_frame_source(settings: Settings) -> FrameSource:
    if settings.camera_source == "synthetic":
        from costume_spotter.camera.synthetic import SyntheticSource
        return SyntheticSource(settings.frame_width, settings.frame_height)
    if settings.camera_source == "webcam":
        from costume_spotter.camera.opencv_source import WebcamSource
        return WebcamSource(settings.frame_width, settings.frame_height)
    if settings.camera_source == "picamera2":
        from costume_spotter.camera.picamera2_source import Picamera2Source
        return Picamera2Source(settings.frame_width, settings.frame_height)
    raise ValueError(f"unknown CAMERA_SOURCE: {settings.camera_source!r}")


def build_detector(settings: Settings) -> Detector:
    if settings.detector == "mock":
        from costume_spotter.detection.mock import MockDetector
        return MockDetector()
    if settings.detector == "hog":
        from costume_spotter.detection.hog import HogDetector
        return HogDetector(settings.detection_confidence_threshold)
    if settings.detector == "hailo":
        from costume_spotter.detection.hailo import HailoDetector
        if settings.hailo_hef_path is None:
            raise ValueError("DETECTOR=hailo requires HAILO_HEF_PATH (docs/setup-pi.md §3)")
        return HailoDetector(settings.hailo_hef_path, settings.detection_confidence_threshold)
    raise ValueError(f"unknown DETECTOR: {settings.detector!r}")


def build_tts_engine(settings: Settings) -> TtsEngine:
    if settings.tts_engine == "piper":
        from costume_spotter.speech.piper import PiperTtsEngine
        if settings.piper_voice_path is None:
            raise ValueError("TTS_ENGINE=piper requires PIPER_VOICE_PATH (docs/setup-pi.md §5)")
        return PiperTtsEngine(str(settings.piper_voice_path))
    if settings.tts_engine == "google":
        from costume_spotter.speech.google_tts import GoogleTtsEngine
        return GoogleTtsEngine()
    from costume_spotter.speech.null import NullTtsEngine
    return NullTtsEngine()


def build_audio_player(settings: Settings) -> AudioPlayer:
    if settings.edge_profile is Profile.PI:
        from costume_spotter.speech.aplay import AplayAudioPlayer
        return AplayAudioPlayer(settings.audio_device)
    from costume_spotter.speech.null import FileAudioPlayer
    return FileAudioPlayer(settings.audio_out_dir)


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------

def build_application(settings: Settings) -> FastAPI:
    """Construct the whole system. Every arrow in the architecture diagram
    (docs/architecture.md) corresponds to a line in this function."""
    bus = EventBus()

    # Storage
    repository = SightingRepository(settings.db_path)
    snapshots = SnapshotStore(settings.snapshots_dir, settings.snapshot_retention_days)
    sighting_logger = SightingLogger(bus, repository, snapshots)

    # Perception
    source = build_frame_source(settings)
    detector = build_detector(settings)
    tracker = VisitorTracker(
        iou_threshold=settings.tracker_iou_threshold,
        min_hits=settings.tracker_min_hits,
        retire_seconds=settings.tracker_retire_seconds,
    )
    pipeline = FramePipeline(bus, source, detector, tracker,
                             target_fps=settings.target_fps,
                             confidence_threshold=settings.detection_confidence_threshold)

    # Reaction: identification + speech (both are pure bus subscribers)
    identifier = CostumeIdentifier(bus, api_key=settings.anthropic_api_key,
                                   model=settings.claude_model,
                                   timeout_seconds=settings.identify_timeout_seconds,
                                   detector_name=detector.name)
    tts_engine = build_tts_engine(settings)
    audio_filter = None
    if settings.spooky_voice:
        from costume_spotter.speech.spooky import SpookyVoice
        audio_filter = SpookyVoice()  # rotating spooky effect (issue #15)
    SpeechService(bus, tts_engine, build_audio_player(settings),
                  queue_max=settings.speech_queue_max, audio_filter=audio_filter)

    # Optional cloud tier (07-F1: off unless explicitly enabled)
    if settings.cloud_sync_enabled:
        from costume_spotter.cloudsync.pubsub_publisher import PubSubPublisher
        PubSubPublisher(bus, project_id=settings.gcp_project_id,
                        topic=settings.gcp_pubsub_topic, device_id=settings.device_id)

    app = create_app(settings, bus, repository, snapshots)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        await bus.start()  # consumers first: no early event is dropped
        # Initial heartbeats: components that only report on failure would
        # otherwise show as "unknown" in /api/health until something breaks.
        bus.publish(SystemStatus(component="identifier", ok=True, detail=identifier.mode))
        bus.publish(SystemStatus(component="speech", ok=True, detail=tts_engine.name))
        if not settings.cloud_sync_enabled:
            bus.publish(SystemStatus(component="cloudsync", ok=True, detail="disabled"))
        tasks = [
            asyncio.create_task(pipeline.run(), name="pipeline"),
            asyncio.create_task(sighting_logger.prune_forever(), name="retention"),
        ]
        logger.info("costume spotter up — profile=%s detector=%s tts=%s",
                    settings.edge_profile.value, detector.name, settings.tts_engine)
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await bus.stop()

    app.router.lifespan_context = lifespan
    return app


def run() -> None:
    """Entry point for ``python -m costume_spotter``."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app = build_application(settings)
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_level="warning")
