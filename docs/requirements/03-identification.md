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
| 03-F1 | Consume `GroupSpotted` events; send each person's cropped snapshot to the Claude Vision API. Snapshots are padded 25% around the person (hats, wings, props), at most 1024 px, and contrast/low-light corrected so night-time porch shots stay readable. |
| 03-F2 | One API call returns all three outputs — costume label, confidence (`high/medium/low`), and comment — via a structured (JSON) response. Two calls per visitor would double cost and latency. |
| 03-F3 | Recognize the "no costume" case: a person in regular clothes gets `costume: null` and a gentle generic greeting instead of a hallucinated costume. |
| 03-F4 | Comments must be family-friendly, ≤ 20 words (spoken aloud in a few seconds), and never mock the person — the prompt encodes these rules; they are also asserted in tests against the fallback generator. |
| 03-F5 | Publish `CostumeIdentified` on success. |
| 03-F6 | **Graceful degradation:** if the API is unreachable, times out (configurable, default 15 s), or returns malformed output after retries, fall back to `costume: "mystery guest"` with a canned comment — the pipeline (logging, speech) continues. Internet failure must never stop the porch show. |
| 03-F7 | Support a `pretend` mode (no API key configured) that returns rotating canned identifications, so developers and CI exercise the full event flow with zero cost/credentials. |
| 03-F8 | Retry transient API failures (429/5xx/network) with short backoff (0.5 s, then 1 s), max 2 retries — the visitor is standing at the door. |
| 03-F9 | **One call per group:** a `GroupSpotted` is identified with ONE request containing a photo per person (labeled "Person 1..N", ≤ 1024 px). The response holds a greeting for everyone (≤ 20 words) and, per person, a costume label, confidence and a shout-out (≤ 8 words). Each person still produces their own `CostumeIdentified`; the words to speak go out once as `GreetingReady`. |
| 03-F10 | **Specific identification:** the prompt asks for the most specific name the evidence supports ("Elsa from Frozen", not "princess"), to use masks, face paint, props, emblems and colors as clues, to name homemade costumes for what they're meant to be, and to give a best guess with `low` confidence rather than a vague label. `python -m costume_spotter.vision.try_photo` runs the same prompt on any photos. |
| 03-F11 | **Pets:** each photo is labeled with its visitor type ("Visitor 2 (dog):"). A pet in a costume is named the same specific way, including the animal ("Dog dressed as a hot dog"); a pet without one gets `costume: null` and a compliment about the pet itself. Pets are included in group greetings. |
| 03-F12 | **Clues before conclusions:** per visitor, Claude first lists the `clues` it can see (colors, mask, face paint, hat, wings, onesie, props, emblems), then names the costume from them. `costume: null` is only for everyday clothes with no costume element at all; any costume element means a costume must be named (low confidence if unsure). Clues are logged for tuning. (Field data: 41 of 50 sightings were "no costume", including ones whose own comment praised a "cozy monster blanket".) |
| 03-F13 | **Tonight's history:** each call lists the costumes already greeted this session (most recent 12; 20 kept in memory) and asks for a fresh joke when a costume repeats, so five vampires get five different greetings. The prompt also sets the scene explicitly: a porch on Halloween night. |

## Non-functional requirements

| ID | Requirement |
|----|-------------|
| 03-N1 | Median snapshot→comment latency < 4 s (visitor is still on the porch when the speaker reacts). The model (`claude-sonnet-5-5` by default; `claude-haiku-5-5` when speed matters most) balances this against identification accuracy. |
| 03-N2 | Cost per sighting ≈ $0.001–0.005 (one ~1000-token vision call on Haiku). A busy Halloween night (200 visitors) ≈ under a dollar. |
| 03-N3 | Snapshots are sent to the API over TLS and are not used for training (per Anthropic API terms); they are not persisted anywhere off-device by this component. |
| 03-N4 | The API key lives in an environment variable, never in code or logs. |

## Prompt contract (summary)

The system prompt instructs the model to return JSON:
`{"costume": string|null, "confidence": "high"|"medium"|"low", "comment": string}` and
encodes tone rules (03-F4). The full prompt lives beside the code in
[`edge/costume_spotter/vision/prompts.py`](../../edge/costume_spotter/vision/prompts.py)
so prompt changes are code-reviewed like any logic change.
