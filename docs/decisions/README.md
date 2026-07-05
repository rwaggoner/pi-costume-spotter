# Architecture Decision Records

Every significant technical choice in this project is captured as an ADR: the context,
the options considered with honest pros/cons, the decision, and its consequences.
The point is that a reader can disagree with a decision and still understand exactly
why it was made.

| ADR | Decision |
|-----|----------|
| [001](001-hailo-vs-imx500.md) | Run person detection on the Hailo-8 HAT+, not the AI Camera's on-sensor NPU |
| [002](002-claude-vision.md) | Identify costumes with the Claude Vision API, not a local classifier |
| [003](003-event-bus.md) | Decouple components with an in-process asyncio event bus |
| [004](004-sqlite-edge.md) | Use SQLite (not Postgres/files) for edge persistence |
| [005](005-tts-strategy.md) | Pluggable TTS: Piper default, Google Cloud TTS optional |
| [006](006-cloud-sql.md) | Cloud SQL (PostgreSQL) for the cloud tier, not Firestore/BigQuery |
| [007](007-mjpeg-vs-webrtc.md) | Stream live video as MJPEG, not WebRTC/HLS |
| [008](008-hardware-abstraction.md) | Ports & adapters at every hardware boundary (mock-first development) |
| [009](009-kotlin-ingest.md) | Kotlin + Ktor on Cloud Run for the ingest service |

Format follows [Michael Nygard's ADR template](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions),
extended with an explicit pros/cons table per option.
