"""SpeechService: serialization, engine output, and never-fatal failure (04-F3/F5/F6)."""

import wave
from io import BytesIO

from costume_spotter.events import CommentSpoken, CostumeIdentified
from costume_spotter.events.events import BoundingBox
from costume_spotter.speech import SpeechService
from costume_spotter.speech.base import AudioPlayer, TtsEngine
from costume_spotter.speech.null import NullTtsEngine
from tests.conftest import drain


def identified(sighting_id: str, comment: str = "Nice costume!") -> CostumeIdentified:
    return CostumeIdentified(
        sighting_id=sighting_id, visitor_id=1, costume="witch", confidence="high",
        comment=comment, source="pretend", snapshot_jpeg=b"x",
        box=BoundingBox(0, 0, 10, 10), detector="mock",
    )


class RecordingPlayer(AudioPlayer):
    def __init__(self) -> None:
        self.played: list[bytes] = []

    def play(self, wav_bytes: bytes) -> None:
        self.played.append(wav_bytes)


async def test_speaks_and_reports(bus):
    player = RecordingPlayer()
    SpeechService(bus, NullTtsEngine(), player)
    spoken_events = []

    async def handler(event):
        spoken_events.append(event)

    bus.subscribe(handler, to=(CommentSpoken,), name="test.collector")
    await bus.start()

    bus.publish(identified("s1"))
    await drain(bus)

    assert len(player.played) == 1
    assert spoken_events[0].spoken is True
    assert spoken_events[0].engine == "null"


async def test_engine_failure_is_reported_not_fatal(bus):  # 04-F5
    class BrokenEngine(TtsEngine):
        name = "broken"

        def synthesize(self, text: str) -> bytes:
            raise RuntimeError("voice model missing")

    player = RecordingPlayer()
    SpeechService(bus, BrokenEngine(), player)
    spoken_events = []

    async def handler(event):
        spoken_events.append(event)

    bus.subscribe(handler, to=(CommentSpoken,), name="test.collector")
    await bus.start()

    bus.publish(identified("s1"))
    await drain(bus)

    assert player.played == []
    assert spoken_events[0].spoken is False  # reported honestly, pipeline alive


def test_null_engine_produces_valid_wav_scaled_to_text():
    short = NullTtsEngine().synthesize("Hi")
    long = NullTtsEngine().synthesize("A much longer comment about a very elaborate costume")
    for wav_bytes in (short, long):
        with wave.open(BytesIO(wav_bytes)) as wav:  # parses = structurally valid
            assert wav.getnchannels() == 1
    assert len(long) > len(short)  # duration tracks text length (see null.py)
