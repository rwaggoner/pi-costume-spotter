# Raspberry Pi bring-up

Target hardware: **Raspberry Pi 5 (4 GB)** + **Raspberry Pi AI Camera (IMX500)** +
**Hailo AI HAT+ (26 TOPS)** + any USB or 3.5 mm-via-HAT speaker.

> Follow this top to bottom on a fresh Raspberry Pi OS install. Each stage ends with a
> check — don't continue past a failing check.

## Names used throughout (read this first)

Four similar names appear below; they are different things:

| Name | What it is |
|------|------------|
| `~/pi-costume-spotter/` | **The repository** you clone in §6. The app is always launched from its `edge/` subdirectory (that's where `.env` is read from). |
| `~/costume-spotter-data/` | **Runtime data**: downloaded models (§3), voices (§5), and — via `DATA_DIR` — the SQLite DB and snapshots. Kept outside the repo so `git` operations can never touch data, and data never lands in the public repo. |
| `costume_spotter` | The **Python module**: `python -m costume_spotter`, run from `pi-costume-spotter/edge` with its venv active. |
| `costume-spotter.service` | The **systemd unit** (§7) that runs the module on boot. |

The examples use `/home/pi/…`; substitute your actual username throughout
(e.g. `/home/ryan/…`).

## 1. OS and base packages

Use **Raspberry Pi OS (64-bit)** — Bookworm or Trixie both work (Trixie needs
one extra driver step, called out in §3). The Hailo stack and Picamera2 both
require the Raspberry Pi OS repos, so stock Debian/Ubuntu images won't do.

```bash
sudo apt update && sudo apt full-upgrade -y
# git — clones this repository (§6)          python3-picamera2 — camera stack (apt-only)
# python3-pip/venv — the app's environment   alsa-utils — aplay, for the speaker (§4)
sudo apt install -y git python3-pip python3-venv python3-picamera2 alsa-utils
```

**Check:** `python3 -c "import picamera2; print('picamera2 OK')"`

## 2. AI Camera (IMX500)

Connect the camera to a CSI port (Pi 5 has two; either works). Then:

```bash
sudo apt install -y imx500-all   # firmware + models for the on-sensor NPU
sudo reboot
```

**Check:** `rpicam-hello --list-cameras` should list `imx500`.
A 5-second preview test: `rpicam-hello -t 5000`.

## 3. Hailo AI HAT+

Physically install the HAT+ on the Pi 5's PCIe connector (power off first; use the
included thermal pad). Then:

```bash
sudo apt install -y hailo-all    # HailoRT runtime, driver, TAPPAS core
sudo reboot
```

> **Raspberry Pi OS Trixie (Debian 13) note — learned the hard way.** Bookworm
> kernels ship the `hailo_pci` module in-tree; Trixie kernels do not, and the
> `hailort-pcie-driver` package builds it with dkms instead. Without dkms and
> kernel headers present, `hailo-all` installs "successfully" yet no driver
> module ever exists. On Trixie, install these too:
>
> ```bash
> sudo apt install -y dkms linux-headers-rpi-2712
> sudo apt install --reinstall hailort-pcie-driver   # watch it compile this time
> sudo reboot
> ```

