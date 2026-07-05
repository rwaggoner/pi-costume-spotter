"""REST endpoints (06-F3): sighting history, snapshots, stats, health.

Response models are explicit Pydantic classes rather than raw dicts: they are
the contract the React app's ``web/src/api/types.ts`` mirrors, and FastAPI turns
them into the OpenAPI docs at /docs.
"""

import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api")


class SightingOut(BaseModel):
    id: str
    spotted_at: datetime
    costume: str | None
    confidence: str
    comment: str
    spoken: bool
    has_snapshot: bool
    detector: str
    source: str
    box: dict


class SightingsPage(BaseModel):
    sightings: list[SightingOut]
    limit: int
    offset: int


@router.get("/sightings", response_model=SightingsPage)
async def list_sightings(request: Request, limit: int = Query(50, ge=1, le=200),
                         offset: int = Query(0, ge=0)) -> SightingsPage:
    # Repository calls are sync SQLite; keep them off the loop (see repository.py).
    records = await asyncio.to_thread(request.app.state.repository.recent, limit, offset)
    return SightingsPage(
        sightings=[
            SightingOut(
                id=r.id, spotted_at=r.spotted_at, costume=r.costume,
                confidence=r.confidence, comment=r.comment, spoken=r.spoken,
                has_snapshot=r.snapshot_file is not None, detector=r.detector,
                source=r.source, box=r.box,
            )
            for r in records
        ],
        limit=limit,
        offset=offset,
    )


@router.get("/sightings/{sighting_id}/snapshot")
async def sighting_snapshot(request: Request, sighting_id: str) -> FileResponse:
    record = await asyncio.to_thread(request.app.state.repository.get, sighting_id)
    if record is None or record.snapshot_file is None:
        raise HTTPException(404, "no snapshot for this sighting")
    path = request.app.state.snapshots.path_for(record.snapshot_file)
    if path is None:  # row exists but the file was pruned or retention is off
        raise HTTPException(404, "snapshot no longer available")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/stats")
async def stats(request: Request) -> dict:
    return await asyncio.to_thread(request.app.state.repository.stats)


@router.get("/health")
async def health(request: Request) -> dict:
    """Component heartbeats + bus queue stats — the dashboard's status header
    and the first place to look when something misbehaves (see docs/setup-pi.md)."""
    return {
        "components": request.app.state.health.snapshot(),
        "stream_fps": request.app.state.latest_frame.fps,
        "bus": request.app.state.bus.stats(),
    }
