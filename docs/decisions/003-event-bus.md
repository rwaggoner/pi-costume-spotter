# ADR-003: In-process asyncio event bus as the system's spine

**Status:** Accepted

## Context

One sighting fans out to five independent reactions: identify costume, write DB row,
speak, update dashboards, publish to cloud. Some are fast (DB), some slow (Claude API,
TTS), some optional (cloud). How should components communicate?

## Options

### A — In-process async pub/sub event bus (chosen)

| Pros | Cons |
|------|------|
| Full decoupling: publishers don't know subscribers; adding a feature = adding a subscriber, zero changes to existing code | Events are lost on process crash (no persistence) — acceptable: a missed greeting is not recoverable anyway |
| A slow subscriber (Claude call) can't stall the frame loop — each subscriber consumes from its own queue | "Who handles this event?" requires reading subscriptions, not a call graph (mitigated by the event catalogue in architecture.md) |
| Trivially testable: publish a synthetic event, assert on a subscriber | Single process only — but the edge *is* a single process |
| ~80 lines of dependency-free, readable code | |

### B — Direct calls / orchestrator class

| Pros | Cons |
|------|------|
| Simplest to trace | The orchestrator accretes every concern (API calls, DB, audio, sockets); slow steps must be manually offloaded; every new feature edits the same class — the god-object trajectory |

### C — External broker (Redis pub/sub, MQTT, ZeroMQ)

| Pros | Cons |
|------|------|
| Cross-process, persistent options, industry-standard | An extra daemon on a 4 GB Pi; serialization overhead for events that carry JPEG bytes; operational surface (broker down = system down) — all for one process talking to itself |

## Decision

**Option A.** The bus (`events/bus.py`) is a small asyncio implementation: subscribers
register per event type, each gets a bounded `asyncio.Queue`, and a slow consumer
drops oldest rather than back-pressuring the camera loop. Event types are frozen
dataclasses — the schema is code, not stringly-typed dicts.

Where genuine cross-process eventing is warranted — the Pi-to-GCP hop — a real broker
(**Pub/Sub**) is used ([requirements 07](../requirements/07-cloud.md)). Same pattern,
appropriate scale at each tier.

## Consequences

- The event catalogue (architecture.md) is the de-facto system contract; keep it current.
- Subscriber errors are isolated per-subscriber (caught + logged); one crashing
  handler cannot take down the loop.
- If the system ever splits into multiple processes, the bus interface maps cleanly
  onto MQTT/Redis — the migration path is the same publish/subscribe seam.
