/**
 * Envelope decoding + validation: the gate that decides retryable vs poison (07-F5).
 */
package com.costumespotter.ingest

import java.util.Base64
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull

private fun envelope(payload: String): String {
    val data = Base64.getEncoder().encodeToString(payload.toByteArray())
    return """{"message": {"data": "$data", "messageId": "m1"}, "subscription": "s"}"""
}

private const val VALID = """{
    "id": "11111111-1111-1111-1111-111111111111",
    "spotted_at": "2026-07-03T12:00:00+00:00",
    "costume": "witch",
    "confidence": "high",
    "comment": "Nice hat!",
    "device_id": "porch-pi"
}"""

class MessagesTest {

    @Test
    fun `decodes a valid envelope`() {
        val sighting = decodeSighting(envelope(VALID))
        assertEquals("witch", sighting.costume)
        assertEquals("porch-pi", sighting.device_id)
    }

    @Test
    fun `null costume survives decoding`() { // 03-F3: "no costume" is a real case
        val sighting = decodeSighting(envelope(VALID.replace("\"witch\"", "null")))
        assertNull(sighting.costume)
    }

    @Test
    fun `non-UUID id is rejected`() { // the idempotency key must be sane (07-F4)
        assertFailsWith<IllegalArgumentException> {
            decodeSighting(envelope(VALID.replace("11111111-1111-1111-1111-111111111111", "not-a-uuid")))
        }
    }

    @Test
    fun `blank comment is rejected`() {
        assertFailsWith<IllegalArgumentException> {
            decodeSighting(envelope(VALID.replace("Nice hat!", "")))
        }
    }

    @Test
    fun `garbage body is rejected`() {
        assertFailsWith<Exception> { decodeSighting("{'not json'}") }
    }

    @Test
    fun `unknown envelope fields are tolerated`() { // Pub/Sub adds attributes freely
        val withExtras = envelope(VALID).replace(
            "\"subscription\": \"s\"",
            "\"subscription\": \"s\", \"deliveryAttempt\": 3",
        )
        assertEquals("witch", decodeSighting(withExtras).costume)
    }
}
