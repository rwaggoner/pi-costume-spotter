# 06 — Dashboard (Edge API + React UI)

## Purpose

Show what the system is seeing and doing, live: the camera feed with detection boxes,
a scrolling log of events as they happen, and the history/statistics of past
sightings. It runs on the local network (a laptop or wall-mounted tablet pointed at
the Pi).

## Functional requirements — API (FastAPI on the Pi)

| ID | Requirement |
|----|-------------|
| 06-F1 | Serve the live camera feed as MJPEG at `GET /stream.mjpg` ([ADR-007](../decisions/007-mjpeg-vs-webrtc.md)); the stream must serve multiple simultaneous viewers. |
| 06-F2 | Broadcast every bus event as JSON over `WS /ws/events` — this single socket drives the live log, the box overlay, and status indicators. |
| 06-F3 | REST: paginated sightings (`GET /api/sightings`), per-sighting snapshot (`GET /api/sightings/{id}/snapshot`), aggregate stats (`GET /api/stats`), component health (`GET /api/health`). |
| 06-F4 | Serve the built React app as static files in production, so the Pi exposes exactly one port. |
| 06-F5 | CORS enabled for the Vite dev server origin so `npm run dev` on a laptop can hit the Pi's API directly. |

## Functional requirements — React UI

| ID | Requirement |
|----|-------------|
| 06-F6 | **Live feed panel:** MJPEG stream with detection boxes drawn on an HTML canvas overlay from WebSocket data (boxes ride the socket, not burned into the video, so the overlay can be toggled). |
| 06-F7 | **Live event log:** scrolling feed of events with icons and timestamps (visitor spotted → costume identified → comment spoken), newest first, capped in memory. |
| 06-F8 | **Sightings table:** history with snapshot thumbnails, costume, comment, time; paginated from the REST API. |
| 06-F9 | **Stats:** total sightings, sightings today, top costume; bar chart of costume counts. |
| 06-F10 | **Status header:** camera/detector/identifier/speech health from heartbeats; WebSocket auto-reconnects with visible connection state. |

## Non-functional requirements

| ID | Requirement |
|----|-------------|
| 06-N1 | Feed-to-glass latency < 1 s on the LAN (it's a "what's happening now" display). |
| 06-N2 | The UI is a pure API consumer — no server-side rendering, no coupling to Python internals beyond the JSON contracts (typed in `web/src/api/types.ts`, mirroring the FastAPI schemas). |
| 06-N3 | Dashboard load (streaming + WS fan-out) must not reduce detection fps by more than ~10% on the Pi. |
| 06-N4 | No authentication in v1 — LAN-only deployment, documented as future work for any internet exposure. |
