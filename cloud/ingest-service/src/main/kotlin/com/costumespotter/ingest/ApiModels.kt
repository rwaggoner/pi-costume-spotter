/** Response models for the read API (07-F7). Serialized by kotlinx.serialization. */
package com.costumespotter.ingest

import kotlinx.serialization.Serializable

@Serializable
data class StoredSighting(
    val id: String,
    val spotted_at: String,
    val ingested_at: String,
    val costume: String?,
    val confidence: String,
    val comment: String,
    val device_id: String,
)

@Serializable
data class CostumeCount(val costume: String, val count: Long)

@Serializable
data class StatsResponse(val total: Long, val topCostumes: List<CostumeCount>)
