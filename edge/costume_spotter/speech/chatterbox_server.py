"""Chatterbox voice server: a small local HTTP service the app asks for speech.

Runs in its OWN virtual environment (edge/.venv-chatterbox), not the app's:
Chatterbox needs PyTorch (2+ GB) and exact versions of transformers, diffusers
and numpy that would fight the app's dependencies. So this file imports nothing
from costume_spotter, only the standard library plus chatterbox/torch, and is run
as a script:

    edge\\.venv-chatterbox\\Scripts\\python.exe costume_spotter\\speech\\chatterbox_server.py

The app starts it automatically when CHATTERBOX_PYTHON is set
(speech/chatterbox.py); setup-chatterbox.ps1 builds the environment. Modes:

    (no flag)  load Chatterbox Turbo on the GPU and serve on 127.0.0.1:8010
    --check    report Python/PyTorch/GPU support and exit (no model download)
    --bench    load the model, time some porch-length lines, save a sample WAV

API (localhost only):
    GET  /health  -> {"ok": true, "device": "cuda", "gpu": "...", "voice": "..."}
    POST /speak   {"text": "..."} -> audio/wav (16-bit mono)

The server only starts listening once the model is loaded and warmed up, so
"connection refused" means "not ready yet": the app speaks with Piper meanwhile.
"""

import argparse
import io
import json
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_PORT = 8010
MAX_TEXT = 600  # characters; a group greeting plus shout-outs is ~250

BENCH_LINES = (
    "Boo! Welcome, little ghost!",
    "A vampire, a witch and a T-Rex! Step right up for treats.",
    "Spider-Man and his pumpkin pup! Swing on by. Your web-slinging is spot on. "
    "Cutest gourd on the block!",
)


def check() -> int:
    """Print what this environment can do; exit 1 if it can't use the GPU."""
    print(f"python  {sys.version.split()[0]}")
    try:
        import torch
    except ImportError:
        print("torch   NOT INSTALLED")
        return 1
    print(f"torch   {torch.__version__} (CUDA {torch.version.cuda})")
    if not torch.cuda.is_available():
        print("gpu     none usable: CUDA is not available to PyTorch "
              "(CPU-only build, or no NVIDIA driver)")
        return 1
    major, minor = torch.cuda.get_device_capability(0)
    arch = f"sm_{major}{minor}"
    supported = torch.cuda.get_arch_list()
    print(f"gpu     {torch.cuda.get_device_name(0)} ({arch})")
    if arch not in supported:
        # RTX 50-series (sm_120) needs a PyTorch built for CUDA 12.8 or newer.
        print(f"FAIL    this PyTorch has no kernels for {arch} (has: {' '.join(supported)})")
        return 1
    try:
        import chatterbox  # noqa: F401
    except ImportError as exc:
        print(f"FAIL    chatterbox is not importable: {exc}")
        return 1
    print("OK      ready for Chatterbox on the GPU")
    return 0


class Voice:
    """Chatterbox Turbo, loaded once, one synthesis at a time."""

    def __init__(self, device: str, voice_clip: Path | None) -> None:
        import torch
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        if device == "cuda" and not torch.cuda.is_available():
            raise SystemExit("CUDA is not available; run with --check to see why")
        started = time.perf_counter()
        self._model = ChatterboxTurboTTS.from_pretrained(device=device)
        if voice_clip is not None:
            # Done once here: generate(audio_prompt_path=...) would redo it per line.
            self._model.prepare_conditionals(str(voice_clip))
        elif self._model.conds is None:
            raise SystemExit("this Chatterbox download has no built-in voice; "
                             "set CHATTERBOX_VOICE_CLIP to a 10-second WAV")
        self._lock = threading.Lock()
        self.sample_rate = self._model.sr
        self.device = device
        self.gpu = torch.cuda.get_device_name(0) if device == "cuda" else "cpu"
        self.voice = voice_clip.name if voice_clip else "built-in"
        self.speak("Hello there.")  # warm-up: the first run compiles GPU kernels
        print(f"model ready in {time.perf_counter() - started:.1f} s "
              f"({self.gpu}, voice: {self.voice})", flush=True)

    def speak(self, text: str) -> bytes:
        import numpy as np

        with self._lock:
            audio = self._model.generate(text)
        samples = np.clip(audio.squeeze(0).numpy(), -1.0, 1.0)
        return to_wav((samples * 32767).astype("<i2").tobytes(), self.sample_rate)


def to_wav(pcm16: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm16)
    return buf.getvalue()


def wav_seconds(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes)) as clip:
        return clip.getnframes() / clip.getframerate()


def make_handler(voice):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — http.server naming
            if self.path != "/health":
                self.send_error(404)
                return
            self._send(200, "application/json", json.dumps({
                "ok": True, "device": voice.device, "gpu": voice.gpu,
                "voice": voice.voice}).encode())

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/speak":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                text = str(json.loads(self.rfile.read(length))["text"]).strip()[:MAX_TEXT]
                if not text:
                    raise ValueError("empty text")
            except (ValueError, KeyError, TypeError) as exc:
                self._send(400, "text/plain", f"bad request: {exc}".encode())
                return
            started = time.perf_counter()
            try:
                wav = voice.speak(text)
            except Exception as exc:  # noqa: BLE001 — report, keep serving
                self._send(500, "text/plain", f"synthesis failed: {exc}".encode())
                return
            took = time.perf_counter() - started
            print(f"spoke {wav_seconds(wav):.1f} s of audio in {took:.2f} s: {text[:60]!r}",
                  flush=True)
            self._send(200, "audio/wav", wav)

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:  # one line per request is printed above
            pass

    return Handler


def bench(voice: Voice) -> None:
    print("\nseconds to make each line (lower is better; under ~1.5 s feels instant):")
    for text in BENCH_LINES:
        times, wav = [], b""
        for _ in range(3):
            started = time.perf_counter()
            wav = voice.speak(text)
            times.append(time.perf_counter() - started)
        took = sorted(times)[1]  # median of 3
        audio = wav_seconds(wav)
        print(f"  {took:5.2f} s for {audio:4.1f} s of speech "
              f"(x{audio / took:.1f} real time): {text[:50]!r}")
    sample = Path("chatterbox-sample.wav").resolve()
    sample.write_bytes(wav)
    print(f"\nlast line saved to {sample} - play it to hear the voice")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--device", default="cuda", choices=("cuda", "cpu"))
    parser.add_argument("--voice-clip", type=Path, default=None,
                        help="WAV of the voice to copy (5+ seconds, one speaker)")
    parser.add_argument("--check", action="store_true", help="check the GPU setup and exit")
    parser.add_argument("--bench", action="store_true", help="time some lines and exit")
    args = parser.parse_args()

    if args.check:
        return check()
    if args.voice_clip is not None and not args.voice_clip.is_file():
        print(f"voice clip not found: {args.voice_clip}", file=sys.stderr)
        return 1
    voice = Voice(args.device, args.voice_clip)
    if args.bench:
        bench(voice)
        return 0
    server = ThreadingHTTPServer((args.host, args.port), make_handler(voice))
    print(f"listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
