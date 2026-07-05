# cloud/ingest-service — sightings ingest on Cloud Run

Kotlin + Ktor. Receives sightings from a Pub/Sub **push** subscription, writes
them idempotently to Cloud SQL (PostgreSQL), and serves a small read API.
Why Kotlin/Ktor: [ADR-009](../../docs/decisions/009-kotlin-ingest.md).
Requirements: [07-cloud.md](../../docs/requirements/07-cloud.md).

## The interesting parts

- [`Messages.kt`](src/main/kotlin/com/costumespotter/ingest/Messages.kt) — decodes
  the Pub/Sub envelope; every malformed-payload path fails *here*, mapped to
  HTTP 400 so poison messages dead-letter instead of looping (07-F5).
- [`SightingRepository.kt`](src/main/kotlin/com/costumespotter/ingest/SightingRepository.kt) —
  plain JDBC with the SQL visible; `INSERT … ON CONFLICT (id) DO NOTHING` is the
  entire idempotency story (07-F4), because the primary key is the UUID the Pi minted.
- [`db/migration/`](src/main/resources/db/migration/) — Flyway migrations, run at
  startup. This Postgres holds durable data, so it gets real migrations — unlike
  the edge's disposable SQLite (contrast argued in [ADR-004](../../docs/decisions/004-sqlite-edge.md)).

## Build & test

No local Java required for deployment — Cloud Build compiles the
[Dockerfile](Dockerfile) remotely ([docs/setup-gcp.md](../../docs/setup-gcp.md) §1),
and CI runs the tests with its own Gradle. With a JDK installed locally:

```bash
gradle test    # JUnit; repository/route tests run on H2 in PostgreSQL mode
gradle run     # needs DB_URL / DB_USER / DB_PASSWORD env vars
```

## Endpoints

| Route | Purpose |
|-------|---------|
| `POST /pubsub` | Pub/Sub push target. 204 = stored (or duplicate), 400 = dead-letter-bound, 5xx = retry me |
| `GET /healthz` | Liveness |
| `GET /api/sightings?limit=50` | Recent sightings, newest first |
| `GET /api/stats` | Total + costume leaderboard |
