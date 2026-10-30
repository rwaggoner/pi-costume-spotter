"""Piper TTS engine: local, offline, free — the default voice (ADR-005).

**Voice kept loaded (in-process).** Loading the voice model takes ~1.5-2 s;
synthesizing a sentence with it already loaded takes ~0.3-0.5 s. The original
design ran the ``piper`` CLI once per comment, paying the load every time, and
that was the single biggest delay between a visitor arriving and the porch
speaking. So the engine now loads ``PiperVoice`` once at startup (plus a tiny
warm-up synthesis, so the first visitor doesn't pay ONNX Runtime's first-run
cost) and reuses it.

The trade-off is isolation: a crash inside piper's ONNX runtime would now take
the app down instead of one subprocess. In practice synthesis errors surface as
Python exceptions, which SpeechService already turns into a non-fatal
``CommentSpoken(spoken=False)`` (04-F5).

**CLI fallback.** If the ``piper`` Python package isn't importable but a
``piper`` executable is on PATH, the engine falls back to one subprocess per
comment. It passes text and WAV through files rather than pipes: piper's
``--output-file -`` re-opens a locked temp file (fails on Windows), and stdin
is decoded with the console code page there (ADR-010).
"""

import importlib.util
import io
import shutil
import subprocess
import sys
import tempfile
import threading
import wave
from pathlib import Path

from costume_spotter.speech.base import TtsEngine


def piper_command() -> list[str] | None:
    """How to launch the piper CLI here, or None if it isn't installed."""
    if importlib.util.find_spec("piper") is not None:
        return [sys.executable, "-m", "piper"]
    if shutil.which("piper") is not None:
        return ["piper"]
    return None


class PiperTtsEngine(TtsEngine):
    """Text → WAV via piper and a local voice model (docs/setup-pi.md §5,
    docs/setup-windows.md §4)."""

    name = "piper"

    def __init__(self, voice_path: str, in_process: bool | None = None) -> None:
        """``in_process``: None = keep the voice loaded when the piper package is
        importable, else use the CLI; True/False forces one (tests use False)."""
        if not Path(voice_path).is_file():
            raise RuntimeError(f"PIPER_VOICE_PATH not found: {voice_path} — download a voice "
                               "with: python -m piper.download_voices en_US-lessac-medium")
        self._voice_path = str(voice_path)
        if in_process is None:
            in_process = importlib.util.find_spec("piper") is not None
        self._voice = None
        self._lock = threading.Lock()  # PiperVoice isn't documented as thread-safe

        if in_process:
            from piper import PiperVoice

            self._voice = PiperVoice.load(self._voice_path)
            self.synthesize("Hello.")  # warm-up: the first ONNX run is the slow one
        else:
            command = piper_command()
            if command is None:  # fail fast at wiring time, not first visitor
                raise RuntimeError("TTS_ENGINE=piper but piper is not installed "
                                   "(pip install piper-tts)")
            self._command = command

    def synthesize(self, text: str) -> bytes:
        if self._voice is not None:
            return self._synthesize_in_process(text)
        return self._synthesize_cli(text)

    def _synthesize_in_process(self, text: str) -> bytes:
        buf = io.BytesIO()
        with self._lock, wave.open(buf, "wb") as wav_file:
            self._voice.synthesize_wav(" ".join(text.split()), wav_file)
        return buf.getvalue()

    def _synthesize_cli(self, text: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="piper-") as tmp:
            text_path = Path(tmp) / "in.txt"
            wav_path = Path(tmp) / "out.wav"
            # One line: piper inserts sentence silence between input lines.
            text_path.write_text(" ".join(text.split()), encoding="utf-8")
            result = subprocess.run(
                [*self._command, "--model", self._voice_path,
                 "--input-file", str(text_path), "--output-file", str(wav_path)],
                capture_output=True,
                timeout=60,  # first call loads the model; slow PCs need headroom
            )
            if result.returncode != 0 or not wav_path.is_file():
                raise RuntimeError(
                    f"piper failed: {result.stderr.decode(errors='replace')[-300:]}"
                )
            return wav_path.read_bytes()
