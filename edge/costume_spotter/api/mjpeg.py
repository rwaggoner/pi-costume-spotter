"""The MJPEG live stream: /stream.mjpg (06-F1).

MJPEG is a multipart HTTP response where each part is a JPEG; browsers render it
in a plain <img> tag with no client code. Why this instead of WebRTC is
docs/decisions/007-mjpeg-vs-webrtc.md. Each connected viewer runs this generator
independently, all pulling the same shared LatestFrame — a slow viewer skips
frames rather than lagging behind (next_frame always returns the newest).
"""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from costume_spotter.api.state import LatestFrame

_BOUNDARY = "costume-spotter-frame"

router = APIRouter()


async def _frame_parts(latest: LatestFrame, request: Request) -> AsyncIterator[bytes]:
    while not await request.is_disconnected():
        jpeg = await latest.next_frame()
        yield (
            f"--{_BOUNDARY}\r\n"
            f"Content-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n"
        ).encode() + jpeg + b"\r\n"


@router.get("/stream.mjpg")
async def mjpeg_stream(request: Request) -> StreamingResponse:
    latest: LatestFrame = request.app.state.latest_frame
    return StreamingResponse(
        _frame_parts(latest, request),
        media_type=f"multipart/x-mixed-replace; boundary={_BOUNDARY}",
        # Defeat any proxy buffering between the Pi and the browser.
        headers={"Cache-Control": "no-store"},
    )
