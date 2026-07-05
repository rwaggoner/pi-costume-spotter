"""Costume Spotter edge application.

Package layout mirrors the component diagram in docs/architecture.md:

- ``events/``    — the asyncio event bus and the event dataclasses (the system's spine)
- ``camera/``    — FrameSource adapters (synthetic, webcam, Picamera2)
- ``detection/`` — Detector adapters (mock, HOG, Hailo)
- ``tracking/``  — turns per-frame detections into one event per visitor
- ``vision/``    — costume identification via the Claude Vision API
- ``speech/``    — TTS engines and the one-at-a-time playback queue
- ``storage/``   — SQLite sighting repository and snapshot files
- ``cloudsync/`` — optional GCP Pub/Sub publisher
- ``api/``       — FastAPI: REST + WebSocket + MJPEG for the React dashboard
- ``main.py``    — the composition root that wires a profile's adapters together
"""

__version__ = "0.1.0"
