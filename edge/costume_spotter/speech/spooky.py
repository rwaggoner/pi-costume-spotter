"""Spooky voice filter: run synthesized speech through a Halloween effect.

Sits between the TTS engine and the audio player (issue #15). Engine-agnostic
(it transforms WAV bytes, so it works with Piper, Google, or the null engine)
and fully local. It rotates through a list of presets so consecutive visitors
get different spooky styles — vampire #1 doesn't sound identical to ghost #2.

The effects are pure numpy (ADR-010). They replaced a ``sox`` subprocess, which
was an extra install on every platform and awkward on Windows (PATH setup,
binary stdin/stdout piping). The three effects mirror the sox ones they
replaced, so the presets kept their character:

- **pitch** — deeper voice at the *same* speaking speed: resample (lowers pitch
  but slows speech), then WSOLA time-stretch back to the original length.
- **echo** — one delayed, decayed copy, sox ``echo`` semantics.
- **reverb** — a classic Schroeder reverb (4 comb + 2 all-pass filters).

Never-breaks-audio rule (04-F5): if an effect fails (e.g. an unexpected WAV
format), the filter returns the audio unchanged and the porch keeps talking.
"""

import io
import logging
import wave
from collections.abc import Callable
from dataclasses import dataclass
from itertools import cycle

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpookyPreset:
    """A named set of effect settings.

    ``pitch_cents``: 100 = one semitone; more negative = deeper.
    ``reverb``: 0-100, how cavernous.
    ``echo``: (gain_in, gain_out, delay_ms, decay) for a ghostly repeat, or None.
    Tune by ear with the recipe in docs/setup-pi.md §5.
    """

    name: str
    pitch_cents: float = 0.0
    reverb: float = 0.0
    echo: tuple[float, float, float, float] | None = None


# The rotation. Ordered light → heavy so a stream of visitors gets variety.
PRESETS: tuple[SpookyPreset, ...] = (
    SpookyPreset("friendly-ghost", pitch_cents=-200, reverb=40),
    SpookyPreset("classic-spooky", pitch_cents=-400, reverb=60, echo=(0.8, 0.7, 60, 0.5)),
    SpookyPreset("crypt-keeper", pitch_cents=-700, reverb=75, echo=(0.8, 0.88, 120, 0.4)),
)


# --------------------------------------------------------------------------
# DSP — mono float arrays in -1..1 at a given sample rate
# --------------------------------------------------------------------------

def time_stretch(x: np.ndarray, rate: float, sample_rate: int) -> np.ndarray:
    """WSOLA: change duration by 1/rate without changing pitch (rate > 1 = shorter).

    Overlap-adds 30 ms Hann windows, nudging each input frame by up to ±7.5 ms to
    the position that best continues the previous one — that alignment is what
    avoids the "phasey" sound of naive overlap-add on speech.
    """
    win = max(64, int(0.030 * sample_rate) // 2 * 2)
    hop = win // 2
    tol = win // 4
    window = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(win) / win)  # periodic Hann: sums to 1
    n_frames = max(1, int((len(x) / rate - win) / hop) + 1)
    padded = np.concatenate([np.zeros(tol), x, np.zeros(win + 2 * tol + int(hop * rate) + 1)])
    out = np.zeros((n_frames - 1) * hop + win)
    prev = 0  # input position (in unpadded samples) of the previous frame
    for k in range(n_frames):
        nominal = int(round(k * hop * rate))
        if k == 0:
            pos = 0
        else:
            # What would naturally follow the previous frame...
            template = padded[tol + prev + hop: tol + prev + hop + win]
            # ...and where near `nominal` the input matches it best.
            region = padded[nominal: nominal + 2 * tol + win]
            pos = nominal - tol + int(np.argmax(np.correlate(region, template, "valid")))
            pos = max(pos, 0)
        out[k * hop: k * hop + win] += padded[tol + pos: tol + pos + win] * window
        prev = pos
    return out


def pitch_shift(x: np.ndarray, cents: float, sample_rate: int) -> np.ndarray:
    """Shift pitch by ``cents``, keeping duration."""
    if cents == 0 or len(x) == 0:
        return x
    factor = 2.0 ** (cents / 1200.0)  # < 1 = deeper
    # Reading the signal at step `factor` scales pitch by `factor` and length by 1/factor...
    resampled = np.interp(np.arange(0, len(x) - 1, factor), np.arange(len(x)), x)
    # ...then time-stretch it back to the original length.
    stretched = time_stretch(resampled, 1.0 / factor, sample_rate)[: len(x)]
    return np.pad(stretched, (0, len(x) - len(stretched)))  # WSOLA rounds down a few ms


def echo(x: np.ndarray, gain_in: float, gain_out: float, delay_ms: float, decay: float,
         sample_rate: int) -> np.ndarray:
    """sox ``echo``: (in·gain_in + delayed(in)·decay)·gain_out, extended by the delay."""
    delay = int(sample_rate * delay_ms / 1000)
    out = np.zeros(len(x) + delay)
    out[: len(x)] += x * gain_in
    out[delay: delay + len(x)] += x * decay
    return out * gain_out


