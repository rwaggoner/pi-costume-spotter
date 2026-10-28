"""Windows speaker playback via the standard library's ``winsound`` (ADR-010).

The Windows counterpart of aplay.py. ``winsound.PlaySound`` with ``SND_MEMORY``
plays WAV bytes straight from memory and, without ``SND_ASYNC``, blocks until the
clip finishes — exactly the AudioPlayer contract, with nothing to install.

Trade-off: it always plays on the Windows *default* output device, so pick the
porch speaker in Settings > System > Sound. AUDIO_DEVICE is Pi-only (ALSA).
"""

from collections.abc import Callable

from costume_spotter.speech.base import AudioPlayer

# The OS seam: (wav_bytes) -> None, blocking. Tests inject a fake.
PlayFn = Callable[[bytes], None]


def _winsound_play(wav_bytes: bytes) -> None:
    import winsound  # Windows-only module: imported here so other OSes can import this file

    # SND_NODEFAULT: on a bad clip, raise instead of playing the system "ding".
    winsound.PlaySound(wav_bytes, winsound.SND_MEMORY | winsound.SND_NODEFAULT)


class WinsoundAudioPlayer(AudioPlayer):
    """Plays WAV bytes on the default Windows output device."""

    def __init__(self, play: PlayFn | None = None) -> None:
        if play is None:
            try:
                import winsound  # noqa: F401 — fail fast at wiring time (01-F6 spirit)
            except ImportError as exc:
                raise RuntimeError("the winsound audio player only works on Windows "
                                   "(EDGE_PROFILE=windows)") from exc
        self._play = play or _winsound_play

    def play(self, wav_bytes: bytes) -> None:
        if not wav_bytes.startswith(b"RIFF"):  # PlaySound needs a complete WAV file
            raise RuntimeError("winsound player expects WAV bytes (RIFF header missing)")
        self._play(wav_bytes)
