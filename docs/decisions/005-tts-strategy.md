# ADR-005: Pluggable TTS — Piper by default, Google Cloud TTS optional

**Status:** Accepted

## Context

Comments must be spoken aloud ([requirements 04](../requirements/04-speech.md)). The
options differ mainly on the offline/quality/cost triangle, and this project also
wants to demonstrate GCP service integration.

## Options

| Option | Pros | Cons |
|--------|------|------|
| **Piper (local)** | Free, offline, private, ~1 s synthesis on Pi 5, good neural voices | Voice quality a notch below cloud engines; model file (~60 MB) to install |
| **Google Cloud TTS** | Excellent Neural2/WaveNet voices; effectively free at this volume | Requires internet + GCP credentials for a *core* feature; per-char cost at scale |
| eSpeak-NG (local) | Tiny, instant | Distinctly robotic — undermines the demo |
| Claude/OpenAI audio APIs | One-vendor story | Same connectivity coupling, higher cost, no offline story |

## Decision

**Both Piper and Google Cloud TTS, behind a single `TtsEngine` interface, selected by
config — Piper is the default.**

Rationale, in order of weight:

1. **Reliability principle:** the edge must work with no internet (architecture
   principle #3). Speech is core, so its default engine must be local.
2. **Showcase value:** a strategy pattern at a vendor boundary — two real
   implementations, config-driven selection, shared contract tests — demonstrates
   more engineering judgment than either engine alone.
3. **Quality option:** demos on good speakers can flip one env var
   (`TTS_ENGINE=google`) for noticeably nicer voices.

The cost of the decision is honest: two integrations to maintain instead of one, and
an abstraction that must not leak either engine's quirks (e.g. Google returns MP3 by
default — the interface contract normalizes on WAV/PCM).

## Consequences

- `speech/base.py` defines `TtsEngine.synthesize(text) -> AudioClip`; `piper.py` and
  `google_tts.py` implement it; a shared test suite runs against both (Google's
  mocked in CI).
- Playback (queueing, one-at-a-time, drop-when-stale — 04-F3/F4) lives *outside* the
  engines in `player.py`, so it's written once.
- `dev` profile uses Piper if installed, else a null engine that writes text to WAV
  silence — CI needs no audio stack.
