"""Typed application configuration.

Every tunable in the system lives here, loaded from environment variables and/or
an ``.env`` file (see ``edge/.env.example`` for the annotated template). Components
never read ``os.environ`` directly — they receive a ``Settings`` object (or just the
fields they need) from the composition root, which keeps configuration testable:
tests construct ``Settings(...)`` with explicit values.
"""

from enum import StrEnum
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Profile(StrEnum):
    """Which set of hardware adapters the composition root wires up.

    See docs/decisions/008-hardware-abstraction.md — this single value is what
    makes the same codebase run on a laptop, on the Pi, and on a Windows PC.
    See docs/decisions/010-windows-target.md for the Windows profile.
    """

    DEV = "dev"
    PI = "pi"
    WINDOWS = "windows"


# Hardware each profile wires when CAMERA_SOURCE / DETECTOR are left unset.
_PROFILE_CAMERA = {Profile.DEV: "synthetic", Profile.PI: "picamera2", Profile.WINDOWS: "webcam"}
_PROFILE_DETECTOR = {Profile.DEV: "mock", Profile.PI: "hailo", Profile.WINDOWS: "onnx"}


class Settings(BaseSettings):
    """All runtime configuration, with defaults chosen for the zero-setup dev experience."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    edge_profile: Profile = Profile.DEV

    # --- Camera ---
    # None = "follow the profile" (dev → synthetic, pi → picamera2); set
    # explicitly only to override, e.g. CAMERA_SOURCE=webcam on a laptop.
    # Field-tested reason this exists: a Pi with EDGE_PROFILE=pi and no
    # override once ran the synthetic test scene, exactly as the old defaults
    # said to — the profile must be the one switch that re-wires hardware.
    camera_source: str | None = None  # synthetic | webcam | picamera2
    # Webcam only: which camera (0 = first) and which OpenCV capture backend.
    # "auto" = DirectShow on Windows (opens in ~1 s and honors the resolution;
    # the default Media Foundation backend can take 5-10 s), OpenCV's choice elsewhere.
    camera_index: int = 0
    camera_backend: str = "auto"  # auto | dshow | msmf | v4l2 | any
    frame_width: int = 1280
    frame_height: int = 720
    target_fps: float = 15.0

    # --- Detection (docs/requirements/01-detection.md) ---
    detector: str | None = None  # mock | hog | hailo | onnx; None = follow the profile
    detection_confidence_threshold: float = 0.5  # 01-F5
    # 01-F7: also greet dogs and cats (onnx and hailo detectors; COCO classes).
    detect_pets: bool = True
    # 01-F8: ignore visitors shorter than this fraction of the frame height
    # (too far away to identify). Lower it if your camera is far from the door.
    min_person_height: float = 0.2
    min_pet_height: float = 0.1
    hailo_hef_path: Path | None = None
    # ONNX YOLOv8 detector (windows profile; any machine with the [onnx] extra).
    onnx_model_path: Path = Path("./models/yolov8n.onnx")
    onnx_provider: str = "cpu"  # cpu | directml (needs the [directml] extra)

    # --- Costume identification (docs/requirements/03-identification.md) ---
    anthropic_api_key: str | None = None  # unset → pretend mode (03-F7)
    # Sonnet: names specific characters and reads props/homemade costumes far
    # better than Haiku, for ~1 s more per greeting (ADR-002). claude-haiku-5-5
    # is the faster, cheaper alternative.
    claude_model: str = "claude-sonnet-5-5"
    identify_timeout_seconds: float = 15.0  # 03-F6

    # --- Tracking (docs/requirements/02-tracking.md) ---
    tracker_min_hits: int = 3  # 02-F3: frames a person must be seen before "new visitor"
    tracker_max_misses: int = 2  # 02-F3: missed frames tolerated while counting those hits
    tracker_retire_seconds: float = 30.0  # 02-F4: absence before a visitor is forgotten
    tracker_iou_threshold: float = 0.3  # 02-F1: minimum overlap to match across frames
    # --- Groups (02-F7, 03-F9, 04-F9) ---
    group_wait_seconds: float = 1.0  # longest a group waits for friends a step behind
    group_max_size: int = 6  # people per Claude call; bigger crowds become several groups
    shout_out_max_group: int = 3  # speak per-costume shout-outs for groups up to this size
    # --- Photos sent to Claude (02-F8) ---
    snapshots_per_visitor: int = 3  # best photo + up to 2 other moments; 1 = best only
    max_images_per_call: int = 8  # extras fill this budget after everyone's best photo

    # --- Speech (docs/requirements/04-speech.md) ---
    tts_engine: str = "null"  # piper | google | null
    piper_voice_path: Path | None = None
    audio_device: str | None = None  # ALSA device on the Pi, e.g. "plughw:1,0" (Pi only)
    speech_queue_max: int = 3  # 04-F4: older unspoken comments beyond this are dropped
    spooky_voice: bool = False  # issue #15: rotate spooky voice effects (pure numpy)

    # --- Storage & privacy (docs/requirements/05-storage.md) ---
    data_dir: Path = Path("./data")
    snapshot_retention_days: int = 7  # 0 = metadata-only mode (05-N3)

    # --- API server ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- Cloud sync (docs/requirements/07-cloud.md; off by default per 07-F1) ---
    cloud_sync_enabled: bool = False
    gcp_project_id: str | None = None
    gcp_pubsub_topic: str = "costume-sightings"
    device_id: str = "porch-pi"

    @model_validator(mode="after")
    def _profile_defaults(self) -> "Settings":
        """Resolve profile-dependent defaults (see camera_source comment above)."""
        if self.camera_source is None:
            self.camera_source = _PROFILE_CAMERA[self.edge_profile]
        if self.detector is None:
            self.detector = _PROFILE_DETECTOR[self.edge_profile]
        return self

    # Derived paths — one place decides the on-disk layout under data_dir.
    @property
    def db_path(self) -> Path:
        return self.data_dir / "sightings.db"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def audio_out_dir(self) -> Path:
        """Where the dev-profile NullAudioPlayer drops WAV files (04-F7)."""
        return self.data_dir / "audio-out"
