# ADR-010: Windows as a first-class deployment target

**Status:** Accepted

## Context

The system was built for one deployment: a Raspberry Pi 5 with the AI Camera and
the Hailo-8 HAT+. The `dev` profile already ran on a Windows laptop, but only
with fakes: a synthetic camera, a mock detector, and audio written to files.
The goal now is the *real* porch experience on a plain Windows PC: a webcam,
real person detection, a speaker, and autostart.

Four things only existed for Linux: the camera (Picamera2), detection (Hailo
only fits a Pi), playback (`aplay`/ALSA) and service management (systemd). Two
more broke on Windows in practice. Piper's "WAV to stdout" mode reopens a locked
temp file, which Windows forbids. The spooky voice depended on a `sox` binary on
PATH.

ADR-008's ports-and-adapters design is what makes this tractable. Every one of
these is an adapter swap behind an existing port; no pipeline, tracking, event
bus, or API code changes.

## Options

### Overall approach

| Option | Pros | Cons |
|--------|------|------|
| **A third `windows` profile with native adapters** | One switch rewires the hardware, the same way `pi` works; native camera and audio; no new runtime layers | More adapters to maintain |
| WSL2 or Docker running the Linux build | No new code | Webcam and audio passthrough into WSL2/containers is fragile (usbipd, PulseAudio bridges) — and those are the two things this app depends on |
| `dev` profile plus `.env` overrides | No new profile | The hardware pairing lives in documentation instead of code; that is exactly the bug class `_profile_defaults` was added to prevent |

### Person detection

| Option | Pros | Cons |
|--------|------|------|
| **YOLOv8n on ONNX Runtime (CPU, DirectML optional)** | Same model family as the Pi's Hailo path; ~80 ms/frame on a modern CPU; any DirectX 12 GPU via DirectML; one small pip package | Weights licensed AGPL-3.0 by Ultralytics (see Consequences) |
| HOG (existing) | Already implemented, no model file | Misses many people, and costumes (capes, masks, inflatables) make it worse |
| Ultralytics package at runtime | Simplest code | Pulls PyTorch (~1 GB) into the app's environment; AGPL code imported into the process |
| YOLOX via ONNX | Apache-2.0 weights | Different output format from the Pi's YOLOv8; fewer ready exports |

### Audio playback

| Option | Pros | Cons |
|--------|------|------|
| **`winsound` (standard library)** | Nothing to install; plays WAV bytes from memory and blocks until done, which is exactly the `AudioPlayer` contract | Default output device only |
| `sounddevice` | Choose any device, like `AUDIO_DEVICE` on the Pi | New native dependency (PortAudio) |

### Autostart

| Option | Pros | Cons |
|--------|------|------|
| **Task Scheduler logon task + restart loop** | Runs in the user's desktop session, so camera and speaker work as they do by hand; no admin rights; no third-party tools | Needs a logged-in user (pair with auto sign-in) |
| Windows service via NSSM | Starts at boot | Session-0 isolation: services can't reliably use the camera or play audio; third-party binary |

### Spooky voice

| Option | Pros | Cons |
|--------|------|------|
| **Re-implement the effects in numpy** | No extra install on *any* platform; testable on pure tones; ~20 ms per clip | ~150 lines of DSP to own |
| Keep `sox` | Already written | Extra install and PATH setup on Windows; binary stdin/stdout piping is fragile there |

## Decision

Make Windows first-class with a **`windows` profile** that wires: webcam
(DirectShow), **YOLOv8 on ONNX Runtime**, Piper, **`winsound`** playback, and a
**Task Scheduler** autostart. Also, on every platform:

- **Piper** runs as `python -m piper` with the app's own interpreter, using
  text and WAV *files* rather than pipes.
- **The spooky voice** is pure numpy; `sox` is no longer used.
- **OpenCV is pinned below 5**: version 5 removed `HOGDescriptor` from the main
  module, which broke `HogDetector` and the contract tests on fresh installs.

## Consequences

- `edge/costume_spotter/detection/onnx_yolo.py` joins the detector contract
  tests whenever a model file is present (`ONNX_TEST_MODEL`). Its decode,
  letterbox and NMS logic is unit-tested without a model, so CI needs none. It
  can also serve as a CPU fallback on a Pi without a Hailo HAT
  (`DETECTOR=onnx`).
- **Model licensing:** the YOLOv8 weights are AGPL-3.0 (Ultralytics). They are
  not committed (`models/` and `*.onnx` are ignored). Each machine exports its
  own copy with `edge/deploy/windows/export-model.ps1`, in a throwaway
  environment, so PyTorch and Ultralytics never enter the app's dependencies.
  Anyone redistributing the model or a product built on it must check the
  Ultralytics terms. The Pi's Hailo model zoo `.hef` is also YOLOv8; this
  decision doesn't change the project's license position, it makes it explicit.
- `onnxruntime` and `onnxruntime-directml` share a module name and conflict.
  `piper-tts` depends on the CPU build, so `setup.ps1 -Gpu` uninstalls it before
  installing DirectML; Piper then runs on the DirectML build.
- Playback always uses the Windows default device. If per-device selection
  becomes necessary, a `sounddevice` player can be added behind the same port.
- CI runs the edge test suite on `windows-latest` as well as Ubuntu, so
  Windows-only breakage (paths, encodings, subprocess behavior) shows up in PRs.
- The setup scripts target Windows PowerShell 5.1, which ships with every
  Windows 10/11 install, and are syntax-checked with PowerShell 7.
