# 02 — Visitor Tracking

## Purpose

Convert a stream of per-frame person boxes (~30/sec) into **one event per actual
visitor**. This component is the gatekeeper for everything expensive downstream: each
`NewVisitorSpotted` event triggers a Claude API call, a database write, and speech.
Over-triggering costs money and makes the speaker babble; under-triggering misses
costumes.

## Functional requirements

| ID | Requirement |
|----|-------------|
| 02-F1 | Associate detections across frames using IoU (intersection-over-union) matching, assigning a stable visitor ID while a person remains in frame. |
| 02-F2 | Publish exactly one `NewVisitorSpotted` event per tracked visitor, carrying a cropped snapshot of the person. |
| 02-F3 | Require a visitor to be seen in **N frames** (configurable, default 3) before announcing, tolerating up to **M missed frames in a row** while counting (default 2) — a one-frame YOLO false positive on a shadow must not trigger an event, but a real person the detector blinks on (capes, masks) must not have their count restarted. |
| 02-F4 | Retire a visitor after they have been out of frame for **T seconds** (configurable, default 30). A retired visitor who returns is treated as new — re-identification is explicitly out of scope (privacy). |
| 02-F5 | Choose the snapshot from the frame where the person's box is largest (they're closest / most visible), not the first frame they appeared in at the edge of the shot. |
| 02-F6 | Support multiple simultaneous visitors with independent life cycles. |
| 02-F7 | **Groups:** visitors who arrive together are published as one `GroupSpotted`. When someone is announced while others in view are about to be, wait for them up to `GROUP_WAIT_SECONDS` (default 1 s); a lone visitor is published immediately (no added latency). Groups are capped at `GROUP_MAX_SIZE` (default 6); bigger crowds become several groups. |

## Non-functional requirements

| ID | Requirement |
|----|-------------|
| 02-N1 | Tracking adds < 5 ms per frame (it's pure Python geometry on a handful of boxes; no ML). |
| 02-N2 | Tracker state is in-memory only and bounded (visitors retire; the dict cannot grow forever). |
| 02-N3 | Deterministic and fully unit-testable with scripted box sequences — no camera or clock dependencies (time is injected). |

## The decision flow

See the flowchart in [architecture.md](../architecture.md#is-this-a-new-visitor-decision-flow).

## Design notes

A full multi-object tracker (SORT/DeepSORT with Kalman filters) was considered and
rejected: at porch scale (0–4 people, slow walking speeds) greedy IoU matching is
within a few percent of SORT's accuracy and is ~100 lines of readable, dependency-free
code — which serves this repo's readability goal better than importing a tracking
library. If the project grew to crowds, that decision should be revisited.
