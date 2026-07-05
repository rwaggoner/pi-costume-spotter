# ADR-001: Person detection on the Hailo-8 HAT+, not the IMX500's on-sensor NPU

**Status:** Accepted

## Context

The hardware includes *two* AI accelerators: the Raspberry Pi AI Camera's Sony IMX500
(an image sensor with a small NPU on the sensor die) and the Hailo AI HAT+ (a Hailo-8
with 26 TOPS on the PCIe bus). Person detection ([requirements 01](../requirements/01-detection.md))
could run on either. We need to pick a primary.

## Options

### A — Hailo-8 HAT+ (chosen)

| Pros | Cons |
|------|------|
| 26 TOPS: runs YOLOv8s (or larger) at way beyond camera frame rate, with headroom for future models | Occupies the PCIe port and needs the HailoRT driver stack installed |
| Rich, actively maintained model zoo (`hailo_model_zoo`) with precompiled `.hef` files | Detection consumes some host CPU for pre/post-processing |
| Host receives full raw frames — the same frame is used for detection, MJPEG streaming, and snapshots | Extra ~2.5 W power draw |
| Well-trodden Picamera2 + Hailo examples from Raspberry Pi themselves | |

### B — IMX500 on-sensor NPU

| Pros | Cons |
|------|------|
| Zero host CPU for inference — detections arrive as metadata alongside frames | Small NPU: limited to compact models (e.g. SSD MobileNet, nanodet), lower accuracy on partial/occluded people |
| No extra HAT required; lower power | Model must be converted/packaged for the IMX500 toolchain — much smaller ecosystem |
| Elegant "smart sensor" story | Detection tied to the camera's own processing pipeline; less flexible resolution/ROI control |

### C — Both simultaneously (IMX500 as first-stage gate, Hailo for confirmation)

| Pros | Cons |
|------|------|
| Maximum hardware utilization; interesting demo | Significant complexity for no accuracy win at porch scale; two driver stacks to debug; harder to reason about — conflicts with the readability goal |

## Decision

**Option A.** The Hailo-8 is dramatically more capable, better documented, and keeps
the pipeline simple: one detector, full frames on the host. The 4 GB Pi 5 has enough
CPU headroom for pre/post-processing at 30 fps.

The `Detector` interface ([ADR-008](008-hardware-abstraction.md)) keeps Option B
available: an `IMX500Detector` can be dropped in without touching any downstream code,
and the codebase documents where it would slot in.

## Consequences

- Detection accuracy benefits from YOLOv8s; small/occluded costumes are detected more reliably.
- The project requires the HailoRT runtime installed on the Pi ([setup-pi.md](../setup-pi.md)).
- The AI Camera is used purely as a (very good) camera; its NPU idles. That's an
  acceptable cost for a simpler, more capable primary path.
