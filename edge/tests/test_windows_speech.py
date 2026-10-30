"""Windows speech adapters (ADR-010), tested on any OS through their seams."""

import subprocess
import sys
from pathlib import Path

import pytest

from costume_spotter.speech import piper as piper_module
from costume_spotter.speech.null import NullTtsEngine
from costume_spotter.speech.winsound_player import WinsoundAudioPlayer

# --- winsound player -------------------------------------------------------

def test_winsound_player_hands_complete_wav_to_the_os():
    played = []
    player = WinsoundAudioPlayer(play=played.append)
    wav = NullTtsEngine().synthesize("boo")
    player.play(wav)
    assert played == [wav]


def test_winsound_player_rejects_non_wav_bytes():
    player = WinsoundAudioPlayer(play=lambda _: None)
    with pytest.raises(RuntimeError, match="RIFF"):
        player.play(b"ID3 not a wav")


@pytest.mark.skipif(sys.platform == "win32", reason="winsound exists on Windows")
def test_winsound_player_fails_fast_off_windows():
    with pytest.raises(RuntimeError, match="Windows"):
        WinsoundAudioPlayer()


# --- piper engine -----------------------------------------------------------

@pytest.fixture
def voice(tmp_path) -> Path:
    path = tmp_path / "voice.onnx"
    path.write_bytes(b"fake model")
    return path


def test_piper_uses_files_not_pipes(monkeypatch, voice):
    """Text in via a UTF-8 file and WAV out via a file: stdout WAV mode breaks on
    Windows, and stdin is decoded with the console code page there."""
    seen = {}

    def fake_run(cmd, **kwargs):
        args = dict(zip(cmd, cmd[1:]))
        seen["text"] = Path(args["--input-file"]).read_text(encoding="utf-8")
        Path(args["--output-file"]).write_bytes(b"RIFF fake wav")
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(piper_module, "piper_command", lambda: ["piper"])
    monkeypatch.setattr(piper_module.subprocess, "run", fake_run)
    engine = piper_module.PiperTtsEngine(str(voice), in_process=False)
    wav = engine.synthesize("A wild T-Rex appears —\n tiny arms, big candy!")
    assert wav == b"RIFF fake wav"
    assert seen["text"] == "A wild T-Rex appears — tiny arms, big candy!"  # one line, UTF-8 intact
    assert "-" not in seen["cmd"]


def test_piper_reports_failures(monkeypatch, voice):
    monkeypatch.setattr(piper_module, "piper_command", lambda: ["piper"])
    monkeypatch.setattr(piper_module.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b"boom"))
    with pytest.raises(RuntimeError, match="boom"):
        piper_module.PiperTtsEngine(str(voice), in_process=False).synthesize("hi")


def test_piper_fails_fast_on_missing_voice(monkeypatch, tmp_path):
    monkeypatch.setattr(piper_module, "piper_command", lambda: ["piper"])
    with pytest.raises(RuntimeError, match="PIPER_VOICE_PATH"):
        piper_module.PiperTtsEngine(str(tmp_path / "missing.onnx"))


def test_piper_prefers_our_interpreter_over_path(monkeypatch):
    """Task Scheduler runs the venv's python without activating the venv, so
    the `piper` script isn't on PATH — `python -m piper` still works."""
    monkeypatch.setattr(piper_module.importlib.util, "find_spec", lambda name: object())
    assert piper_module.piper_command() == [sys.executable, "-m", "piper"]


def test_piper_keeps_the_voice_loaded(monkeypatch, voice):
    """The voice loads ONCE (plus a warm-up) and every comment reuses it — no
    per-comment model load, which used to cost ~2 s per greeting."""
    import types
    import wave

    loads: list = []
    spoken: list = []

    class FakeVoice:
        @staticmethod
        def load(path):
            loads.append(path)
            return FakeVoice()

        def synthesize_wav(self, text, wav_file):
            spoken.append(text)
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(b"\x00\x00" * 160)

    monkeypatch.setitem(sys.modules, "piper", types.SimpleNamespace(PiperVoice=FakeVoice))
    engine = piper_module.PiperTtsEngine(str(voice), in_process=True)
    first = engine.synthesize("Boo!\n Happy  Halloween")
    engine.synthesize("Again!")

    assert loads == [str(voice)]  # loaded once
    assert spoken == ["Hello.", "Boo! Happy Halloween", "Again!"]  # warm-up, then reuse
    with wave.open(__import__("io").BytesIO(first)) as w:
        assert w.getnframes() == 160