def _feedback(u: np.ndarray, delay: int, gain: float) -> np.ndarray:
    """y[n] = u[n] + gain·y[n - delay], vectorized one delay-length block at a time."""
    n_blocks = -(-len(u) // delay)
    blocks = np.zeros(n_blocks * delay)
    blocks[: len(u)] = u
    blocks = blocks.reshape(n_blocks, delay)
    for b in range(1, n_blocks):
        blocks[b] += gain * blocks[b - 1]
    return blocks.reshape(-1)[: len(u)]


def reverb(x: np.ndarray, amount: float, sample_rate: int) -> np.ndarray:
    """Schroeder reverb; ``amount`` 0-100 sets both tail length and wet level."""
    if amount <= 0:
        return x
    amount = min(amount, 100) / 100
    tail = int(sample_rate * (0.3 + 1.2 * amount))
    dry = np.concatenate([x, np.zeros(tail)])
    feedback = 0.70 + 0.14 * amount
    wet = np.zeros_like(dry)
    for ms in (29.7, 37.1, 41.1, 43.7):  # parallel combs: mutually prime-ish delays
        wet += _feedback(dry, int(sample_rate * ms / 1000), feedback)
    wet /= 4
    for ms in (5.0, 1.7):  # series all-passes: diffuse the comb echoes
        d, g = int(sample_rate * ms / 1000), 0.7
        delayed = np.concatenate([np.zeros(d), wet[:-d]])
        wet = _feedback(-g * wet + delayed, d, g)
    return dry + wet * (0.6 * amount)


def apply_preset(wav_bytes: bytes, preset: SpookyPreset) -> bytes:
    """WAV in, spookified WAV out. Raises on formats it can't handle (caller falls back)."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as src:
        channels, width, rate = src.getnchannels(), src.getsampwidth(), src.getframerate()
        frames = src.readframes(src.getnframes())
    if width != 2:
        raise ValueError(f"expected 16-bit PCM WAV, got {8 * width}-bit")
    pcm = np.frombuffer(frames, dtype="<i2").reshape(-1, channels).astype(np.float64) / 32768
    peak = float(np.abs(pcm).max()) if pcm.size else 0.0

    processed = []
    for ch in range(channels):
        y = pitch_shift(pcm[:, ch], preset.pitch_cents, rate)
        if preset.echo:
            y = echo(y, *preset.echo, sample_rate=rate)
        y = reverb(y, preset.reverb, rate)
        processed.append(y)
    length = max(len(y) for y in processed)
    out = np.zeros((length, channels))
    for ch, y in enumerate(processed):
        out[: len(y), ch] = y
    # Match the original loudness so effects never clip or fade the greeting.
    out_peak = float(np.abs(out).max()) if out.size else 0.0
    if out_peak > 0 and peak > 0:
        out *= min(peak, 0.98) / out_peak

    buf = io.BytesIO()
    with wave.open(buf, "wb") as dst:
        dst.setnchannels(channels)
        dst.setsampwidth(2)
        dst.setframerate(rate)
        dst.writeframes((np.clip(out, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


# The effect seam: a callable (wav, preset) -> wav. The real one is apply_preset;
# tests inject a fake so rotation logic is verified independently of the DSP.
EffectRunner = Callable[[bytes, SpookyPreset], bytes]


class SpookyVoice:
    """Applies a rotating spooky effect to WAV audio (issue #15)."""

    def __init__(self, presets: tuple[SpookyPreset, ...] = PRESETS,
                 runner: EffectRunner | None = None) -> None:
        self._presets = presets
        self._cycle = cycle(presets)
        self._runner = runner or apply_preset

    def apply(self, wav_bytes: bytes) -> bytes:
        """Return spookified WAV, or the input unchanged if the effect errors —
        audio must never be lost to the effect (04-F5)."""
        preset = next(self._cycle)  # rotate: one style per spoken comment
        try:
            out = self._runner(wav_bytes, preset)
            logger.info("spooky voice: %s", preset.name)
            return out
        except Exception as exc:  # noqa: BLE001 — any effect failure falls back to clean audio
            logger.warning("spooky filter (%s) failed: %s; playing unprocessed audio",
                           preset.name, exc)
            return wav_bytes


if __name__ == "__main__":
    # Audition the presets: python -m costume_spotter.speech.spooky plain.wav
    # writes plain.friendly-ghost.wav, plain.classic-spooky.wav, ... next to it.
    import sys
    from pathlib import Path

    if len(sys.argv) != 2:
        sys.exit("usage: python -m costume_spotter.speech.spooky <speech.wav>")
    source = Path(sys.argv[1])
    for p in PRESETS:
        target = source.with_name(f"{source.stem}.{p.name}.wav")
        target.write_bytes(apply_preset(source.read_bytes(), p))
        print(f"wrote {target}")
