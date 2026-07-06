#!/usr/bin/env bash
# Pre-start camera check for the Costume Spotter systemd unit.
#
# Works around the AI Camera's RP2040 boot race (github issue #4, and
# docs/setup-pi.md troubleshooting): at cold boot the camera's onboard RP2040
# can still be initializing when the imx500 kernel driver probes, so the probe
# fails (-121) and the system stays camera-less until the module is reloaded.
# This script makes unattended reboots self-heal: if libcamera lists no
# camera, reload the module and re-check, up to 3 attempts.
#
# Runs as root via the "+" prefix on ExecStartPre in costume-spotter.service
# (modprobe requires it). Exits 0 when a camera is present, 1 when all
# attempts are exhausted — which fails the unit start visibly rather than
# letting the app crash on a missing camera.

set -u

camera_present() {
    rpicam-hello --list-cameras 2>/dev/null | grep -q "imx500"
}

for attempt in 1 2 3; do
    if camera_present; then
        echo "camera present (attempt ${attempt})"
        exit 0
    fi
    echo "no camera detected (attempt ${attempt}) — reloading imx500 module"
    modprobe -r imx500 2>/dev/null || true   # may not be loaded; that's fine
    sleep 2
    modprobe imx500
    sleep 3   # give the probe + RP2040 handshake a moment to settle
done

if camera_present; then
    exit 0
fi
echo "camera still absent after 3 module reloads — see docs/setup-pi.md troubleshooting" >&2
exit 1
