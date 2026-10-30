"""SpeechService: serialization, engine output, and never-fatal failure (04-F3/F5/F6)."""

import wave
from io import BytesIO

from costume_spotter.events import CommentSpoken, GreetingReady
from costume_spotter.speech import SpeechService
from costume_spotter.speech.base import AudioPlayer, TtsEngine
from costume_spotter.speech.null import NullTtsEngine
from tests.conftest import drain


def identified(sighting_id: str, comment: str = "Nice costume!") -> GreetingReady:
    """A lone visitor's greeting: one sighting."""
    return GreetingReady(group_id=f"g-{sighting_id}", text=comment, sighting_ids=(sighting_id,))


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


async def test_audio_filter_transforms_wav_before_playback(bus):  # issue #15
    """The optional filter (e.g. SpookyVoice) runs between synthesis and play."""
    class UppercaseFilter:  # a trivial stand-in for the spooky filter
        def apply(self, wav: bytes) -> bytes:
            return b"FILTERED:" + wav

    player = RecordingPlayer()
    SpeechService(bus, NullTtsEngine(), player, audio_filter=UppercaseFilter())
    await bus.start()

    bus.publish(identified("s1"))
    await drain(bus)

    assert len(player.played) == 1
    assert player.played[0].startswith(b"FILTERED:")  # the filter's output reached the player
    await bus.stop()


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


async def test_a_group_is_one_utterance_and_every_sighting_is_marked(bus):  # 04-F9
    player = RecordingPlayer()
    SpeechService(bus, NullTtsEngine(), player)
    spoken: list = []

    async def handler(event):
        spoken.append(event)

    bus.subscribe(handler, to=(CommentSpoken,), name="test.collector")
    await bus.start()
    bus.publish(GreetingReady(group_id="g", text="Hi crew! Boo! Meow!",
                              sighting_ids=("a", "b", "c")))
    await drain(bus)

    assert len(player.played) == 1  # one clip for the whole group
    assert [e.sighting_id for e in spoken] == ["a", "b", "c"]
    assert all(e.spoken and e.text == "Hi crew! Boo! Meow!" for e in spoken)
    await bus.stop()


def test_null_engine_produces_valid_wav_scaled_to_text():
    short = NullTtsEngine().synthesize("Hi")
    long = NullTtsEngine().synthesize("A much longer comment about a very elaborate costume")
    for wav_bytes in (short, long):
        with wave.open(BytesIO(wav_bytes)) as wav:  # parses = structurally valid
            assert wav.getnchannels() == 1
    assert len(long) > len(short)  # duration tracks text length (see null.py)
