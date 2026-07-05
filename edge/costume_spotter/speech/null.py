"""Dev/CI stand-ins for the speech hardware (04-F7).

``NullTtsEngine`` produces a short valid-but-silent WAV so everything downstream
(players, duration math, file writing) handles real bytes. ``FileAudioPlayer``
"plays" by writing the WAV to a directory — the dev-profile way to verify what
would have come out of the speaker.
"""

import io
import logging
import struct
import time
import wave
from pathlib import Path

from costume_spotter.speech.base import AudioPlayer, TtsEngine

logger = logging.getLogger(__name__)


class NullTtsEngine(TtsEngine):
    """Silence, sized to the text: ~0.06 s per character ≈ natural speech pacing,
    so queue/timing behavior in dev matches reality."""

    name = "null"

    def synthesize(self, text: str) -> bytes:
        sample_rate = 16_000
        n_samples = int(len(text) * 0.06 * sample_rate)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # 16-bit PCM
            wav.setframerate(sample_rate)
            wav.writeframes(struct.pack(f"<{n_samples}h", *([0] * n_samples)))
        return buf.getvalue()


class FileAudioPlayer(AudioPlayer):
    """Writes clips to ``data/audio-out/`` instead of a speaker."""

    def __init__(self, out_dir: Path) -> None:
        self._out_dir = out_dir
        out_dir.mkdir(parents=True, exist_ok=True)

    def play(self, wav_bytes: bytes) -> None:
        path = self._out_dir / f"comment-{int(time.time() * 1000)}.wav"
        path.write_bytes(wav_bytes)
        logger.info("dev audio: wrote %s (%d bytes)", path.name, len(wav_bytes))
