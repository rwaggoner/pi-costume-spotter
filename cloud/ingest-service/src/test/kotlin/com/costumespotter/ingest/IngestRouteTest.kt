/**
 * The service end-to-end, in-process: Ktor test host + H2 in PostgreSQL mode.
 *
 * H2-as-Postgres keeps CI free of Docker while exercising the real migration
 * and the real SQL (including ON CONFLICT — supported in H2's pg mode). The
 * one thing it can't prove is Cloud SQL connectivity, which the deployment
 * runbook verifies instead (docs/setup-gcp.md §4).
 */
package com.costumespotter.ingest

import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpStatusCode
import io.ktor.server.testing.testApplication
import java.util.Base64
import java.util.UUID
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

private fun freshRepository(): SightingRepository {
    // A uniquely-named in-memory DB per test → full isolation, no cleanup.
    val dataSource = connectAndMigrate(
        url = "jdbc:h2:mem:${UUID.randomUUID()};MODE=PostgreSQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
        user = "sa",
        password = "",
    )
    return SightingRepository(dataSource)
}

private fun pushBody(id: String, costume: String = "robot"): String {
    val payload = """{
        "id": "$id",
        "spotted_at": "2026-07-03T12:00:00+00:00",
        "costume": "$costume",
        "confidence": "high",
        "comment": "Beep boop!",
        "device_id": "test-pi"
    }"""
    return """{"message": {"data": "${Base64.getEncoder().encodeToString(payload.toByteArray())}"}}"""
}

class IngestRouteTest {

    private val id = "22222222-2222-2222-2222-222222222222"

    @Test
    fun `stores a pushed sighting and serves it back`() = testApplication {
        val repository = freshRepository()
        application { configure(repository) }

        val push = client.post("/pubsub") { setBody(pushBody(id)) }
        assertEquals(HttpStatusCode.NoContent, push.status)

        val listed = client.get("/api/sightings").bodyAsText()
        assertTrue(id in listed && "robot" in listed)
    }

    @Test
    fun `redelivery of the same sighting is acknowledged not duplicated`() = testApplication {
        val repository = freshRepository()
        application { configure(repository) }

        repeat(3) { // Pub/Sub at-least-once, simulated (07-F4)
            assertEquals(HttpStatusCode.NoContent, client.post("/pubsub") { setBody(pushBody(id)) }.status)
        }
        assertEquals(1, repository.total())
    }

    @Test
    fun `malformed message gets 400 so it can dead-letter`() = testApplication { // 07-F5
        application { configure(freshRepository()) }

        val response = client.post("/pubsub") { setBody("""{"message": {"data": "bm90IGpzb24="}}""") }
        assertEquals(HttpStatusCode.BadRequest, response.status)
    }

    @Test
    fun `stats aggregates by costume`() = testApplication {
        val repository = freshRepository()
        application { configure(repository) }

        client.post("/pubsub") { setBody(pushBody("33333333-3333-3333-3333-333333333333", "witch")) }
        client.post("/pubsub") { setBody(pushBody("44444444-4444-4444-4444-444444444444", "witch")) }
        client.post("/pubsub") { setBody(pushBody("55555555-5555-5555-5555-555555555555", "robot")) }

        val stats = client.get("/api/stats").bodyAsText()
        assertTrue("\"total\":3" in stats)
        assertTrue(stats.indexOf("witch") < stats.indexOf("robot")) // ordered by count desc
    }

    @Test
    fun `healthz answers`() = testApplication {
        application { configure(freshRepository()) }
        assertEquals("ok", client.get("/healthz").bodyAsText())
    }
}
