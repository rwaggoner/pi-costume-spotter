# Windows setup — the full porch experience on a Windows PC

The `windows` profile runs the real thing on a Windows 10/11 PC: a USB webcam,
YOLOv8 person detection on the CPU (or any DirectX 12 GPU), Piper speech through
your speakers, the live dashboard, and autostart at login. No Raspberry Pi
needed. Why it is built this way: [ADR-010](decisions/010-windows-target.md).

Just want to poke at the code with no hardware? [setup-dev.md](setup-dev.md)
works on Windows too.

| Pi part | Windows equivalent |
|---------|--------------------|
| AI Camera (Picamera2) | Any USB/built-in webcam (OpenCV, DirectShow) |
| Hailo-8 + YOLOv8s | YOLOv8n on ONNX Runtime — CPU, or GPU via DirectML |
| `aplay` on an ALSA device | `winsound` on the Windows default output device |
| systemd unit | Task Scheduler logon task + restart loop |

## Prerequisites

- Windows 10 or 11, 64-bit
- [Python 3.11–3.14, 64-bit](https://www.python.org/downloads/windows/) — tick **Add python.exe to PATH**.
  Python 3.15 doesn't work yet: ONNX Runtime has no Windows build for it.
  Having one installed alongside is fine; the setup script picks a supported version.
- [Node.js 20+](https://nodejs.org) — only to build the dashboard
- A webcam and speakers
- (optional) an Anthropic API key — without one, costumes are "pretend" identified

All commands below run in **PowerShell** from the repository root.

## 1. Run the setup script

```powershell
powershell -ExecutionPolicy Bypass -File edge\deploy\windows\setup.ps1
```

It creates `edge\.venv`, installs the `[windows]` extra (webcam, ONNX Runtime,
Piper), writes `edge\.env` with `EDGE_PROFILE=windows`, downloads the Piper
voice, and builds the dashboard. It is safe to re-run; an existing `.env` is
never overwritten.

Have a DirectX 12 GPU? Add `-Gpu` to use ONNX Runtime's DirectML build instead
(it sets `ONNX_PROVIDER=directml`).

## 2. Add your API key

Edit `edge\.env` and set `ANTHROPIC_API_KEY=...` — the same key rules as the Pi
(see the API-key note in [setup-pi.md §6](setup-pi.md#6-the-application)).
PowerShell equivalent of the env-override check: `Get-ChildItem Env:ANTHROPIC*`.

## 3. Export the person-detection model (once)

```powershell
powershell -ExecutionPolicy Bypass -File edge\deploy\windows\export-model.ps1
```

This makes `edge\models\yolov8n.onnx`. It installs Ultralytics and PyTorch into
a **throwaway** environment in `%TEMP%` (about 1 GB of downloads, deleted
afterwards). The app itself only needs ONNX Runtime.

The model is not in the repo because the YOLOv8 weights are licensed by
Ultralytics under **AGPL-3.0**, while this repo is MIT. Exporting your own copy
for personal use is fine; read the Ultralytics license before redistributing the
file or a product built on it. Already have a `yolov8n.onnx`? Copy it into
`edge\models\` and skip this step.

Options: `-Model yolov8s` is more accurate and about 3× slower (then set
`ONNX_MODEL_PATH=./models/yolov8s.onnx`). `yolo11n` / `yolo11s` also work.

## 4. Pick your camera and speaker

- **Speaker:** the app plays on the Windows **default output device**. Set it
  in *Settings → System → Sound*. (`AUDIO_DEVICE` is Pi-only.)
- **Camera:** `CAMERA_INDEX=0` is the first camera. A laptop with an external
  webcam usually wants `1`.
- **Camera privacy:** *Settings → Privacy & security → Camera →* turn on
  **Let desktop apps access your camera**. If it's off, the camera "opens" but
  never delivers a frame. The app catches this at startup and says so.
- Hear the voice before running everything:

  ```powershell
  cd edge
  "Trick or treat" | Out-File -Encoding utf8 $env:TEMP\t.txt
  .venv\Scripts\python.exe -m piper -m models\voices\en_US-lessac-medium.onnx -i $env:TEMP\t.txt -f $env:TEMP\t.wav
  (New-Object Media.SoundPlayer "$env:TEMP\t.wav").PlaySync()
  ```

**Spooky voice:** set `SPOOKY_VOICE=true` in `edge\.env`. It's built in, with
nothing extra to install. To audition the presets:
`.venv\Scripts\python.exe -m costume_spotter.speech.spooky $env:TEMP\t.wav`

## 5. Check identification on a few photos (optional)

With your API key in `edge\.env`, test what the AI says about any photos before
Halloween night: one photo per person, cropped to the person for best results.

```powershell
cd edge
.venv\Scripts\python.exe -m costume_spotter.vision.try_photo witch.jpg robot.jpg
.venv\Scripts\python.exe -m costume_spotter.vision.try_photo C:\Users\ryan\Pictures\costume-test
.venv\Scripts\python.exe -m costume_spotter.vision.try_photo --group kid1.jpg kid2.jpg
.venv\Scripts\python.exe -m costume_spotter.vision.try_photo --model claude-haiku-5-5 witch.jpg
```

## 6. Run it

```powershell
cd edge
.venv\Scripts\python.exe -m costume_spotter
```

Open http://localhost:8000 and walk in front of the camera in a hat. You should
see yourself boxed on the live feed, hear a comment, and see the sighting in the
log. `/api/health` shows `detector: onnx-yolov8n`.

From another device on your network, use `http://<pc-name>:8000`. The first run
triggers a Windows Firewall prompt; allow **private networks** only.

## 7. Start automatically at login

```powershell
powershell -ExecutionPolicy Bypass -File edge\deploy\windows\install-autostart.ps1
Start-ScheduledTask -TaskName "Costume Spotter"     # start now without logging out
```

This registers a Task Scheduler task that runs the app in a hidden window when
you log in. If the app crashes, it restarts after 5 seconds, like the Pi's
systemd unit. It's a logon task rather than a Windows service because a service
runs outside your desktop session and can't reliably use the webcam or speaker.
For a dedicated porch PC, also turn on automatic sign-in.

- **Logs:** `edge\data\logs\spotter-<time>.log`, one file per run; the newest 20 runs are kept.
- **Stop:** `Stop-ScheduledTask -TaskName "Costume Spotter"`
- **Remove:** re-run the script with `-Uninstall`

## 8. Update and restart (one step)

After pulling new code, changing `edge\.env`, or whenever the app needs a clean
restart, double-click **`update.cmd`** in the repo folder, or run:

```powershell
powershell -ExecutionPolicy Bypass -File edge\deploy\windows\update.ps1
```

It pulls the latest code (skipped if you have uncommitted changes), stops the
running app, updates Python packages (keeping the DirectML GPU runtime if you
use it), rebuilds the dashboard, tells you whether the AI is on or in pretend
mode, and starts the app again: through the autostart task if installed,
otherwise in that window.

| Option | Effect |
|--------|--------|
| `-NoPull` | Don't `git pull` |
| `-SkipDashboard` | Don't rebuild the dashboard |
| `-NoStart` | Update and rebuild, but leave the app stopped |

(With `update.cmd`, add options after it: `update.cmd -NoPull -SkipDashboard`.)

## 9. A more natural voice: Chatterbox (optional, NVIDIA GPU)

[Chatterbox Turbo](https://github.com/resemble-ai/chatterbox) (Resemble AI, MIT
license) sounds far more human than Piper. It needs an **NVIDIA GPU**, since on
the processor alone a greeting takes 15-50 s, and it runs on Windows only (the
Pi stays on Piper). It runs as a separate voice server with its own Python
environment, `edge\.venv-chatterbox`, because it needs PyTorch (about 3 GB) and
library versions that would clash with the app's. The app starts and stops it
for you.

1. Build it once. This takes 10-20 minutes and downloads about 4.5 GB:
   ```powershell
   powershell -ExecutionPolicy Bypass -File edge\deploy\windows\setup-chatterbox.ps1
   ```
   It needs 64-bit **Python 3.11** (3.12 or 3.13 also work) next to your other
   Pythons. It installs PyTorch for CUDA 12.8, which RTX 50-series cards need,
   checks the GPU, downloads the model, and times a few porch lines. Play
   `edge\chatterbox-sample.wav` to hear it.
2. In `edge\.env` set the following, keeping `PIPER_VOICE_PATH` as it is:
   ```
   TTS_ENGINE=chatterbox
   CHATTERBOX_PYTHON=.venv-chatterbox\Scripts\python.exe
   ```
3. Run `update.cmd`.

How it behaves:

- **Piper still speaks:**
  - while Chatterbox loads, which takes 10-30 s after the app starts;
  - if Chatterbox is down;
  - if a sentence takes longer than `CHATTERBOX_TIMEOUT_SECONDS` (default 4).

  Visitors are never left in silence, and one greeting never switches voices
  midway.
- **Speaking starts after the first sentence.** The rest of a group's greeting
  is made while the first sentence plays.
- **Your own voice (optional):** set `CHATTERBOX_VOICE_CLIP` to a WAV of about
  10 seconds of one person talking, with no music or background noise. Your own
  best spooky voice works well. Don't use a recording of a celebrity or a
  character.
- **Logs:** the voice server writes to `edge\data\logs\chatterbox.log`, which
  shows how long each line took.
- **Watermark:** Chatterbox marks every clip with an inaudible watermark.

To time it again later: `setup-chatterbox.ps1 -BenchOnly`. Under about 1.5 s per
line feels instant.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `webcam N opened but returned no frame` | Camera privacy setting (§4), or another app (Teams, Zoom, the Camera app) has the camera |
| `webcam N could not be opened` | Wrong `CAMERA_INDEX` — try 1, 2… Or try `CAMERA_BACKEND=msmf` |
| Camera opens slowly / wrong resolution | You're on `CAMERA_BACKEND=msmf`; `auto` (DirectShow) is faster |
| `ONNX model not found` | Run step 3, or fix `ONNX_MODEL_PATH` |
| `ONNX_PROVIDER=directml but DmlExecutionProvider isn't available` | Both ONNX Runtimes are installed. Fix: `pip uninstall -y onnxruntime onnxruntime-directml` then `pip install onnxruntime-directml` (in the venv) |
| No sound, no error | Wrong default output device (§4), or `TTS_ENGINE` isn't `piper` |
| `PIPER_VOICE_PATH not found` | Re-run `setup.ps1`, or fix the path in `.env` |
| Still Piper's voice with `TTS_ENGINE=chatterbox` | Wait 30 s after start; then check `edge\data\logs\chatterbox.log`. `setup-chatterbox.ps1 -BenchOnly` re-checks the GPU (§9) |
| Low FPS | Expect roughly 8–15 FPS for `yolov8n` on a modern CPU. Try `-Gpu`, or lower `FRAME_WIDTH`/`FRAME_HEIGHT` |
| Dashboard 404 at `/` | The dashboard isn't built: install Node.js and re-run `setup.ps1` |
| `onnxruntime` … `from versions: none` during setup | The venv uses an unsupported Python (too new, or 32-bit). `setup.ps1` now detects this. Delete `edge\.venv`, make sure Python 3.11–3.14 64-bit is installed, and re-run |
| Script blocked: "running scripts is disabled" | Launch it as shown, with `powershell -ExecutionPolicy Bypass -File ...` |
