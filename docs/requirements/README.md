# Requirements

One document per major component. Each lists **functional requirements** (what it must
do, numbered `XX-Fn` so code comments and tests can reference them) and
**non-functional requirements** (`XX-Nn`: performance, reliability, privacy).

| # | Component | Doc |
|---|-----------|-----|
| 01 | Person detection | [01-detection.md](01-detection.md) |
| 02 | Visitor tracking | [02-tracking.md](02-tracking.md) |
| 03 | Costume identification & commentary | [03-identification.md](03-identification.md) |
| 04 | Speech output | [04-speech.md](04-speech.md) |
| 05 | Storage & privacy | [05-storage.md](05-storage.md) |
| 06 | Dashboard (API + React UI) | [06-dashboard.md](06-dashboard.md) |
| 07 | Cloud tier | [07-cloud.md](07-cloud.md) |

Requirement IDs appear in tests (e.g. `test_tracker_debounces_flicker` cites `02-F3`)
and in code comments where a non-obvious constraint comes from a requirement.