**Check:** `hailortcli fw-control identify` should print the device (Hailo-8, 26 TOPS
variant). If it prints nothing, work through the diagnostic ladder in
[Troubleshooting](#troubleshooting) below.

Download the person-detection model (YOLOv8s compiled for Hailo-8, `.hef`):

```bash
mkdir -p ~/costume-spotter-data/models
wget -O ~/costume-spotter-data/models/yolov8s_h8.hef \
  https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v2.14.0/hailo8/yolov8s.hef
```

> The exact URL moves between Hailo model-zoo releases; if it 404s, get the current
> `yolov8s.hef` (Hailo-8, *not* 8L) link from
> https://github.com/hailo-ai/hailo_model_zoo — and update `HAILO_HEF_PATH` in `.env`.

## 4. Speaker

Plug in a USB speaker (simplest — the Pi 5 has no analog jack, and the GPIO
header sits under the Hailo HAT+, so DAC HATs are out) and find its ALSA device:

```bash
aplay -l                       # your speaker appears as its own card, by product name
speaker-test -c 1 -t wav -D plughw:CARD=<name-from-aplay>
```

Put the working device in `.env`, e.g. `AUDIO_DEVICE=plughw:CARD=UACDemoV10`.
Address cards by `CARD=<name>`, not number — USB card numbers reshuffle across
reboots.

Notes from a real bring-up:

- `aplay -l` showing only `vc4hdmi0/1` means the Pi sees no speaker at all —
  those are the HDMI ports. Check `lsusb`; beware Bluetooth speakers whose USB
  port is charge-only.
- **Testing with a monitor attached:** `AUDIO_DEVICE=plughw:CARD=vc4hdmi0`
  plays through the display's speakers — handy before the real speaker
  arrives. HDMI audio errors out (`-524`) when headless, so switch to the USB
  device for the porch deployment.

## 5. Piper voice (local TTS)

```bash
pip install piper-tts --break-system-packages   # or inside the venv below
mkdir -p ~/costume-spotter-data/voices && cd ~/costume-spotter-data/voices
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

**Check:** `echo "trick or treat" | piper -m en_US-lessac-medium.onnx -f test.wav && aplay test.wav`

## 6. The application

```bash
# If `git` is missing (Lite images, or §1 skipped): sudo apt install -y git
cd ~ && git clone https://github.com/<you>/pi-costume-spotter.git
cd pi-costume-spotter/edge
python3 -m venv --system-site-packages .venv   # --system-site-packages: picamera2
                                               # and hailo bindings are apt-installed
source .venv/bin/activate
pip install -e .
cp .env.example .env
nano .env
```

Set at minimum:

```ini
# The one hardware switch: pi selects Picamera2 camera + Hailo detector + ALSA
# audio. (CAMERA_SOURCE / DETECTOR exist only to override that pairing.)
EDGE_PROFILE=pi
ANTHROPIC_API_KEY=sk-ant-...   # paste your REAL key — see the API-key note below
HAILO_HEF_PATH=/home/pi/costume-spotter-data/models/yolov8s_h8.hef
PIPER_VOICE_PATH=/home/pi/costume-spotter-data/voices/en_US-lessac-medium.onnx
AUDIO_DEVICE=plughw:1,0
DATA_DIR=/home/pi/costume-spotter-data
```

**The API-key note (learned the hard way, twice):**

- A real key is `sk-ant-api03-` + ~90 more characters, all ASCII. The console
  shows it **in full exactly once**, at creation — the `sk-ant-…xyz` shown in
  the key list afterwards is a truncated *display*, and pasting it puts a real
  Unicode ellipsis in your config. The app now refuses to start on a non-ASCII
  key rather than failing per-visitor.
- Shell environment variables **override** `.env`. If identification still
  fails after fixing the file, run `env | grep ANTHROPIC` — a stale
  `export ANTHROPIC_API_KEY=…` in `~/.bashrc` wins over everything.

**Check (the big one):** from `pi-costume-spotter/edge` with the venv active,
`python -m costume_spotter`, then open
`http://<pi-ip>:8000` from a laptop, walk in front of the camera in a hat. You should
see yourself boxed on the live feed, hear a comment, and see the sighting in the log.

## 7. Run as a service

```bash
sudo cp deploy/costume-spotter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now costume-spotter
```

**Check:** `systemctl status costume-spotter` is `active (running)`; reboot and
confirm it comes back by itself. Logs: `journalctl -u costume-spotter -f`.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `hailortcli` not found / no device | `hailo-all` not installed, or PCIe ribbon loose — see the ladder below |
| `Failed to allocate buffers` from Picamera2 | Increase CMA memory: add `dtoverlay=vc4-kms-v3d,cma-512` to `/boot/firmware/config.txt` |
| "No cameras available!" and dmesg shows `imx500 ... probe failed with error -121` (`setup of GPIO led failed`) | The camera's onboard RP2040 wasn't ready when the driver probed — a cold-boot race, not a wiring fault. Recover: `sudo modprobe -r imx500 && sudo modprobe imx500`. The systemd unit self-heals this via `deploy/ensure-camera.sh` |
=======
| "libcamera sees no cameras" at startup (older builds: bare `IndexError` from `Picamera2()`) | The OS lost the camera: check `rpicam-hello --list-cameras`, reseat the CSI ribbon at both ends (easily disturbed while mounting the Hailo HAT), confirm `imx500-all` is installed and `camera_auto_detect=1` in config.txt, reboot |

| Detection runs but < 10 fps | Check `HAILO_HEF_PATH` points to a Hailo-**8** (not 8L) model; check thermals (`vcgencmd measure_temp`) |
| No audio | Wrong `AUDIO_DEVICE`; re-run `aplay -l`; USB speakers sometimes enumerate as card 2 after reboot — consider an `/etc/asound.conf` default |
| Comments are always "mystery guest" | No/invalid `ANTHROPIC_API_KEY`, or no internet — check `/api/health` |

### "hailortcli fw-control identify returns nothing" — the diagnostic ladder

The first question is whether the PCIe bus sees the chip at all:

```bash
lspci | grep -i hailo
```

**`lspci` shows nothing → physical / PCIe config:**

1. **Reseat the ribbon** (the most common cause). Power off and unplug. Each end
   of the flat-flex cable has a latch: flip it up, insert the ribbon straight
   and fully — a slightly angled insertion produces exactly this silent failure
   — and close the latch firmly. Check *both* ends and the orientation markings.
2. **Update firmware / force-enable PCIe.** `sudo rpi-eeprom-update` (apply with
   `-a` + reboot if an update is available). The HAT's EEPROM should auto-enable
   the PCIe port, but on older firmware add to `/boot/firmware/config.txt`:
   ```ini
   dtparam=pciex1
   dtparam=pciex1_gen=3   # optional: full speed for the Hailo-8
   ```
3. **Check power.** PCIe enumeration failure is a classic undervoltage symptom —
   use the official 27 W PSU; `dmesg | grep -i voltage` reports throttling.

**`lspci` shows the Hailo device → driver stack:**

4. `dpkg -l | grep -i hailo` — every package should be `ii`. Nothing listed
   means the §3 install never completed; partial flags (`iU`/`iF`) mean
   `sudo apt --fix-broken install`.
5. `modinfo hailo_pci` — **"Module not found" is the Trixie case** (see the
   note in §3): the kernel has no in-tree driver and dkms was never able to
   build one. Fix: `sudo apt install dkms linux-headers-rpi-2712`, then
   `sudo apt install --reinstall hailort-pcie-driver`, reboot. `sudo dkms status`
   should then say `installed`.
6. `dmesg | grep -i hailo` after `sudo modprobe hailo_pci` — a *version
   mismatch* message means driver and HailoRT library are out of sync
   (`sudo apt full-upgrade` + reinstall `hailo-all`); a *firmware file not
   found* message means `/lib/firmware/hailo/` is missing its blob
   (reinstall `hailort-pcie-driver`, which carries it).
7. `ls /dev/hailo*` — once `/dev/hailo0` exists, `identify` will answer.

Diagnosed symptoms in one line each: package set healthy + device on the bus +
`modprobe: FATAL: Module hailo_pci not found` = case 5 above. A `hailortcli`
that prints *nothing at all* (no error) is this same case — the runtime is
installed but has no driver to talk through.

When `identify` prints the board details (Hailo-8, 26 TOPS), resume at §3.
