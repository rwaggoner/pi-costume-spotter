// ---------------------------------------------------------------------------
// Costume Spotter cloud ingest service (docs/decisions/009-kotlin-ingest.md).
//
// Stack choices, briefly (full reasoning in the ADR):
//  - Ktor + CIO: lightweight server -> fast Cloud Run cold starts
//  - kotlinx.serialization: decodes the Pub/Sub push envelope
//  - HikariCP + plain JDBC: the SQL stays visible (no ORM), pooled properly
//  - Flyway: real, versioned migrations — this Postgres holds durable data,
//    unlike the edge's disposable SQLite (contrast argued in ADR-004)
// ---------------------------------------------------------------------------

plugins {
    kotlin("jvm") version "2.1.20"
    kotlin("plugin.serialization") version "2.1.20"
    application
}

group = "com.costumespotter"
version = "0.1.0"

repositories {
    mavenCentral()
}

val ktorVersion = "3.1.2"

dependencies {
    // HTTP server
    implementation("io.ktor:ktor-server-cio:$ktorVersion")
    implementation("io.ktor:ktor-server-content-negotiation:$ktorVersion")
    implementation("io.ktor:ktor-serialization-kotlinx-json:$ktorVersion")

    // Data access
    implementation("com.zaxxer:HikariCP:6.2.1")
    implementation("org.postgresql:postgresql:42.7.5")
    // Connects to Cloud SQL over its managed socket from Cloud Run (no IP allowlists).
    implementation("com.google.cloud.sql:postgres-socket-factory:1.21.0")

    // Migrations
    implementation("org.flywaydb:flyway-core:11.3.4")
    implementation("org.flywaydb:flyway-database-postgresql:11.3.4")

    // Logging
    implementation("ch.qos.logback:logback-classic:1.5.16")

    // Tests: envelope decoding, repository against H2-in-Postgres-mode, routes
    // in-process — no Docker needed in CI (see ADR-009).
    testImplementation(kotlin("test"))
    testImplementation("io.ktor:ktor-server-test-host:$ktorVersion")
    testImplementation("io.ktor:ktor-client-content-negotiation:$ktorVersion")
    testImplementation("com.h2database:h2:2.3.232")
}

kotlin {
    jvmToolchain(21)
}

application {
    mainClass.set("com.costumespotter.ingest.ApplicationKt")
}

tasks.test {
    useJUnitPlatform()
}
