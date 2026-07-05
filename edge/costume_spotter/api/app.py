"""FastAPI application assembly.

``create_app`` receives already-constructed collaborators (bus, repository, …)
from the composition root — the API layer wires nothing itself, it only exposes.
That keeps this module trivially testable: tests pass in fakes.

In production the same app also serves the built React bundle (06-F4), so the
Pi exposes exactly one port. In development the Vite dev server runs separately
and proxies to this app (06-F5).
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from costume_spotter.api import mjpeg, routes, websocket
from costume_spotter.api.state import HealthRegistry, LatestFrame
from costume_spotter.config import Settings
from costume_spotter.events import EventBus, FrameProcessed, SystemStatus
from costume_spotter.storage import SightingRepository, SnapshotStore

# The React build lands here (web/vite.config.ts is configured to match).
_WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def create_app(settings: Settings, bus: EventBus, repository: SightingRepository,
               snapshots: SnapshotStore) -> FastAPI:
    app = FastAPI(
        title="Costume Spotter",
        description="Edge API: live feed, live events, sighting history.",
        version="0.1.0",
    )

    # Shared live state, kept fresh by bus subscriptions (see api/state.py).
    latest_frame = LatestFrame()
    health = HealthRegistry()
    bus.subscribe(latest_frame.update, to=(FrameProcessed,),
                  name="api.latest_frame", queue_size=2)  # only the newest matters
    bus.subscribe(health.update, to=(SystemStatus,), name="api.health", queue_size=64)

    # Everything routes reach through request.app.state — one obvious junction.
    app.state.bus = bus
    app.state.repository = repository
    app.state.snapshots = snapshots
    app.state.latest_frame = latest_frame
    app.state.health = health
    app.state.event_broadcaster = websocket.EventBroadcaster(bus)

    # 06-F5: allow the Vite dev server origin during development.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(routes.router)
    app.include_router(mjpeg.router)
    app.include_router(websocket.router)

    if _WEB_DIST.is_dir():  # 06-F4: production serves the built dashboard
        app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="dashboard")

    return app
