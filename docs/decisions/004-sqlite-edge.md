# ADR-004: SQLite for edge persistence

**Status:** Accepted

## Context

Sightings must survive restarts and power the dashboard's history/stats
([requirements 05](../requirements/05-storage.md)). Write rate is tiny (a busy night =
hundreds of rows); readers are the API endpoints.

## Options

| Option | Pros | Cons |
|--------|------|------|
| **SQLite (chosen)** | Zero administration, single file, in the stdlib ecosystem, ACID, plenty fast at this scale; trivially backed up (`cp`) | Single-writer — irrelevant here (one process); limited concurrent-write throughput — irrelevant |
| PostgreSQL on the Pi | "Real" DB, same engine as cloud tier | A daemon to install/tune/monitor on a 4 GB Pi for hundreds of rows/day — pure overhead |
| JSON-lines / CSV files | Even simpler | No queries (stats need GROUP BY), no indexes, manual pagination, corruption risk on power cut |

## Decision

**SQLite via SQLAlchemy.** SQLAlchemy (rather than raw `sqlite3`) buys: declarative
models readable as schema documentation, and dialect portability that makes the
repository layer's patterns identical to what you'd write against Postgres —
relevant since this repo also demonstrates a Postgres tier in the cloud.

Schema management is `metadata.create_all()` at startup rather than Alembic
migrations: the edge DB holds disposable, auto-pruned data (7-day retention), so
"delete the file" is an acceptable migration strategy. The cloud tier, which holds
durable data, gets real migrations (Flyway — [requirements 07-F6](../requirements/07-cloud.md)).
That contrast is deliberate and instructive: migration rigor should match data
durability.

## Consequences

- Backup/restore is file copy; the DB file lives outside the repo tree and is gitignored.
- WAL mode is enabled so dashboard reads never block pipeline writes.
- If multi-process access were ever needed (it isn't planned), this decision must be revisited.
