/**
 * Database bootstrap: connection pool + migrations.
 *
 * Configuration is env-vars-only (12-factor; Cloud Run injects them from
 * Terraform — see cloud/terraform/main.tf). The JDBC URL for Cloud SQL uses
 * the socket-factory form, so no IP allowlisting is involved:
 *
 *   jdbc:postgresql:///costume?cloudSqlInstance=PROJECT:REGION:INSTANCE
 *        &socketFactory=com.google.cloud.sql.postgres.SocketFactory
 *
 * Locally / in tests a plain jdbc:postgresql://localhost/... or H2 URL works
 * identically — that swap is the whole reason this module takes the URL as
 * data instead of building it.
 */
package com.costumespotter.ingest

import com.zaxxer.hikari.HikariConfig
import com.zaxxer.hikari.HikariDataSource
import org.flywaydb.core.Flyway
import javax.sql.DataSource

fun connectAndMigrate(url: String, user: String, password: String): DataSource {
    val pool = HikariDataSource(
        HikariConfig().apply {
            jdbcUrl = url
            username = user
            setPassword(password)
            // Cloud Run instances scale horizontally; keep per-instance pools tiny
            // so N instances × pool size stays under Cloud SQL's connection cap.
            maximumPoolSize = 4
        },
    )
    // Migrations run at startup, every startup: idempotent, versioned, and the
    // service can't come up against a schema it doesn't understand (07-F6).
    Flyway.configure().dataSource(pool).load().migrate()
    return pool
}
