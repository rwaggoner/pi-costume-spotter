/**
 * Wire formats: the Pub/Sub push envelope and the sighting it carries.
 *
 * Pub/Sub push subscriptions POST a JSON envelope whose `message.data` field is
 * the base64 of whatever the publisher sent — in our case the JSON built by
 * edge/costume_spotter/cloudsync/pubsub_publisher.py. Both shapes are modeled
 * explicitly here so a malformed payload fails *decoding*, in one place, rather
 * than surfacing as nulls deep in SQL code (07-F5).
 */
package com.costumespotter.ingest

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.util.Base64
import java.util.UUID

/** What Pub/Sub POSTs to us. Fields we don't use are omitted (Json ignores them). */
@Serializable
data class PushEnvelope(val message: PushMessage, val subscription: String? = null)

@Serializable
data class PushMessage(val data: String, val messageId: String? = null)

/** The sighting as published by the Pi — text metadata only, never pixels (05-N1). */
@Serializable
data class Sighting(
    val id: String,
    val spotted_at: String, // ISO-8601, UTC, straight from the edge
    val costume: String? = null, // null = person in regular clothes (03-F3)
    val confidence: String,
    val comment: String,
    val device_id: String,
) {
    /**
     * Validation beyond what the type system gives us. The UUID check matters
     * most: `id` is the idempotency key AND the primary key (07-F4), so garbage
     * there must be rejected as non-retryable rather than inserted.
     */
    fun validate(): Sighting {
        UUID.fromString(id) // throws IllegalArgumentException if not a UUID
        require(comment.isNotBlank()) { "comment must not be blank" }
        require(confidence in setOf("high", "medium", "low", "unknown")) {
            "unexpected confidence '$confidence'"
        }
        return this
    }
}

private val json = Json { ignoreUnknownKeys = true }

/** Envelope JSON -> validated Sighting. Every failure mode throws — callers map that to 400. */
fun decodeSighting(envelopeBody: String): Sighting {
    val envelope = json.decodeFromString<PushEnvelope>(envelopeBody)
    val payload = String(Base64.getDecoder().decode(envelope.message.data))
    return json.decodeFromString<Sighting>(payload).validate()
}
