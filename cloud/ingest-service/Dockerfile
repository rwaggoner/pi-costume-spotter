# Multi-stage build: Gradle compiles in a full JDK image; the runtime image is
# a slim JRE. Built remotely by Cloud Build (docs/setup-gcp.md §1), so
# contributors never need Java locally.

FROM gradle:8.13-jdk21 AS build
WORKDIR /app
# Dependency layer first: docker caches it unless build files change.
COPY build.gradle.kts settings.gradle.kts ./
RUN gradle dependencies --no-daemon -q || true
COPY src ./src
RUN gradle installDist --no-daemon

FROM eclipse-temurin:21-jre-jammy
WORKDIR /app
COPY --from=build /app/build/install/costume-ingest/ ./
# Cloud Run sets PORT; the app reads it (Application.kt).
ENTRYPOINT ["./bin/costume-ingest"]
