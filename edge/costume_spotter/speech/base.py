"""The speech ports: TtsEngine (text → WAV) and AudioPlayer (WAV → sound)."""

from abc import ABC, abstractmethod


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


class AudioPlayer(ABC):
    """Plays one WAV clip to completion. Blocking; called from a worker thread."""

    @abstractmethod
    def play(self, wav_bytes: bytes) -> None: ...
