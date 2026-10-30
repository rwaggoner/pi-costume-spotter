# edge/ — the application that runs on the Raspberry Pi

Python 3.11+, on a Raspberry Pi or a Windows PC. Watches the camera, detects and tracks visitors, identifies
costumes via Claude, speaks, logs, and serves the dashboard's API.

**Run it with zero hardware:** [docs/setup-dev.md](../docs/setup-dev.md).
**Run it on the Pi:** [docs/setup-pi.md](../docs/setup-pi.md).
**Run it on Windows:** [docs/setup-windows.md](../docs/setup-windows.md).

## Package map

Mirrors the architecture diagram ([docs/architecture.md](../docs/architecture.md)):

| Package | Role | Key decision |
|---------|------|--------------|
| [`events/`](costume_spotter/events/) | Async pub/sub bus + event dataclasses — the spine | [ADR-003](../docs/decisions/003-event-bus.md) |
| [`camera/`](costume_spotter/camera/) | `FrameSource` port: synthetic / webcam / Picamera2 | [ADR-008](../docs/decisions/008-hardware-abstraction.md) |
| [`detection/`](costume_spotter/detection/) | `Detector` port: mock / HOG / Hailo YOLOv8 / ONNX YOLOv8 | [ADR-001](../docs/decisions/001-hailo-vs-imx500.md), [ADR-010](../docs/decisions/010-windows-target.md) |
| [`tracking/`](costume_spotter/tracking/) | Per-frame boxes → one event per visitor | [02-tracking.md](../docs/requirements/02-tracking.md) |
| [`vision/`](costume_spotter/vision/) | Claude Vision: costume + comment in one call | [ADR-002](../docs/decisions/002-claude-vision.md) |
| [`speech/`](costume_spotter/speech/) | `TtsEngine` + `AudioPlayer` ports (aplay / winsound), playback queue, spooky voice | [ADR-005](../docs/decisions/005-tts-strategy.md) |
| [`storage/`](costume_spotter/storage/) | SQLite rows + snapshot files + retention | [ADR-004](../docs/decisions/004-sqlite-edge.md) |
| [`cloudsync/`](costume_spotter/cloudsync/) | Optional Pub/Sub publisher (text only, no pixels) | [07-cloud.md](../docs/requirements/07-cloud.md) |
| [`api/`](costume_spotter/api/) | FastAPI: REST + `/ws/events` + `/stream.mjpg` | [ADR-007](../docs/decisions/007-mjpeg-vs-webrtc.md) |
| [`main.py`](costume_spotter/main.py) | **Start here** — the composition root that wires a profile | |

## Commands

```bash
pip install -e ".[dev]"      # add [webcam], [onnx], [windows] and/or [gcp] extras as needed
python -m costume_spotter    # http://localhost:8000 (API docs at /docs)
python -m costume_spotter.vision.try_photo a.jpg b.jpg   # test identification on photos
pytest                       # no hardware required
ruff check .
```

## Reading guide

The best 15-minute tour: `main.py` (how it's wired) → `events/bus.py` (how parts
talk) → `tracking/tracker.py` (the interesting logic) → `vision/identifier.py`
(the AI call and its failure philosophy).
