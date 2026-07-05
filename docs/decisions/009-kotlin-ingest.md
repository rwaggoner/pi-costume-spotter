# ADR-009: Kotlin + Ktor on Cloud Run for the ingest service

**Status:** Accepted

## Context

The cloud tier needs a service that receives Pub/Sub push messages and writes to
Cloud SQL ([requirements 07](../requirements/07-cloud.md)). Functionally this is small
(~an afternoon in any language) — so the language choice is driven largely by the
portfolio goal of demonstrating JVM-ecosystem competence alongside the Python edge and
TypeScript frontend.

## Options

| Option | Pros | Cons |
|--------|------|------|
| **Kotlin + Ktor (chosen)** | Demonstrates modern JVM development: coroutines, kotlinx.serialization, Gradle Kotlin DSL, HikariCP, Flyway; Ktor is lightweight → fast Cloud Run cold starts; Kotlin reads cleanly for a public repo | JVM cold start slower than Go/Python (mitigated: Ktor+CIO is lean, and this path is not latency-critical) |
| Kotlin + Spring Boot | The dominant enterprise stack — high recognition value | Heavy for a one-endpoint service; slow cold starts on scale-to-zero; framework magic obscures the readable-code goal |
| Java + Spring Boot | Maximum "Java on the resume" | Same weight concerns; and the repo already shows JVM skills better through idiomatic Kotlin (Java interop is inherent to the build) |
| Python (FastAPI) again | One backend language; fastest to write | Zero new skills demonstrated; the explicit brief was to include Java/Kotlin |
| Cloud Function (any lang) | Least infrastructure | Less to show: no container, no service design; cold-start and runtime limits |

## Decision

**Kotlin + Ktor**, containerized (multi-stage Dockerfile, JRE-slim runtime image) on
Cloud Run with scale-to-zero. Stack details: Ktor (CIO engine) for HTTP,
kotlinx.serialization for the Pub/Sub envelope, HikariCP + plain JDBC for data access
(a full ORM like Exposed/Hibernate would hide the SQL this service exists to
showcase), Flyway for migrations, JUnit 5 + Testcontainers-free unit tests (the
repository layer is tested against H2 in Postgres mode; CI has no Docker-in-Docker
dependency).

Spring Boot was the closest runner-up — its ubiquity is itself a portfolio argument —
but a one-route service under Spring is mostly annotations and autoconfiguration,
which demonstrates framework familiarity rather than engineering. Ktor keeps every
moving part visible in ~300 lines.

## Consequences

- The repo shows three languages in production roles (Python, TypeScript, Kotlin),
  each where it's strong.
- JVM build requires no local Java for contributors: CI (and Cloud Build) compile it;
  the Gradle wrapper pins the toolchain.
- Cold starts add ~1–2 s to the first sighting after idle — within the 10 s budget (07-N2).
