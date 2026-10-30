# 04 — Speech Output

## Purpose

Turn the generated comment into audible speech from a speaker attached to the Pi.
Speech is the "delight" feature of the project — it must be reliable (works offline)
and never turn into overlapping chaos when three kids arrive at once.

## Functional requirements

| ID | Requirement |
|----|-------------|
| 04-F1 | Consume `CostumeIdentified` events and speak the comment aloud. |
| 04-F2 | TTS engines are pluggable behind one interface ([ADR-005](../decisions/005-tts-strategy.md)): **Piper** (local neural TTS, default) and **Google Cloud TTS** (optional, higher quality), selected by config. |
| 04-F3 | Speech requests are queued and played strictly one at a time — simultaneous visitors produce sequential comments, never overlapping audio. |
| 04-F4 | If the queue exceeds a configurable depth (default 3), the oldest unspoken comments are dropped — a comment about someone who left 40 seconds ago is worse than silence. |
| 04-F5 | If the configured engine fails (Piper model missing, Google unreachable), log the failure, publish the event with `spoken: false`, and keep running — speech failure must not stop detection or logging. |
| 04-F6 | Publish `CommentSpoken` after playback so the dashboard can show what was said and when. |
| 04-F7 | In `dev` profile, audio output is a `NullAudioPlayer` that writes WAV files to a temp dir instead of playing them (laptops in CI have no speaker). |
| 04-F8 | An optional audio filter (`SPOOKY_VOICE`, issue #15) transforms the synthesized WAV before playback — a rotating Halloween effect (pitch, echo, reverb) implemented in numpy, so it needs no extra install on any platform (ADR-010; it originally shelled out to `sox`). It is engine-agnostic and must degrade to unmodified audio if an effect fails (never silence the porch — a corollary of 04-F5). |
| 04-F9 | **Groups are one utterance:** speech consumes `GreetingReady`, not `CostumeIdentified`. A group hears the greeting followed by each person's shout-out when the group has at most `SHOUT_OUT_MAX_GROUP` people (default 3); bigger groups hear only the greeting. `CommentSpoken` is published once per sighting covered. |
| 04-F10 | **Voice kept loaded:** the Piper voice model is loaded once at startup (with a warm-up), not per comment — loading costs ~2 s, synthesis with a loaded voice ~0.4 s. |

## Non-functional requirements

| ID | Requirement |
|----|-------------|
| 04-N1 | Piper synthesis of a 20-word sentence completes in < 2 s on the Pi 5 CPU. |
| 04-N2 | The default path (Piper) requires no internet and no credentials. |
| 04-N3 | Synthesis runs off the event-loop thread (it's CPU-bound); the bus and API must stay responsive during synthesis. |

## Engine comparison (why both exist)

| | Piper (default) | Google Cloud TTS |
|---|---|---|
| Runs | On the Pi, offline | Cloud API |
| Cost | Free | ~$4/1M chars (free tier covers this project) |
| Voice quality | Good neural voice | Excellent (WaveNet/Neural2) |
| Latency | ~1 s synthesis | ~0.5 s + network RTT |
| Failure mode | None (local) | Needs internet + GCP credentials |

Keeping both behind one interface is itself a showcase goal: the strategy pattern at a
vendor boundary, with config-driven selection.
