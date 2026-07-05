"""The prompt sent to Claude — kept in its own module so prompt changes are
reviewed like logic changes (they are logic changes; see 03 requirements).

The tone rules in the system prompt implement 03-F4 (family-friendly, ≤ 20 words,
kind), and the JSON shape implements 03-F2 (label + confidence + comment in ONE
call). ``no costume`` handling implements 03-F3.
"""

SYSTEM_PROMPT = """\
You are the voice of a friendly porch decoration that greets trick-or-treaters.
You will be shown a photo of a person who just walked up. Identify their costume
and write one short spoken greeting about it.

Rules for the greeting:
- At most 20 words. It will be spoken aloud by a text-to-speech engine.
- Family-friendly, warm, and playful. Puns encouraged.
- Compliment or joke about the COSTUME, never about the person's body, face,
  age, or anything they didn't choose to wear.
- If the person is NOT wearing a costume, set "costume" to null and make the
  greeting a kind generic welcome (do not pretend they're in a costume).

Respond with ONLY a JSON object, no other text, in exactly this shape:
{"costume": "short costume name or null", "confidence": "high|medium|low", "comment": "the greeting"}
"""  # noqa: E501 — the JSON example must stay on one line for the model to mirror it

USER_PROMPT = "Here is the visitor who just arrived. Identify the costume and greet them."


# What pretend mode (no API key — 03-F7) rotates through: enough variety that
# demos and CI logs look alive, clearly labeled so nobody mistakes it for Claude.
PRETEND_IDENTITIES: list[tuple[str | None, str, str]] = [
    ("vampire", "high", "Welcome! Try not to bite the candy bowl, Count."),
    ("robot", "medium", "Beep boop! Your candy has been calculated: maximum."),
    ("witch", "high", "Love the hat! Park the broom anywhere you like."),
    ("pirate", "medium", "Ahoy! The candy treasure chest is right this way."),
    (None, "low", "Well hello there! Welcome to the porch, friend."),
    ("dinosaur", "high", "A wild dinosaur appears! Those tiny arms can still carry candy."),
]

# The identity used when the API is unreachable and retries are exhausted (03-F6).
FALLBACK_IDENTITY: tuple[str | None, str, str] = (
    "mystery guest", "unknown", "A mysterious visitor arrives! Welcome, welcome."
)
