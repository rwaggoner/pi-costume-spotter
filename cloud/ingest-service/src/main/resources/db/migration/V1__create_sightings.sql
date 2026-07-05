-- V1: the sightings table (docs/requirements/07-cloud.md).
--
-- Mirrors the edge's SQLite schema minus device-local columns (snapshot paths
-- never leave the Pi — privacy contract 05-N1), plus ingest metadata.
--
-- The primary key is the UUID minted on the edge: Pub/Sub delivers
-- at-least-once, and this constraint is what makes redelivery harmless (07-F4;
-- see the ON CONFLICT clause in SightingRepository.insertIfNew).

CREATE TABLE sightings (
    id          UUID PRIMARY KEY,
    spotted_at  TIMESTAMPTZ NOT NULL,           -- when the Pi saw them
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(), -- when the cloud heard about it
    costume     VARCHAR(120),                    -- NULL = no costume (03-F3)
    confidence  VARCHAR(10) NOT NULL
        CHECK (confidence IN ('high', 'medium', 'low', 'unknown')),
    comment     TEXT NOT NULL,
    device_id   VARCHAR(60) NOT NULL             -- which Pi (there could be a fleet)
);

-- The dashboard queries: recent-first listings and per-costume aggregates.
-- (A partial index "WHERE costume IS NOT NULL" would be marginally better for
-- the second one, but tests run this migration on H2, which lacks partial
-- indexes — a deliberate portability > micro-optimization trade at this scale.)
CREATE INDEX ix_sightings_spotted_at ON sightings (spotted_at DESC);
CREATE INDEX ix_sightings_costume ON sightings (costume);
