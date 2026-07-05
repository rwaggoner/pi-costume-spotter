# 01 — Person Detection

## Purpose

Find people in each camera frame, in real time, entirely on-device. Detection is the
front of the pipeline: everything downstream depends on its boxes. It must be fast
enough that the live feed looks live, and cheap enough that the Pi 5 (4 GB) has CPU
left for the API server and TTS.

## Functional requirements

| ID | Requirement |
|----|-------------|
| 01-F1 | Detect people (COCO class `person`) in camera frames and emit axis-aligned bounding boxes with confidence scores. |
| 01-F2 | Run inference on the Hailo-8 accelerator on the Pi (`EDGE_PROFILE=pi`). The host CPU must not run the neural network. |
| 01-F3 | Provide a mock implementation (`EDGE_PROFILE=dev`) that produces detections on a laptop with no accelerator — from a webcam or a looping sample video — so the whole pipeline is testable off-device. |
| 01-F4 | Expose detections as plain data (`Detection(box, confidence, class)`) — downstream code must never import Hailo/IMX500 SDKs. |
| 01-F5 | Detections below a configurable confidence threshold (default 0.5) are discarded at the source. |
| 01-F6 | Detector failures (driver missing, model file absent) must fail fast at startup with an actionable error message, not degrade silently. |

## Non-functional requirements

| ID | Requirement |
|----|-------------|
| 01-N1 | ≥ 15 fps end-to-end on the Pi at 1280×720 (target 30 fps; the Hailo-8 runs YOLOv8s at well over 100 fps, so the camera pipeline is the practical limit). |
| 01-N2 | Detection latency (frame captured → boxes available) < 100 ms. |
| 01-N3 | All camera frames stay in memory on-device; raw frames are never written to disk or network by this component. |

## Notes & interactions

- Model choice (YOLOv8s vs the IMX500's on-sensor option) is analyzed in
  [ADR-001](../decisions/001-hailo-vs-imx500.md).
- The detector does **not** decide what a "visitor" is — that is tracking's job
  ([02-tracking.md](02-tracking.md)). The detector is intentionally stateless.
