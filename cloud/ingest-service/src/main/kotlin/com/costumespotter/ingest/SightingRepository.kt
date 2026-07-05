/**
 * Data access for sightings: plain JDBC, visible SQL.
 *
 * No ORM by design (ADR-009): this service exists partly to demonstrate SQL —
 * hiding the one interesting INSERT behind an entity mapper would defeat that.
 * Every method borrows a pooled connection and returns it via `use`.
 */
package com.costumespotter.ingest

import java.sql.ResultSet
import java.sql.Timestamp
import java.time.OffsetDateTime
import java.util.UUID
import javax.sql.DataSource

class SightingRepository(private val dataSource: DataSource) {

    /**
     * Idempotent insert (07-F4): Pub/Sub delivers at-least-once, so the same
     * sighting may arrive twice. ON CONFLICT DO NOTHING makes the second
     * delivery a harmless no-op; the return value says which happened, so the
     * route can log redeliveries honestly.
     */
    fun insertIfNew(sighting: Sighting): Boolean {
        dataSource.connection.use { conn ->
            conn.prepareStatement(
                """
                INSERT INTO sightings (id, spotted_at, costume, confidence, comment, device_id)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING
                """.trimIndent(),
            ).use { stmt ->
                stmt.setObject(1, UUID.fromString(sighting.id))
                stmt.setTimestamp(2, Timestamp.from(OffsetDateTime.parse(sighting.spotted_at).toInstant()))
                stmt.setString(3, sighting.costume)
                stmt.setString(4, sighting.confidence)
                stmt.setString(5, sighting.comment)
                stmt.setString(6, sighting.device_id)
                return stmt.executeUpdate() == 1 // 0 = duplicate, swallowed by ON CONFLICT
            }
        }
    }

    /** Recent sightings for the read API (07-F7), newest first. */
    fun recent(limit: Int = 50): List<StoredSighting> {
        dataSource.connection.use { conn ->
            conn.prepareStatement(
                """
                SELECT id, spotted_at, ingested_at, costume, confidence, comment, device_id
                FROM sightings ORDER BY spotted_at DESC LIMIT ?
                """.trimIndent(),
            ).use { stmt ->
                stmt.setInt(1, limit.coerceIn(1, 500))
                stmt.executeQuery().use { rs ->
                    return generateSequence { if (rs.next()) rs.toStoredSighting() else null }.toList()
                }
            }
        }
    }

    fun total(): Long {
        dataSource.connection.use { conn ->
            conn.createStatement().use { stmt ->
                stmt.executeQuery("SELECT COUNT(*) FROM sightings").use { rs ->
                    rs.next()
                    return rs.getLong(1)
                }
            }
        }
    }

    /** Costume leaderboard — the aggregate the dashboard cares about. */
    fun costumeCounts(): List<CostumeCount> {
        dataSource.connection.use { conn ->
            conn.prepareStatement(
                """
                SELECT costume, COUNT(*) AS n FROM sightings
                WHERE costume IS NOT NULL
                GROUP BY costume ORDER BY n DESC LIMIT 20
                """.trimIndent(),
            ).use { stmt ->
                stmt.executeQuery().use { rs ->
                    return generateSequence {
                        if (rs.next()) CostumeCount(rs.getString("costume"), rs.getLong("n")) else null
                    }.toList()
                }
            }
        }
    }
}

private fun ResultSet.toStoredSighting() = StoredSighting(
    id = getObject("id").toString(),
    spotted_at = getTimestamp("spotted_at").toInstant().toString(),
    ingested_at = getTimestamp("ingested_at").toInstant().toString(),
    costume = getString("costume"),
    confidence = getString("confidence"),
    comment = getString("comment"),
    device_id = getString("device_id"),
)
