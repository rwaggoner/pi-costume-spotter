"""Chatterbox engine + voice server, without a GPU or the model.

The server module is stdlib-only at import time, so its HTTP layer is tested
here with a fake voice; the engine is tested against that real HTTP server,
against nothing (down → Piper fallback), and launching a stand-in server script.
"""

import sys
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

from costume_spotter.events import CommentSpoken, GreetingReady
from costume_spotter.speech import SpeechService, chatterbox
from costume_spotter.speech import chatterbox_server as server
from costume_spotter.speech.base import AudioPlayer, TtsEngine
from costume_spotter.speech.chatterbox import ChatterboxTtsEngine, split_first_sentence
from costume_spotter.speech.spooky import SpookyPreset, SpookyVoice
from tests.conftest import drain


class FakeVoice:
    device, gpu, voice, sample_rate = "cuda", "Fake RTX", "built-in", 24000

    def __init__(self, fail_on: str | None = None) -> None:
        self.spoken: list[str] = []
        self.fail_on = fail_on

    def speak(self, text: str) -> bytes:
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("GPU on fire")
        self.spoken.append(text)
        return server.to_wav(b"\x00\x00" * 2400, self.sample_rate)  # 0.1 s


class Recorder(TtsEngine):
    name = "piper"

    def __init__(self) -> None:
        self.said: list[str] = []

    def synthesize(self, text: str) -> bytes:
        self.said.append(text)
        return b"RIFFpiper:" + text.encode()


@pytest.fixture
def voice_server():
    """A real voice server on a free port, backed by FakeVoice."""
    voice = FakeVoice()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(voice))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", voice
    httpd.shutdown()
    httpd.server_close()


def free_port_url() -> str:
    probe = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(FakeVoice()))
    port = probe.server_address[1]
    probe.server_close()  # nothing listens here now
    return f"http://127.0.0.1:{port}"


# -- splitting ---------------------------------------------------------------

def test_first_sentence_goes_alone_so_speaking_starts_sooner():
    assert split_first_sentence("A vampire and a witch! Fangs out, Count! Great hat!") == [
        "A vampire and a witch!", "Fangs out, Count! Great hat!"]


def test_a_tiny_first_sentence_stays_with_the_next():
    assert split_first_sentence("Boo! Welcome, little ghost. Nice sheet.") == [
        "Boo! Welcome, little ghost.", "Nice sheet."]


def test_one_sentence_is_one_part():
    assert split_first_sentence("  Welcome,\n little ghost!  ") == ["Welcome, little ghost!"]


# -- the server's HTTP layer ----------------------------------------------------

def test_server_health_and_speak(voice_server):
    url, voice = voice_server
    engine = ChatterboxTtsEngine(url, None)
    assert engine.is_ready()
    wav = engine.synthesize("Hello, ghost!")
    assert wav[:4] == b"RIFF" and server.wav_seconds(wav) == pytest.approx(0.1)
    assert voice.spoken == ["Hello, ghost!"]


def test_server_rejects_bad_requests_and_reports_failures():
    import urllib.error
    import urllib.request

    voice = FakeVoice(fail_on="explode")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(voice))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/speak"
    try:
        for body, status in ((b'{"nope": 1}', 400), (b'{"text": "  "}', 400),
                             (b'{"text": "please explode"}', 500)):
            with pytest.raises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST"))
            assert err.value.code == status
    finally:
        httpd.shutdown()
        httpd.server_close()


# -- the engine: fallback rules -----------------------------------------------------

def test_server_down_means_piper_speaks():
    piper = Recorder()
    engine = ChatterboxTtsEngine(free_port_url(), piper)
    assert list(engine.synthesize_parts("Hi there, witch! Great hat!")) == [
        b"RIFFpiper:Hi there, witch!", b"RIFFpiper:Great hat!"]


def test_a_failure_mid_greeting_keeps_the_rest_in_the_same_voice(voice_server):
    url, voice = voice_server
    voice.fail_on = "Great"
    piper = Recorder()
    engine = ChatterboxTtsEngine(url, piper)
    parts = list(engine.synthesize_parts("Hi there, witch! Great hat! Lovely broom!"))
    assert parts[0][:4] == b"RIFF" and b"piper" not in parts[0]  # Chatterbox
    assert piper.said == ["Great hat! Lovely broom!"]  # the rest, all Piper
    # The next greeting tries Chatterbox again (the server itself is fine).
    voice.fail_on = None
    assert b"piper" not in engine.synthesize("Welcome back, friends!")


def test_down_with_no_fallback_is_an_error_speech_service_reports():
    with pytest.raises(RuntimeError, match="PIPER_VOICE_PATH"):
        ChatterboxTtsEngine(free_port_url(), None).synthesize("Hello!")


def test_missing_server_python_fails_at_startup(tmp_path):
    with pytest.raises(RuntimeError, match="setup-chatterbox"):
        ChatterboxTtsEngine(free_port_url(), None, server_python=tmp_path / "python.exe")


