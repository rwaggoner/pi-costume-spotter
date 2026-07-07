"""SpookyVoice: preset rotation and the never-break-audio guarantees (issue #15).

The sox subprocess is injected as a fake runner, so rotation is verified with no
sox installed; the passthrough-when-unavailable path is exercised as it would be
on CI / a dev laptop (no sox on PATH).
"""

from costume_spotter.speech.spooky import PRESETS, SpookyPreset, SpookyVoice


def recording_runner(calls: list):
    """A fake sox: records the effects it was asked for, returns a marker WAV."""
    def run(wav_bytes: bytes, effects: tuple[str, ...]) -> bytes:
        calls.append(effects)
        return b"spooky:" + wav_bytes
    return run


def test_rotates_through_presets_in_order_and_wraps():
    calls: list = []
    spooky = SpookyVoice(runner=recording_runner(calls))
    for _ in range(len(PRESETS) + 1):  # one full cycle plus one, to see the wrap
        spooky.apply(b"audio")
    assert calls[: len(PRESETS)] == [p.effects for p in PRESETS]
    assert calls[len(PRESETS)] == PRESETS[0].effects  # wrapped back to the first


def test_applies_the_effect_to_the_audio():
    spooky = SpookyVoice(runner=recording_runner([]))
    assert spooky.apply(b"clean") == b"spooky:clean"


def test_passthrough_when_sox_unavailable():
    # runner=None + no sox on PATH (CI/dev) → available is False → input returned.
    spooky = SpookyVoice(runner=None)
    if not spooky._available:  # noqa: SLF001 — the branch under test
        assert spooky.apply(b"clean") == b"clean"


def test_sox_failure_falls_back_to_clean_audio():
    def boom(wav_bytes, effects):
        raise RuntimeError("sox exploded")

    spooky = SpookyVoice(runner=boom)
    # Effect failed, but audio is preserved — the porch keeps talking (04-F5).
    assert spooky.apply(b"clean") == b"clean"


def test_single_preset_repeats():
    calls: list = []
    one = (SpookyPreset("only", ("pitch", "-300")),)
    spooky = SpookyVoice(presets=one, runner=recording_runner(calls))
    spooky.apply(b"a")
    spooky.apply(b"b")
    assert calls == [("pitch", "-300"), ("pitch", "-300")]
