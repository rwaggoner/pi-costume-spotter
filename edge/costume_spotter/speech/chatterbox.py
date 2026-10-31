"""Chatterbox TTS engine: a natural-sounding voice from the local GPU voice server.

Chatterbox Turbo (Resemble AI, MIT license) sounds far more human than Piper,
but it needs an NVIDIA GPU and PyTorch, so it runs as a separate process with
its own virtual environment (speech/chatterbox_server.py, built by
deploy/windows/setup-chatterbox.ps1). This engine is the app's side of that: it
starts the server when CHATTERBOX_PYTHON is set, then sends it text over
localhost HTTP and gets WAV back.

**Never slower than Piper by much, never silent.** Every request has a deadline
(CHATTERBOX_TIMEOUT_SECONDS). If the server is still loading (the model takes
10-30 s at startup), down, or too slow, the line is spoken by the fallback
engine (Piper when PIPER_VOICE_PATH is set) instead, and once an utterance has
fallen back it stays on the fallback, so one greeting is never two voices.

**Speaking starts after the first sentence.** ``synthesize_parts`` yields the
first sentence on its own, then the rest: SpeechService plays the first part
while the rest is being made, so a group greeting with shout-outs doesn't wait
for the whole paragraph.
"""

import json
import logging
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

from costume_spotter.speech.base import TtsEngine

logger = logging.getLogger(__name__)

SERVER_SCRIPT = Path(__file__).with_name("chatterbox_server.py")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def split_first_sentence(text: str) -> list[str]:
    """['first sentence', 'everything else'], or [text] when it's one sentence.

    A very short first sentence ("Boo!") stays joined to the next one: each
    request has fixed overhead, and a lone word would sound clipped.
    """
    text = " ".join(text.split())
    parts = _SENTENCE_END.split(text)
    first, rest = parts[0], parts[1:]
    while rest and len(first.split()) < 3:
        first = f"{first} {rest.pop(0)}"
    return [first, " ".join(rest)] if rest else [first]


class ChatterboxTtsEngine(TtsEngine):
    name = "chatterbox"

    def __init__(self, url: str, fallback: TtsEngine | None, *,
                 timeout_seconds: float = 4.0, server_python: Path | None = None,
                 voice_clip: Path | None = None, log_dir: Path | None = None) -> None:
        self._url = url.rstrip("/")
        self._fallback = fallback
        self._timeout = timeout_seconds
        self._ready = False  # set once /health answers; cleared on connection errors
        self._process: subprocess.Popen | None = None
        if server_python is not None:
            self._process = self._start_server(Path(server_python), voice_clip, log_dir)

    # -- the server process ------------------------------------------------------

    def _start_server(self, python: Path, voice_clip: Path | None,
                      log_dir: Path | None) -> subprocess.Popen:
        if not python.is_file():
            raise RuntimeError(f"CHATTERBOX_PYTHON not found: {python} - run "
                               "edge\\deploy\\windows\\setup-chatterbox.ps1 first")
        port = self._url.rsplit(":", 1)[-1].split("/")[0]
        command = [str(python), str(SERVER_SCRIPT), "--port", port]
        if voice_clip is not None:
            if not Path(voice_clip).is_file():
                raise RuntimeError(f"CHATTERBOX_VOICE_CLIP not found: {voice_clip}")
            command += ["--voice-clip", str(voice_clip)]
        log_path = Path(log_dir or ".") / "chatterbox.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(log_path, "ab")  # noqa: SIM115 — owned by the child for its lifetime
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        logger.info("starting the Chatterbox voice server (log: %s); "
                    "Piper speaks until it's ready", log_path)
        return subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                cwd=str(log_path.parent), creationflags=flags,
                                # TQDM_DISABLE: no per-step progress bars filling the log
                                env={**os.environ, "PYTHONUNBUFFERED": "1", "TQDM_DISABLE": "1"})

    def close(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def is_ready(self) -> bool:
        if self._ready:
            return True
        if self._process is not None and self._process.poll() is not None:
            return False  # it exited; chatterbox.log says why
        try:
            with urllib.request.urlopen(f"{self._url}/health", timeout=0.5) as reply:
                info = json.loads(reply.read())
        except (OSError, ValueError):
            return False
        self._ready = bool(info.get("ok"))
        if self._ready:
            logger.info("Chatterbox voice ready: %s, voice %s", info.get("gpu"), info.get("voice"))
        return self._ready

    # -- speech ------------------------------------------------------------------

    def synthesize(self, text: str) -> bytes:
        """The whole text as one clip (SpeechService uses synthesize_parts)."""
        return self._one(" ".join(text.split()), [False])

    def synthesize_parts(self, text: str) -> Iterator[bytes]:
        fell_back = [False]  # shared by the parts of this utterance
        for part in split_first_sentence(text):
            yield self._one(part, fell_back)

    def _one(self, text: str, fell_back: list[bool]) -> bytes:
        if not fell_back[0] and self.is_ready():
            try:
                return self._request(text)
            except Exception as exc:  # noqa: BLE001 — any failure: the fallback speaks
                logger.warning("Chatterbox failed (%s); using %s", exc, self._fallback_name)
                if isinstance(exc, urllib.error.URLError) and not isinstance(
                        exc, urllib.error.HTTPError):
                    self._ready = False  # unreachable: re-check health next time
        fell_back[0] = True
        if self._fallback is None:
            raise RuntimeError("Chatterbox is not ready and no fallback voice is set "
                               "(set PIPER_VOICE_PATH)")
        return self._fallback.synthesize(text)

    @property
    def _fallback_name(self) -> str:
        return self._fallback.name if self._fallback else "nothing"

    def _request(self, text: str) -> bytes:
        request = urllib.request.Request(
            f"{self._url}/speak", data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=self._timeout) as reply:
            wav = reply.read()
        if wav[:4] != b"RIFF":
            raise RuntimeError("the voice server did not return a WAV")
        return wav
