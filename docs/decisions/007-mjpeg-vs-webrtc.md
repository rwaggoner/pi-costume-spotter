# ADR-007: Live video to the browser as MJPEG

**Status:** Accepted

## Context

The dashboard shows the live camera feed ([requirements 06](../requirements/06-dashboard.md)):
LAN-only, 1–3 viewers, sub-second latency desired, and detection boxes are overlaid
from WebSocket data (not burned into the video).

## Options

| Option | Pros | Cons |
|--------|------|------|
| **MJPEG over HTTP (chosen)** | ~40 lines of FastAPI generator code; renders in a plain `<img>` tag (no client JS); sub-second latency; frames are already JPEG-encoded for the pipeline | ~10× the bandwidth of H.264 (fine on a LAN); no audio (not needed) |
| WebRTC | Lowest latency, H.264-efficient, the "proper" answer for internet streaming | Signaling servers, SDP negotiation, ICE/STUN, an aiortc dependency, and H.264 encode load on the Pi — an order of magnitude more complexity for a porch dashboard |
| HLS/DASH | CDN-scalable | 3–10 s segment latency kills the "live" feel; ffmpeg segmenting pipeline to babysit |
| WS + JPEG frames (custom) | Single socket for video+events | Reinvents MJPEG with extra client code; no `<img>` fallback |

## Decision

**MJPEG.** The decisive factors: the deployment is LAN-only with a couple of viewers,
so MJPEG's only real weakness (bandwidth) doesn't bite; and the complexity gap is
enormous. This is a "boring technology" pick, made deliberately and documented so it
doesn't look like ignorance of WebRTC — if the feed ever needs to cross the internet
or serve many viewers, WebRTC is the named successor and the `FrameSource` →
`/stream.mjpg` seam is where it plugs in.

Detection boxes ride the existing `/ws/events` WebSocket as JSON and are drawn on a
`<canvas>` overlay — keeping video transport and metadata separate means the overlay
is toggleable and the video path stays dumb.

## Consequences

- Each connected viewer costs one JPEG stream (~2–4 MB/s at 720p/15fps); the encoder
  output is shared, so marginal cost per extra viewer is just bandwidth.
- Latency in practice: one frame + TCP — comfortably under the 1 s budget (06-N1).
- No audio path exists; the speaker's audio is physical-world only. Fine.
