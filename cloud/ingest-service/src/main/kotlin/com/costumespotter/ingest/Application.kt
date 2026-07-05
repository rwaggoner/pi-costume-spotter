/**
 * The service: a Ktor server with one write route (the Pub/Sub push target) and
 * a small read API (07-F7). Small enough to read in one sitting — that's the
 * point (ADR-009).
 *
 * HTTP status contract for /pubsub, which is what Pub/Sub retry logic sees:
 *   204 — stored (or duplicate: already stored, still success)
 *   400 — malformed message. Pub/Sub retries then routes to the dead-letter
 *         topic after max attempts (07-F5); a poison message can't loop forever.
 *   5xx — our problem (DB down): Pub/Sub keeps retrying with backoff, which is
 *         exactly what we want for transient faults.
 */
package com.costumespotter.ingest

import io.ktor.http.HttpStatusCode
import io.ktor.serialization.kotlinx.json.json
import io.ktor.server.application.Application
import io.ktor.server.application.install
import io.ktor.server.cio.CIO
import io.ktor.server.engine.embeddedServer
import io.ktor.server.plugins.contentnegotiation.ContentNegotiation
import io.ktor.server.request.receiveText
import io.ktor.server.response.respond
import io.ktor.server.response.respondText
import io.ktor.server.routing.get
import io.ktor.server.routing.post
import io.ktor.server.routing.routing
import org.slf4j.LoggerFactory

private val log = LoggerFactory.getLogger("ingest")

fun main() {
    // 12-factor configuration; Cloud Run injects PORT, Terraform injects the rest.
    val port = System.getenv("PORT")?.toInt() ?: 8080
    val dataSource = connectAndMigrate(
        url = requireNotNull(System.getenv("DB_URL")) { "DB_URL is required" },
        user = System.getenv("DB_USER") ?: "ingest",
        password = requireNotNull(System.getenv("DB_PASSWORD")) { "DB_PASSWORD is required" },
    )
    val repository = SightingRepository(dataSource)

    embeddedServer(CIO, port = port) { configure(repository) }.start(wait = true)
}

/** Route wiring, separated from main() so tests can run it in-process. */
fun Application.configure(repository: SightingRepository) {
    install(ContentNegotiation) { json() }

    routing {
        get("/healthz") {
            call.respondText("ok")
        }

        post("/pubsub") {
            val sighting = try {
                decodeSighting(call.receiveText())
            } catch (e: Exception) { // any decode/validation failure → non-retryable
                log.warn("rejecting malformed push message: {}", e.message)
                call.respond(HttpStatusCode.BadRequest, mapOf("error" to (e.message ?: "bad message")))
                return@post
            }
            val inserted = repository.insertIfNew(sighting)
            if (!inserted) {
                // At-least-once delivery doing its thing; worth counting, not worth failing.
                log.info("duplicate delivery for sighting {} — acknowledged", sighting.id)
            }
            call.respond(HttpStatusCode.NoContent)
        }

        get("/api/sightings") {
            val limit = call.request.queryParameters["limit"]?.toIntOrNull() ?: 50
            call.respond(repository.recent(limit))
        }

        get("/api/stats") {
            call.respond(StatsResponse(total = repository.total(), topCostumes = repository.costumeCounts()))
        }
    }
}
