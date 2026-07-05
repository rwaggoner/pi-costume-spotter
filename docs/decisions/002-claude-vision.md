# ADR-002: Costume identification via the Claude Vision API

**Status:** Accepted

## Context

Detecting a *person* is a solved edge problem (ADR-001). Naming their *costume* is
not: costumes are open-vocabulary ("inflatable T-Rex", "Wednesday Addams", "a guy in a
hot-dog suit"), and we also need a witty, family-friendly spoken comment — a language
task. [Requirements 03](../requirements/03-identification.md).

## Options

### A — Claude Vision API (chosen)

| Pros | Cons |
|------|------|
| Open vocabulary: names costumes it has never been configured for | Needs internet + API key; per-call cost (~$0.001–0.005 on Haiku) |
| One structured call returns label + confidence + comment — vision and language in a single round trip | 1–4 s latency (acceptable: visitor is still walking up) |
| Comment quality is genuinely funny and context-aware ("your tiny arms won't hold much candy") | External dependency → must design a fallback path (03-F6) |
| Showcases modern API integration: structured outputs, retries, graceful degradation | |

### B — Local zero-shot classifier (CLIP-family) + template comments

| Pros | Cons |
|------|------|
| Free, offline, private | Closed set: only matches a hand-written list of costume prompts; everything else is misclassified, and 4 GB RAM alongside everything else is tight |
| Deterministic latency | Comments are canned templates — the demo's charm evaporates |

### C — Fine-tuned local classifier

| Pros | Cons |
|------|------|
| Best on-device accuracy for known classes | Needs a labeled costume dataset (doesn't exist); weeks of work; still closed-set; still no language generation |

## Decision

**Option A**, with two mitigations that capture most of Option B's robustness:

1. **Offline fallback (03-F6):** on API failure the pipeline continues with
   `"mystery guest"` + a canned comment.
2. **Pretend mode (03-F7):** with no API key, a stub returns rotating canned results
   so dev/CI runs the full event flow at zero cost.

Model: `claude-haiku-4-5` — the latency/cost sweet spot; a config flag can raise it to
a bigger model for higher-quality comments.

## Consequences

- The Pi needs internet for full functionality; without it the show goes on, less wittily.
- Snapshot JPEGs transit to Anthropic over TLS (not used for training per API terms);
  they are never *persisted* off-device. Documented in the privacy contract (05-N1/N3).
- Costs scale with visitors, not uptime — idle watching is free.
