"""ALSA playback on the Pi, via the ``aplay`` CLI.

Same subprocess reasoning as piper.py: aplay ships with alsa-utils, takes WAV on
stdin, and blocks until playback finishes — which is exactly the semantics the
AudioPlayer port wants (the speech service serializes on that blocking).
"""

import shutil
import subprocess

from costume_spotter.speech.base import AudioPlayer


class AplayAudioPlayer(AudioPlayer):
    """Plays WAV bytes on an ALSA device (AUDIO_DEVICE in .env, e.g. plughw:1,0)."""

    def __init__(self, device: str | None = None) -> None:
        if shutil.which("aplay") is None:
            raise RuntimeError("aplay not found — install alsa-utils (docs/setup-pi.md §4)")
        self._device = device

    def play(self, wav_bytes: bytes) -> None:
        cmd = ["aplay", "-q"]
        if self._device:
            cmd += ["-D", self._device]
        result = subprocess.run(cmd, input=wav_bytes, capture_output=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"aplay failed: {result.stderr.decode(errors='replace')[:200]}")
