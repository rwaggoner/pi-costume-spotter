"""The speech ports: TtsEngine (text → WAV) and AudioPlayer (WAV → sound)."""

from abc import ABC, abstractmethod
from collections.abc import Iterator


class TtsEngine(ABC):
    """Synthesizes speech.

    Contract: ``synthesize`` returns a complete WAV file as bytes (PCM 16-bit).
    The interface normalizes on WAV so players don't care which engine ran —
    e.g. Google TTS is asked for LINEAR16 rather than its default MP3
    (the abstraction must not leak engine quirks; ADR-005).
    Called from a worker thread; may block for the duration of synthesis.
    """

    name: str = "unknown"

    @abstractmethod
    def synthesize(self, text: str) -> bytes: ...

    def synthesize_parts(self, text: str) -> Iterator[bytes]:
        """The same speech as one or more WAV clips, in order, made lazily.

        SpeechService plays each clip while the next one is synthesized, so a
        slow engine can start talking after its first sentence. The default is
        one clip; engines where that wait matters (Chatterbox) override it.
        """
        yield self.synthesize(text)

    def close(self) -> None:
        """Release resources (e.g. a helper process) at shutdown."""


class AudioPlayer(ABC):
    """Plays one WAV clip to completion. Blocking; called from a worker thread."""

    @abstractmethod
    def play(self, wav_bytes: bytes) -> None: ...
