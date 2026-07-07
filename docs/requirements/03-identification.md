# 03 — Costume Identification & Commentary

## Purpose

Given a snapshot of a new visitor, decide **what costume they're wearing** and produce
**a short, family-friendly, witty comment** about it. This is the one component that
uses cloud AI: naming an arbitrary costume ("inflatable T-Rex", "Barbie", "sexy
Pikachu") is open-vocabulary vision + language, which no model that fits the edge
hardware can do well ([ADR-002](../decisions/002-claude-vision.md)).

## Functional requirements

| ID | Requirement |
|----|-------------|
| 03-F1 | Consume `NewVisitorSpotted` events; send the visitor's crop(s) to the Claude Vision API. When the tracker supplies more than one crop (02-F2), all are sent in a single call and the prompt notes they are the same visitor at different moments (issue #11), so one blurred frame can't sink the identification. |
| 03-F2 | One API call returns all three outputs — costume label, confidence (`high/medium/low`), and comment — via a structured (JSON) response, regardless of how many snapshots it carries. Two calls per visitor would double cost and latency. |
| 03-F3 | Recognize the "no costume" case: a person in regular clothes gets `costume: null` and a gentle generic greeting instead of a hallucinated costume. |
| 03-F4 | Comments must be family-friendly, ≤ 20 words (spoken aloud in a few seconds), and never mock the person — the prompt encodes these rules; they are also asserted in tests against the fallback generator. |
| 03-F5 | Publish `CostumeIdentified` on success. |
| 03-F6 | **Graceful degradation:** if the API is unreachable, times out (configurable, default 15 s), or returns malformed output after retries, fall back to `costume: "mystery guest"` with a canned comment — the pipeline (logging, speech) continues. Internet failure must never stop the porch show. |
| 03-F7 | Support a `pretend` mode (no API key configured) that returns rotating canned identifications, so developers and CI exercise the full event flow with zero cost/credentials. |
| 03-F8 | Retry transient API failures (429/5xx/network) with exponential backoff, max 2 retries. |

## Non-functional requirements

| ID | Requirement |
|----|-------------|
| 03-N1 | Median snapshot→comment latency < 4 s (visitor is still on the porch when the speaker reacts). Model choice `claude-haiku-4-5` is driven by this + cost. |
| 03-N2 | Cost per sighting ≈ $0.001–0.005 (one ~1000-token vision call on Haiku). A busy Halloween night (200 visitors) ≈ under a dollar. |
| 03-N3 | Snapshots are sent to the API over TLS and are not used for training (per Anthropic API terms); they are not persisted anywhere off-device by this component. |
| 03-N4 | The API key lives in an environment variable, never in code or logs. |

## Prompt contract (summary)

The system prompt instructs the model to return JSON:
`{"costume": string|null, "confidence": "high"|"medium"|"low", "comment": string}` and
encodes tone rules (03-F4). The full prompt lives beside the code in
[`edge/costume_spotter/vision/prompts.py`](../../edge/costume_spotter/vision/prompts.py)
so prompt changes are code-reviewed like any logic change.
