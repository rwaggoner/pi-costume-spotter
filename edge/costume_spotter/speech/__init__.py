"""Speech: turn comments into audio and play them, one at a time.

Two ports here (docs/decisions/005-tts-strategy.md):
- ``TtsEngine`` — text → WAV bytes (piper | google | null)
- ``AudioPlayer`` — WAV bytes → sound (aplay on the Pi | files in dev)

``service.SpeechService`` owns the queueing rules (04-F3/F4) so they're written
once, outside any engine.
"""

from costume_spotter.speech.service import SpeechService

__all__ = ["SpeechService"]
