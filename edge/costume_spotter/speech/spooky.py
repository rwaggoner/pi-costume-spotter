"""Spooky voice filter: run synthesized speech through sox for a Halloween effect.

Sits between the TTS engine and the audio player (issue #15). Engine-agnostic
(it transforms WAV bytes, so it works with Piper, Google, or the null engine)
and fully local. It rotates through a list of presets so consecutive visitors
get different spooky styles — vampire #1 doesn't sound identical to ghost #2.

Never-breaks-audio rule (04-F5): if ``sox`` isn't installed or a run fails, the
filter returns the audio unchanged and the porch keeps talking. sox is invoked
as a subprocess, the same pattern as piper.py and aplay.py.
"""

import logging
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from itertools import cycle

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpookyPreset:
    """A named set of sox effect arguments.

    ``pitch`` is in cents (100 = one semitone; more negative = deeper). ``reverb``
    0–100 is how cavernous. ``echo gain-in gain-out delay-ms decay`` adds a
    ghostly repeat. Tune these by ear with the recipe in docs/setup-pi.md §5.
    """

    name: str
    effects: tuple[str, ...]


# The rotation. Ordered light → heavy so a stream of visitors gets variety.
PRESETS: tuple[SpookyPreset, ...] = (
    SpookyPreset("friendly-ghost", ("pitch", "-200", "reverb", "40")),
    SpookyPreset("classic-spooky",
                 ("pitch", "-400", "reverb", "60", "echo", "0.8", "0.7", "60", "0.5")),
    SpookyPreset("crypt-keeper",
                 ("pitch", "-700", "reverb", "75", "echo", "0.8", "0.88", "120", "0.4")),
)


def _run_sox(wav_bytes: bytes, effects: tuple[str, ...]) -> bytes:
    """Pipe WAV through sox stdin→stdout applying ``effects``. Raises on failure."""
    result = subprocess.run(
        ["sox", "-t", "wav", "-", "-t", "wav", "-", *effects],
        input=wav_bytes, capture_output=True, timeout=30,
    )
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError(f"sox failed: {result.stderr.decode(errors='replace')[:200]}")
    return result.stdout


# The subprocess seam: a callable (wav, effects) -> wav. Real one is _run_sox;
# tests inject a fake so rotation logic is verified without sox installed.
SoxRunner = Callable[[bytes, tuple[str, ...]], bytes]


class SpookyVoice:
    """Applies a rotating spooky effect to WAV audio (issue #15)."""

    def __init__(self, presets: tuple[SpookyPreset, ...] = PRESETS,
                 runner: SoxRunner | None = None) -> None:
        self._presets = presets
        self._cycle = cycle(presets)
        self._runner = runner or _run_sox
        # A caller-provided runner (tests) is always "available"; otherwise we
        # need sox on PATH. Checked once so we don't warn on every visitor.
        self._available = runner is not None or shutil.which("sox") is not None
        if not self._available:
            logger.warning("SPOOKY_VOICE enabled but `sox` is not installed "
                           "(sudo apt install sox) — playing normal audio")

    def apply(self, wav_bytes: bytes) -> bytes:
        """Return spookified WAV, or the input unchanged if sox is unavailable
        or errors — audio must never be lost to the effect (04-F5)."""
        if not self._available:
            return wav_bytes
        preset = next(self._cycle)  # rotate: one style per spoken comment
        try:
            out = self._runner(wav_bytes, preset.effects)
            logger.info("spooky voice: %s", preset.name)
            return out
        except Exception as exc:  # noqa: BLE001 — any sox failure falls back to clean audio
            logger.warning("spooky filter (%s) failed: %s; playing unprocessed audio",
                           preset.name, exc)
            return wav_bytes
