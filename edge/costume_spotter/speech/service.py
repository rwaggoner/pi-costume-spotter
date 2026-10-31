"""The speech subscriber: GreetingReady → synthesize → play → CommentSpoken.

One GreetingReady per group of visitors (04-F9): a lone visitor's comment, or a
group greeting followed by short shout-outs. The whole thing is synthesized as
ONE utterance, so a group never waits behind a queue of separate clips.

The queueing rules of requirements 04 fall out of the bus's design rather than
needing bespoke machinery:

- **One at a time (04-F3):** the bus runs ONE consumer task per subscription,
  and this handler doesn't return until playback finishes — so comments are
  strictly serialized.
- **Drop stale, keep fresh (04-F4):** the subscription's bounded queue is sized
  to SPEECH_QUEUE_MAX, and a full bus queue sheds the OLDEST event. A comment
  about someone who wandered off 40 seconds ago is worse than silence. Because
  a whole group is one event, the members of a group are never dropped
  individually.
- **Never fatal (04-F5):** any engine/player failure publishes
  ``CommentSpoken(spoken=False)`` and the pipeline rolls on.

An optional ``audio_filter`` (e.g. the spooky voice, issue #15) transforms the
WAV between synthesis and playback; it's expected to be non-fatal itself
(returning audio unchanged on failure), but a raise here still degrades safely
via the same 04-F5 handler.
"""

import asyncio
import logging

from costume_spotter.events import CommentSpoken, EventBus, GreetingReady, SystemStatus
from costume_spotter.events.events import BaseEvent
from costume_spotter.speech.base import AudioPlayer, TtsEngine

logger = logging.getLogger(__name__)


class SpeechService:
    """Speaks each identified costume's comment through the configured engine."""

    def __init__(self, bus: EventBus, engine: TtsEngine, player: AudioPlayer,
                 queue_max: int = 3, audio_filter=None) -> None:
        self._bus = bus
        self._engine = engine
        self._player = player
        self._filter = audio_filter  # optional WAV→WAV transform (e.g. SpookyVoice)
        bus.subscribe(self.on_greeting, to=(GreetingReady,),
                      name="speech.service", queue_size=queue_max)

    async def on_greeting(self, event: BaseEvent) -> None:
        assert isinstance(event, GreetingReady)
        spoken = False
        try:
            # Synthesis and playback are blocking (subprocess / network / ALSA);
            # to_thread keeps the loop responsive (04-N3). Serialization is
            # preserved because *this handler* awaits completion before the bus
            # hands it the next event.
            #
            # An engine may hand the speech over in parts (synthesize_parts):
            # each part plays while the next is synthesized, so a slow engine
            # starts talking after its first sentence.
            parts = self._engine.synthesize_parts(event.text)
            wav = await asyncio.to_thread(next, parts, None)
            first = True
            while wav is not None:
                if self._filter is not None:
                    wav = await asyncio.to_thread(self._filter_part, wav, first)
                playing = asyncio.create_task(asyncio.to_thread(self._player.play, wav))
                try:
                    wav = await asyncio.to_thread(next, parts, None)
                finally:
                    await playing  # never leave a clip playing behind an error
                first = False
            spoken = True
            self._bus.publish(SystemStatus(component="speech", ok=True))
        except Exception as exc:
            logger.warning("speech failed for group %s: %s", event.group_id, exc)
            self._bus.publish(SystemStatus(component="speech", ok=False, detail=str(exc)))
        self._publish_spoken(event, spoken)

    def _filter_part(self, wav: bytes, first: bool) -> bytes:
        # Later parts of one utterance keep the first part's effect (the spooky
        # voice rotates presets per utterance, not per clip).
        if not first and getattr(self._filter, "supports_continuing", False):
            return self._filter.apply(wav, continuing=True)
        return self._filter.apply(wav)

    def _publish_spoken(self, event: GreetingReady, spoken: bool) -> None:
        # One CommentSpoken per sighting, so storage marks every member spoken (04-F6).
        for sighting_id in event.sighting_ids:
            self._bus.publish(CommentSpoken(
                sighting_id=sighting_id,
                text=event.text,
                engine=self._engine.name,
                spoken=spoken,
            ))
