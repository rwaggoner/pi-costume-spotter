"""Piper TTS engine: local, offline, free — the default voice (ADR-005).

Runs the ``piper`` CLI as a subprocess rather than importing piper's Python
bindings: the CLI is the stable, documented surface, it keeps the ONNX runtime
out of our process (a crash there can't take down the pipeline), and a
subprocess per comment is trivially cheap at "a few visitors per minute" scale.
"""

import shutil
import subprocess

from costume_spotter.speech.base import TtsEngine


class PiperTtsEngine(TtsEngine):
    """Text → WAV via the piper CLI and a local voice model (docs/setup-pi.md §5)."""

    name = "piper"

    def __init__(self, voice_path: str) -> None:
        if shutil.which("piper") is None:  # fail fast at wiring time, not first visitor
            raise RuntimeError("TTS_ENGINE=piper but the `piper` CLI is not on PATH "
                               "(pip install piper-tts)")
        self._voice_path = str(voice_path)

    def synthesize(self, text: str) -> bytes:
        # --output-file - writes the WAV to stdout; text goes in on stdin.
        result = subprocess.run(
            ["piper", "--model", self._voice_path, "--output-file", "-"],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0 or not result.stdout:
            raise RuntimeError(f"piper failed: {result.stderr.decode(errors='replace')[:200]}")
        return result.stdout
