"""SpookyVoice: preset rotation, the never-break-audio guarantee (issue #15), and
the numpy effects that replaced sox (ADR-010).

Rotation is verified with a fake effect runner; the DSP is verified on pure
tones, where "a semitone lower" and "same length" are exactly measurable.
"""

import io
import wave

import numpy as np
import pytest

from costume_spotter.speech.null import NullTtsEngine
from costume_spotter.speech.spooky import (
    PRESETS,
    SpookyPreset,
    SpookyVoice,
    apply_preset,
    echo,
    pitch_shift,
    reverb,
)

SR = 22_050


def recording_runner(calls: list):
    """A fake effect: records the preset it was asked for, returns a marker WAV."""
    def run(wav_bytes: bytes, preset: SpookyPreset) -> bytes:
        calls.append(preset)
        return b"spooky:" + wav_bytes
    return run


def tone(freq: float, seconds: float = 1.0, amp: float = 0.5) -> np.ndarray:
    return amp * np.sin(2 * np.pi * freq * np.arange(int(SR * seconds)) / SR)


def dominant_freq(x: np.ndarray) -> float:
    spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return float(np.argmax(spectrum) * SR / len(x))


def to_wav(x: np.ndarray, channels: int = 1, width: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(SR)
        if width == 2:
            w.writeframes((np.repeat(x, channels) * 32767).astype("<i2").tobytes())
        else:
            w.writeframes(bytes(len(x) * channels * width))
    return buf.getvalue()


# --- rotation & fallback ----------------------------------------------------

def test_rotates_through_presets_in_order_and_wraps():
    calls: list = []
    spooky = SpookyVoice(runner=recording_runner(calls))
    for _ in range(len(PRESETS) + 1):  # one full cycle plus one, to see the wrap
        spooky.apply(b"audio")
    assert calls[: len(PRESETS)] == list(PRESETS)
    assert calls[len(PRESETS)] == PRESETS[0]  # wrapped back to the first


def test_applies_the_effect_to_the_audio():
    spooky = SpookyVoice(runner=recording_runner([]))
    assert spooky.apply(b"clean") == b"spooky:clean"


def test_effect_failure_falls_back_to_clean_audio():
    def boom(wav_bytes, preset):
        raise RuntimeError("effect exploded")

    # Effect failed, but audio is preserved — the porch keeps talking (04-F5).
    assert SpookyVoice(runner=boom).apply(b"clean") == b"clean"


def test_unsupported_wav_falls_back_through_the_real_effect():
    eight_bit = to_wav(np.zeros(100), width=1)
    assert SpookyVoice().apply(eight_bit) == eight_bit


def test_single_preset_repeats():
    calls: list = []
    one = (SpookyPreset("only", pitch_cents=-300),)
    spooky = SpookyVoice(presets=one, runner=recording_runner(calls))
    spooky.apply(b"a")
    spooky.apply(b"b")
    assert calls == [one[0], one[0]]


# --- DSP --------------------------------------------------------------------

@pytest.mark.parametrize("cents", [-200, -400, -700, -1200, 300])
def test_pitch_shift_hits_the_target_pitch_and_keeps_duration(cents):
    x = tone(220, seconds=2)
    y = pitch_shift(x, cents, SR)
    assert len(y) == len(x)  # same speaking speed — the point of WSOLA
    expected = 220 * 2 ** (cents / 1200)
    assert dominant_freq(y) == pytest.approx(expected, rel=0.01)


def test_echo_adds_a_delayed_decayed_copy():
    impulse = np.zeros(1000)
    impulse[0] = 1.0
    y = echo(impulse, 0.8, 1.0, delay_ms=10, decay=0.5, sample_rate=SR)
    delay = int(SR * 0.010)
    assert y[0] == pytest.approx(0.8) and y[delay] == pytest.approx(0.5)


def test_reverb_leaves_a_tail_after_the_sound_stops():
    x = tone(440, seconds=0.2)
    y = reverb(x, 60, SR)
    assert len(y) > len(x)
    assert np.abs(y[len(x): len(x) + SR // 10]).max() > 0.01  # still ringing


def test_presets_produce_valid_wav_at_the_original_loudness():
    wav = to_wav(tone(180, seconds=1.5))
    for preset in PRESETS:
        out = apply_preset(wav, preset)
        with wave.open(io.BytesIO(out)) as w:
            assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, SR)
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2") / 32768
        assert np.abs(pcm).max() == pytest.approx(0.5, abs=0.02)  # no clipping, no fade


def test_stereo_and_silence_are_handled():
    assert apply_preset(to_wav(tone(200, 0.5), channels=2), PRESETS[1])[:4] == b"RIFF"
    silent = NullTtsEngine().synthesize("boo")  # what dev mode actually speaks
    assert apply_preset(silent, PRESETS[2])[:4] == b"RIFF"
