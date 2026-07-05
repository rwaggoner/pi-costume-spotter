"""The speech subscriber: CostumeIdentified → synthesize → play → CommentSpoken.

The queueing rules of requirements 04 fall out of the bus's design rather than
needing bespoke machinery:

- **One at a time (04-F3):** the bus runs ONE consumer task per subscription,
  and this handler doesn't return until playback finishes — so comments are
  strictly serialized.
- **Drop stale, keep fresh (04-F4):** the subscription's bounded queue is sized
  to SPEECH_QUEUE_MAX, and a full bus queue sheds the OLDEST event. A comment
  about someone who wandered off 40 seconds ago is worse than silence.
- **Never fatal (04-F5):** any engine/player failure publishes
  ``CommentSpoken(spoken=False)`` and the pipeline rolls on.
"""

import asyncio
import logging

from costume_spotter.events import CommentSpoken, CostumeIdentified, EventBus, SystemStatus
from costume_spotter.events.events import BaseEvent
from costume_spotter.speech.base import AudioPlayer, TtsEngine

logger = logging.getLogger(__name__)


class SpeechService:
    """Speaks each identified costume's comment through the configured engine."""

    def __init__(self, bus: EventBus, engine: TtsEngine, player: AudioPlayer,
                 queue_max: int = 3) -> None:
        self._bus = bus
        self._engine = engine
        self._player = player
        bus.subscribe(self.on_costume_identified, to=(CostumeIdentified,),
                      name="speech.service", queue_size=queue_max)

    async def on_costume_identified(self, event: BaseEvent) -> None:
        assert isinstance(event, CostumeIdentified)
        spoken = False
        try:
            # Synthesis and playback are blocking (subprocess / network / ALSA);
            # to_thread keeps the loop responsive (04-N3). Serialization is
            # preserved because *this handler* awaits completion before the bus
            # hands it the next event.
            wav = await asyncio.to_thread(self._engine.synthesize, event.comment)
            await asyncio.to_thread(self._player.play, wav)
            spoken = True
            self._bus.publish(SystemStatus(component="speech", ok=True))
        except Exception as exc:
            logger.warning("speech failed for sighting %s: %s", event.sighting_id, exc)
            self._bus.publish(SystemStatus(component="speech", ok=False, detail=str(exc)))
        self._bus.publish(CommentSpoken(
            sighting_id=event.sighting_id,
            text=event.comment,
            engine=self._engine.name,
            spoken=spoken,
        ))
