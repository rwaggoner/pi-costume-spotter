# Developer setup — run everything on a laptop

No Raspberry Pi, Hailo chip, camera, speaker, API key, or GCP account required.
This works because every hardware boundary has a mock adapter
([ADR-008](decisions/008-hardware-abstraction.md)).

## Prerequisites

- Python 3.11+
- Node 20+
- (optional) a webcam — otherwise the bundled synthetic video source is used
- (optional) an Anthropic API key — otherwise the identifier runs in pretend mode

## 1. Backend

```bash
cd edge
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -e ".[dev]"
```

Create your local config from the template:

```bash
# Windows:            macOS/Linux:
copy .env.example .env    # cp .env.example .env
```

The defaults select the `dev` profile: synthetic camera, mock detector, pretend
identifier, null audio. Optionally edit `.env`:

| Variable | Effect |
|----------|--------|
| `ANTHROPIC_API_KEY=<your-real-key>` | Real costume identification via Claude. Keys are ~100 ASCII chars, shown in full only when created in the console — the truncated `sk-ant-…` display in the key list is not the key (the app rejects non-ASCII values at startup). |
| `CAMERA_SOURCE=webcam` | Use your webcam instead of the synthetic scene |
| `TTS_ENGINE=piper` | Real local speech if you've installed a Piper voice |

Run it:

```bash
python -m costume_spotter
```

Then check:
- http://localhost:8000/stream.mjpg — live (mock) feed with a wandering "visitor"
- http://localhost:8000/api/health — component status
- http://localhost:8000/docs — interactive OpenAPI docs

The mock detector periodically "spots" a visitor, so within ~10 seconds you'll see
events flowing and sightings accumulating with **zero** hardware.

## 2. Frontend

```bash
cd web
npm install
npm run dev
```

Open http://localhost:5173 — the Vite dev server proxies API calls to the backend on
port 8000 (see `web/vite.config.ts`).

## 3. Tests

```bash
cd edge
pytest                 # unit + contract tests; hardware-needing ones auto-skip
ruff check .           # lint
```

```bash
cd web
npm run lint && npm run build
```

## What's different from the Pi

| Boundary | dev profile | pi profile |
|----------|-------------|-----------|
| Camera | Synthetic scene or webcam (OpenCV) | Picamera2 / IMX500 |
| Detector | Scripted mock (or HOG on webcam) | YOLOv8s on Hailo-8 |
| Identifier | Pretend mode unless key set | Claude Vision API |
| Audio | WAVs written to `data/audio-out/` | ALSA → speaker |

Pi bring-up: [setup-pi.md](setup-pi.md).