def test_engine_starts_and_stops_the_server_process(tmp_path, monkeypatch):
    """CHATTERBOX_PYTHON set: the app launches the server script itself."""
    fake_script = tmp_path / "fake_server.py"
    fake_script.write_text(
        "import sys, threading\n"
        f"sys.path.insert(0, {str(chatterbox.SERVER_SCRIPT.parent)!r})\n"
        "import chatterbox_server as s\n"
        "from tests_fake import FakeVoice\n"
        "from http.server import ThreadingHTTPServer\n"
        "port = int(sys.argv[sys.argv.index('--port') + 1])\n"
        "ThreadingHTTPServer(('127.0.0.1', port), s.make_handler(FakeVoice())).serve_forever()\n")
    (tmp_path / "tests_fake.py").write_text(
        "import chatterbox_server as s\n"
        "class FakeVoice:\n"
        "    device, gpu, voice = 'cuda', 'Fake RTX', 'built-in'\n"
        "    def speak(self, text):\n"
        "        return s.to_wav(b'\\x00\\x00' * 240, 24000)\n")
    monkeypatch.setattr(chatterbox, "SERVER_SCRIPT", fake_script)
    piper = Recorder()
    engine = ChatterboxTtsEngine(free_port_url(), piper, server_python=sys.executable,
                                 log_dir=tmp_path / "logs")
    try:
        deadline = time.monotonic() + 15
        while not engine.is_ready():
            assert time.monotonic() < deadline, (tmp_path / "logs" / "chatterbox.log").read_text()
            time.sleep(0.1)
        assert b"piper" not in engine.synthesize("Hello!")
    finally:
        engine.close()
    assert engine._process.poll() is not None  # noqa: SLF001 — stopped with the app


# -- SpeechService plays parts as they arrive -------------------------------------------

class TwoPartEngine(TtsEngine):
    name = "two-part"

    def __init__(self, log: list) -> None:
        self.log = log

    def synthesize(self, text: str) -> bytes:
        raise AssertionError("SpeechService should use synthesize_parts")

    def synthesize_parts(self, text: str):
        for part in ("first", "second"):
            self.log.append(f"made {part}")
            yield part.encode()


class LoggingPlayer(AudioPlayer):
    def __init__(self, log: list) -> None:
        self.log = log

    def play(self, wav_bytes: bytes) -> None:
        self.log.append(f"play {wav_bytes.decode()}")


async def test_service_plays_each_part_in_order(bus):
    log: list = []
    SpeechService(bus, TwoPartEngine(log), LoggingPlayer(log))
    spoken: list = []

    async def collect(event):
        spoken.append(event)

    bus.subscribe(collect, to=(CommentSpoken,), name="test.spoken")
    await bus.start()
    bus.publish(GreetingReady(group_id="g", text="x", sighting_ids=("a", "b")))
    await drain(bus)
    # The second part is made before (or while) the first plays, never after.
    assert log.index("made second") < log.index("play second")
    assert [line for line in log if line.startswith("play")] == ["play first", "play second"]
    assert [e.spoken for e in spoken] == [True, True]
    await bus.stop()


async def test_spooky_voice_keeps_one_preset_across_the_parts(bus):
    used: list = []
    presets = (SpookyPreset("a", pitch_cents=-100), SpookyPreset("b", pitch_cents=-200))
    spooky = SpookyVoice(presets=presets, runner=lambda wav, p: used.append(p.name) or wav)
    SpeechService(bus, TwoPartEngine([]), LoggingPlayer([]), audio_filter=spooky)
    await bus.start()
    bus.publish(GreetingReady(group_id="g1", text="x", sighting_ids=("a",)))
    bus.publish(GreetingReady(group_id="g2", text="x", sighting_ids=("b",)))
    await drain(bus)
    assert used == ["a", "a", "b", "b"]  # one preset per greeting, not per clip
    await bus.stop()


def test_tts_engine_chatterbox_is_wired_from_settings(tmp_path, monkeypatch):
    from costume_spotter.config import Settings
    from costume_spotter.main import build_tts_engine

    monkeypatch.delenv("CHATTERBOX_PYTHON", raising=False)
    settings = Settings(_env_file=None, tts_engine="chatterbox", data_dir=tmp_path,
                        chatterbox_url=free_port_url(), chatterbox_timeout_seconds=2)
    engine = build_tts_engine(settings)
    assert isinstance(engine, ChatterboxTtsEngine)
    assert engine._fallback is None and engine._timeout == 2  # noqa: SLF001
    assert engine._process is None  # no CHATTERBOX_PYTHON: an already-running server


def test_server_script_imports_the_real_chatterbox_package(tmp_path):
    """Run as a script, the server's own folder (holding the app's
    speech/chatterbox.py) must not shadow the chatterbox package."""
    import os
    import subprocess

    (tmp_path / "torch").mkdir()
    (tmp_path / "torch" / "__init__.py").write_text(
        "__version__ = 'stub'\n"
        "class version:\n    cuda = None\n"
        "class cuda:\n    @staticmethod\n    def is_available():\n        return False\n")
    (tmp_path / "chatterbox").mkdir()
    (tmp_path / "chatterbox" / "__init__.py").write_text("")
    (tmp_path / "chatterbox" / "tts_turbo.py").write_text("class ChatterboxTurboTTS: pass\n")
    result = subprocess.run(
        [sys.executable, str(chatterbox.SERVER_SCRIPT), "--check"],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "PYTHONPATH": str(tmp_path)})
    assert "chatterbox ok" in result.stdout, result.stdout + result.stderr
