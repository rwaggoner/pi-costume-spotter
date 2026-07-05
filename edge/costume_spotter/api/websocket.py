"""The live event socket: /ws/events (06-F2).

One WebSocket carries every bus event as JSON (minus image bytes — see
``BaseEvent.as_wire_dict``). The React app derives everything live from this
single stream: the scrolling log, detection-box overlay, fps readout, and
status lights. Fan-out: each connected client gets its own bounded queue fed by
one shared bus subscription; a slow client drops old messages rather than
back-pressuring the bus.
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from costume_spotter.events import EventBus
from costume_spotter.events.events import BaseEvent

logger = logging.getLogger(__name__)

router = APIRouter()


class EventBroadcaster:
    """Bridges the bus to any number of WebSocket clients."""

    def __init__(self, bus: EventBus) -> None:
        self._clients: set[asyncio.Queue[dict]] = set()
        # Wildcard subscription: the dashboard wants the whole story.
        bus.subscribe(self._on_event, to=None, name="api.ws_broadcaster", queue_size=128)

    async def _on_event(self, event: BaseEvent) -> None:
        message = event.as_wire_dict()
        for queue in self._clients:
            if queue.full():
                queue.get_nowait()  # same freshness-over-completeness rule as the bus
            queue.put_nowait(message)

    async def serve(self, websocket: WebSocket) -> None:
        await websocket.accept()
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=256)
        self._clients.add(queue)
        try:
            while True:
                await websocket.send_json(await queue.get())
        except WebSocketDisconnect:
            pass
        finally:
            self._clients.discard(queue)


@router.websocket("/ws/events")
async def events_socket(websocket: WebSocket) -> None:
    broadcaster: EventBroadcaster = websocket.app.state.event_broadcaster
    await broadcaster.serve(websocket)
