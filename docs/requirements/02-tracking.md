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
| 02-F2 | Publish exactly one `NewVisitorSpotted` event per tracked visitor, carrying a primary cropped snapshot plus up to two additional crops from distinct moments (issue #11) for identification to get a clearer look. |
| 02-F3 | Require a visitor to be seen for **N consecutive frames** (configurable, default 5) before announcing — a one-frame YOLO false positive on a shadow must not trigger an event. |
| 02-F4 | Retire a visitor after they have been out of frame for **T seconds** (configurable, default 30). A retired visitor who returns is treated as new — re-identification is explicitly out of scope (privacy). |
| 02-F5 | Choose the **primary** snapshot from the frame where the person's box is largest (closest / most visible); the additional crops (02-F2) come from other distinct moments so identification isn't hostage to one blurred frame. |
| 02-F6 | Support multiple simultaneous visitors with independent life cycles. |

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
