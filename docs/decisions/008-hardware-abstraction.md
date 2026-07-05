# ADR-008: Ports & adapters at every hardware boundary (mock-first development)

**Status:** Accepted

## Context

The system touches four pieces of hardware/vendor surface: camera (Picamera2),
detector (HailoRT), TTS (Piper binary / Google API), audio out (ALSA). Development
happens on a Windows laptop; CI runs on GitHub-hosted Linux runners. Neither has a Pi
camera, a Hailo chip, or a speaker.

## Options

### A — Interface + adapters per boundary, profile-selected (chosen)

| Pros | Cons |
|------|------|
| The complete pipeline runs and is tested on any machine (`EDGE_PROFILE=dev`): mock detector over a webcam/video, null audio writing WAVs | More files: each boundary has an ABC + 2–3 implementations |
| Hardware SDK imports are quarantined inside adapters — `import hailo_platform` appears in exactly one file, so the codebase imports cleanly everywhere | Mocks can drift from real adapters (mitigated: shared contract tests run against every implementation of an interface) |
| Swapping vendors (ADR-001's IMX500 option, ADR-005's TTS engines) is additive | Indirection: readers must find which adapter a profile selects (mitigated: one composition root, `main.py`, wires everything explicitly) |
| CI needs zero hardware and zero credentials | |

### B — Direct hardware calls, `if platform == "pi"` branches inline

| Pros | Cons |
|------|------|
| Fewer files | Untestable off-device; `picamera2` import crashes on Windows at module load; platform conditionals metastasize through the codebase |

## Decision

**Option A.** This is the decision that makes every other part of the project
demonstrable: the quick-start works on any laptop, CI is green without secrets, and
the React app can be developed against a fully fake but behaviorally real backend.

Concretely, the ports are: `FrameSource` (picamera2 | opencv), `Detector`
(hailo | imx500 | mock), `TtsEngine` (piper | google | null), `AudioPlayer`
(alsa | null). `main.py` is the single composition root that reads the profile and
wires adapters — dependency injection by explicit construction, no DI framework
(a framework would obscure the wiring this repo wants to *show*).

## Consequences

- Every adapter's module docstring states which requirement/profile it serves.
- Contract tests (`tests/contracts/`) assert interface behavior (e.g. "detector
  returns boxes within frame bounds") against all available implementations —
  hardware-needing ones auto-skip off-device.
- New hardware (different camera, Coral TPU, …) is a new adapter file, not a refactor.
