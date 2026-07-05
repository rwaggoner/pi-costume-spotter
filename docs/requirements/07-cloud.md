# 07 — Cloud Tier (GCP)

## Purpose

Give sightings a durable, queryable home off the device, and demonstrate event-driven
cloud architecture: the Pi publishes events, the cloud reacts. The Pi must never
depend on the cloud being up — this tier is strictly additive
(see [architecture.md](../architecture.md#cloud-tier)).

## Functional requirements

| ID | Requirement |
|----|-------------|
| 07-F1 | The edge publishes each `CostumeIdentified` sighting (text metadata only — **no image data**, per 05-N1) to a GCP Pub/Sub topic. Publishing is disabled by default and enabled by config. |
| 07-F2 | Publish failures are logged and dropped after bounded retry — cloud unavailability must not block or crash the edge pipeline. |
| 07-F3 | A Kotlin/Ktor service on Cloud Run ([ADR-009](../decisions/009-kotlin-ingest.md)) receives sightings via a Pub/Sub **push** subscription, validates them, and inserts into Cloud SQL (PostgreSQL, [ADR-006](../decisions/006-cloud-sql.md)). |
| 07-F4 | Ingest is **idempotent**: Pub/Sub is at-least-once, so the sighting UUID (generated on the edge) is the primary key and duplicates are acknowledged without re-insert (`ON CONFLICT DO NOTHING`). |
| 07-F5 | Malformed messages are rejected with a non-retryable response so Pub/Sub routes them to a dead-letter topic after max attempts — a poison message must not loop forever. |
| 07-F6 | Database schema is versioned with Flyway migrations, run automatically at service startup. |
| 07-F7 | The service exposes `GET /healthz` (liveness) and `GET /api/sightings` + `GET /api/stats` (read API over the cloud data). |
| 07-F8 | All GCP infrastructure (topic, subscription, DLQ, Cloud SQL, Cloud Run, service accounts, IAM bindings) is defined in Terraform — nothing is click-created. |

## Non-functional requirements

| ID | Requirement |
|----|-------------|
| 07-N1 | Cloud Run scales to zero; steady-state cost is dominated by Cloud SQL (~$10/mo on `db-f1-micro`). Teardown is one `terraform destroy` and is documented, since a showcase project shouldn't bleed money ([setup-gcp.md](../setup-gcp.md)). |
| 07-N2 | Sighting visible in Cloud SQL within 10 s of the edge publishing (including a Cloud Run cold start). |
| 07-N3 | Least-privilege IAM: the edge's service account can only publish to the one topic; the ingest service account can only connect to the one database and receive pushes. |
| 07-N4 | Secrets (DB password) live in GCP Secret Manager, injected into Cloud Run as env vars by Terraform — never in code, images, or tfvars committed to git. |

## Cloud schema

Mirrors the edge schema minus device-only columns (snapshot path), plus ingest
metadata (`ingested_at`, `device_id`). Defined in
[`cloud/ingest-service/src/main/resources/db/migration/`](../../cloud/ingest-service/src/main/resources/db/migration/).
