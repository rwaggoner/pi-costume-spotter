"""Piper TTS engine: local, offline, free — the default voice (ADR-005).

Runs piper as a subprocess rather than calling its Python API: the CLI is the
stable, documented surface, it keeps the ONNX runtime out of our process (a
crash there can't take down the pipeline), and a subprocess per comment is
trivially cheap at "a few visitors per minute" scale.

Portability (ADR-010), learned the hard way on Windows:

- **Launcher.** Prefer ``python -m piper`` with *our* interpreter. That works
  when the app is started as ``.venv\\Scripts\\python.exe -m costume_spotter``
  from Task Scheduler, where the venv was never "activated" and the ``piper``
  script is not on PATH. The bare ``piper`` CLI is the fallback.
- **Files, not pipes.** Piper's ``--output-file -`` (WAV to stdout) re-opens a
  still-open temp file by name, which Windows forbids, and stdin text is decoded
  with the console code page there. So text goes in via a UTF-8 file and the WAV
  comes back via a file — identical behavior on every OS.
"""

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from costume_spotter.speech.base import TtsEngine


def piper_command() -> list[str] | None:
    """How to launch piper here, or None if it isn't installed."""
    if importlib.util.find_spec("piper") is not None:
        return [sys.executable, "-m", "piper"]
    if shutil.which("piper") is not None:
        return ["piper"]
    return None


class PiperTtsEngine(TtsEngine):
    """Text → WAV via piper and a local voice model (docs/setup-pi.md §5,
    docs/setup-windows.md §4)."""

    name = "piper"

    def __init__(self, voice_path: str) -> None:
        command = piper_command()
        if command is None:  # fail fast at wiring time, not first visitor
            raise RuntimeError("TTS_ENGINE=piper but piper is not installed "
                               "(pip install piper-tts)")
        if not Path(voice_path).is_file():
            raise RuntimeError(f"PIPER_VOICE_PATH not found: {voice_path} — download a voice "
                               "with: python -m piper.download_voices en_US-lessac-medium")
        self._command = command
        self._voice_path = str(voice_path)

    def synthesize(self, text: str) -> bytes:
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
