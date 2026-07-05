# 05 — Storage & Privacy

## Purpose

Persist every sighting so the dashboard can show history and stats, and define the
project's privacy posture — this system films people, and the repository is public, so
the rules about what is stored where must be explicit and enforced by code, not
convention.

## Functional requirements

| ID | Requirement |
|----|-------------|
| 05-F1 | Persist each sighting to SQLite on the Pi ([ADR-004](../decisions/004-sqlite-edge.md)): UUID, timestamp (UTC), costume label, confidence, comment, whether it was spoken, snapshot filename, detection metadata (box, detector backend). |
| 05-F2 | Save the visitor's cropped snapshot as a JPEG in a dedicated snapshots directory, named by sighting UUID. |
| 05-F3 | Auto-prune: a background job deletes snapshots **and** their sighting rows older than a configurable retention window (default 7 days), running at startup and daily. |
| 05-F4 | Expose repository query methods for the API: recent sightings (paginated), costume counts, sightings-per-hour histogram. |
| 05-F5 | The schema is created/migrated automatically at startup (SQLAlchemy metadata; the edge DB is disposable cache-like data, so full migration tooling is overkill — noted in ADR-004). |

## Non-functional requirements (the privacy contract)

| ID | Requirement |
|----|-------------|
| 05-N1 | Snapshots exist **only** on the Pi's filesystem. They are excluded from git (`.gitignore`), never published to Pub/Sub, and never uploaded to GCP. Only text metadata (label, comment, timestamp) leaves the device. |
| 05-N2 | No face recognition, no identity persistence, no cross-visit correlation. Visitor IDs are session-scoped integers that reset on restart. |
| 05-N3 | Retention default of 7 days; setting `SNAPSHOT_RETENTION_DAYS=0` disables snapshot storage entirely (metadata-only mode). |
| 05-N4 | A sighting write (row + JPEG) completes in < 50 ms and runs off the event loop. |

## Edge schema

```sql
CREATE TABLE sightings (
    id            TEXT PRIMARY KEY,   -- UUID4, generated on the edge; reused by the
                                      -- cloud tier for idempotent ingest (07-F4)
    spotted_at    TIMESTAMP NOT NULL, -- UTC
    costume       TEXT,               -- NULL = person in regular clothes (03-F3)
    confidence    TEXT NOT NULL,      -- high | medium | low | unknown
    comment       TEXT NOT NULL,
    spoken        BOOLEAN NOT NULL DEFAULT 0,
    snapshot_file TEXT,               -- NULL in metadata-only mode
    detector      TEXT NOT NULL,      -- hailo | imx500 | mock
    box_json      TEXT NOT NULL       -- bounding box for the dashboard overlay
);
CREATE INDEX ix_sightings_spotted_at ON sightings (spotted_at);
```
