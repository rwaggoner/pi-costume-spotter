# ADR-006: Cloud SQL (PostgreSQL) as the cloud tier's database

**Status:** Accepted

## Context

The cloud tier stores durable sighting history and serves aggregate queries
([requirements 07](../requirements/07-cloud.md)). Volume is tiny (thousands of rows),
but the choice signals database design skill, and cost matters for a hobby-scale
deployment.

## Options

| Option | Pros | Cons |
|--------|------|------|
| **Cloud SQL / PostgreSQL (chosen)** | Real relational modeling: schema, constraints, indexes, migrations, SQL analytics; the industry-default skill set on display; `ON CONFLICT DO NOTHING` gives trivial idempotent ingest (07-F4) | ~$10/mo idle cost on `db-f1-micro` (it's a VM, not serverless); needs the Cloud SQL connector from Cloud Run |
| Firestore | Serverless, zero idle cost, generous free tier | Document model shows less DB skill; aggregates (counts by costume) are awkward; no schema/constraints — idempotency needs app logic |
| BigQuery | Superb analytics, pennies at this scale | It's a warehouse: no primary keys/upserts (idempotency is painful), streaming-insert quirks; wrong tool as an operational store |

## Decision

**Cloud SQL (PostgreSQL)** — explicitly chosen by the project owner with the idle cost
understood. Skill-showcase weight beats cost here: relational schema design, Flyway
migrations, unique-constraint-based idempotency, and SQL aggregates are exactly the
"database management" competencies the portfolio should demonstrate.

Cost mitigations documented in [setup-gcp.md](../setup-gcp.md):
- smallest tier (`db-f1-micro`, shared core) with no HA and minimal storage;
- `terraform destroy` teardown runbook, and a stop-instance note for pauses;
- everything else in the stack (Cloud Run, Pub/Sub) scales to zero, so the DB is the
  *only* idle cost.

## Consequences

- The ingest service carries a real migration story (Flyway `V1__…​.sql` files) —
  contrasting deliberately with the edge's create-on-start SQLite (see ADR-004).
- Connection management matters (Cloud Run can scale out): the service uses a small
  HikariCP pool and the Cloud SQL Java connector.
- If this ran 24/7/365 long-term, revisiting Firestore (or turning the instance off
  outside demo periods) would be the fiscally sane move; the ADR trail makes that an
  easy, documented pivot.
