"""The costume identifier subscriber: GroupSpotted → Claude → CostumeIdentified + GreetingReady.

One Claude call per group of visitors who arrived together (03-F9): a lone
visitor is a group of one. The answer is split into one CostumeIdentified per
person (each logged as its own sighting) and one GreetingReady with the words
to speak (04-F9): the group greeting, plus short per-costume shout-outs when
the group is small enough for them to stay snappy.

Failure philosophy (03-F6): this component sits between an unreliable network and
a porch full of kids. Every path out of ``on_group`` publishes — perfect words
from Claude, canned ones in pretend mode, or the fallback identity when the API
is down. Downstream components (storage, speech, dashboard) never need to know which.
"""

import asyncio
import base64
import json
import logging
import random
import re
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from itertools import cycle

from costume_spotter.events import (
    CostumeIdentified,
    DataReset,
    EventBus,
    GreetingReady,
    GroupSpotted,
    SystemStatus,
)
from costume_spotter.events.events import BaseEvent
from costume_spotter.vision import prompts

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2  # 03-F8: transient failures get 2 retries...
_BACKOFF_SECONDS = (0.5, 1.0)  # ...quickly: the visitor is standing right there
_VALID_CONFIDENCE = {"high", "medium", "low"}
# The greeting is the first field of the JSON, so with a streamed reply it is
# complete long before the per-visitor clues and shout-outs are (03-F15).
_GREETING = re.compile(r'"greeting"\s*:\s*"((?:[^"\\]|\\.)*)"')


@dataclass(frozen=True)
class PersonReading:
    costume: str | None  # None = regular clothes (03-F3)
    confidence: str
    shout_out: str
    clues: str = ""  # what Claude saw before deciding (03-F12) — logged, for tuning
    age: str = ""  # little kid | big kid | teen or adult | pet (03-F14) — logged only


@dataclass(frozen=True)
class GroupReading:
    greeting: str
    people: tuple[PersonReading, ...]  # one per visitor, in group order


class CostumeIdentifier:
    """Identifies costumes via the Claude Vision API — or pretends to (03-F7)."""

    def __init__(self, bus: EventBus, *, api_key: str | None, model: str,
                 timeout_seconds: float, detector_name: str,
                 shout_out_max_group: int = 3, max_images_per_call: int = 8,
                 sarcasm_rate: float = 0.4, rng: random.Random | None = None) -> None:
        self._bus = bus
        self._model = model
        self._timeout = timeout_seconds
        self._detector_name = detector_name
        # 04-F9: shout-outs are spoken for groups up to this size; bigger groups
        # get the greeting only, so the porch isn't talking for half a minute.
        self._shout_out_max_group = shout_out_max_group
        # 02-F8: extra photos per visitor fill this budget after everyone's best
        # photo, so a big group can't balloon one request (latency, image tokens).
        self._max_images_per_call = max_images_per_call
        self._pretend = cycle(prompts.PRETEND_IDENTITIES)
        self._pretend_pets = cycle(prompts.PRETEND_PETS)
        self._pretend_group = cycle(prompts.PRETEND_GROUP_GREETINGS)
        # Tonight's greeted costumes, session-scoped, so repeat costumes get
        # varied jokes (03-F13). Bounded: old entries age out naturally.
        self._recent_costumes: deque[str] = deque(maxlen=20)
        # 03-F14: the share of calls where older visitors get dry sarcasm. Rolled
        # here, not left to the model, which can't do "sometimes" reliably.
        self._sarcasm_rate = min(max(sarcasm_rate, 0.0), 1.0)
        self._rng = rng or random.Random()

        if api_key:
            # Fail fast on an unusable key (same philosophy as 01-F6). Keys ride
            # in an ASCII-only HTTP header, so a non-ASCII key can never work —
            # and the classic way to get one is pasting a placeholder or the
            # console's truncated display ("sk-ant-…", with a real ellipsis).
            # Field-tested: this exact mistake cost two debugging sessions
            # because the old behavior was three doomed retries per visitor.
            if not api_key.isascii():
                bad = ", ".join(sorted({repr(c) for c in api_key if not c.isascii()}))
                raise ValueError(
                    f"ANTHROPIC_API_KEY contains non-ASCII characters ({bad}) — this is "
                    "usually a pasted placeholder or the console's truncated display "
                    "('sk-ant-…'). Real keys are ~100 ASCII characters, shown in full "
                    "only when created. Check edge/.env AND the shell environment "
                    "(`env | grep ANTHROPIC`) — exported variables override .env."
                )
            # Import here so the SDK is only a hard requirement when actually used.
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=api_key, max_retries=0)  # we do our own retries
            self.mode = "claude"
        else:
            self._client = None
            self.mode = "pretend"
            logger.warning("no ANTHROPIC_API_KEY — identifier running in pretend mode (03-F7)")

        # Small queue on purpose: if identification falls behind a crowd, greeting
        # the freshest arrivals beats working through people who already left.
        bus.subscribe(self.on_group, to=(GroupSpotted,), name="vision.identifier", queue_size=8)
        bus.subscribe(self.on_reset, to=(DataReset,), name="vision.identifier.reset")

    async def on_reset(self, event: BaseEvent) -> None:
        """A reset starts the night over: tonight's costume list goes too (03-F13)."""
        self._recent_costumes.clear()

    async def on_group(self, event: BaseEvent) -> None:
        assert isinstance(event, GroupSpotted)
        count = len(event.visitors)
        started = time.monotonic()
        # Minted up front so an early greeting (03-F15) can already name them.
        sighting_ids = tuple(str(uuid.uuid4()) for _ in event.visitors)
        greeted_early = False

        def speak_greeting_now(greeting: str) -> None:
            nonlocal greeted_early
            greeted_early = True
            logger.info("greeting ready %.1f s after the group was spotted",
                        time.monotonic() - started)
            self._bus.publish(GreetingReady(group_id=event.group_id, text=greeting,
                                            sighting_ids=sighting_ids))

        if self._client is None:
            reading = self._pretend_reading([v.visitor_type for v in event.visitors])
            source = "pretend"
        else:
            try:
                reading = await self._identify_with_claude(
                    [((v.snapshot_jpeg, *v.extra_jpegs), v.visitor_type)
                     for v in event.visitors], on_greeting=speak_greeting_now)
                source = "claude"
                self._recent_costumes.extend(p.costume for p in reading.people if p.costume)
                self._bus.publish(SystemStatus(component="identifier", ok=True))
            except Exception as exc:
                # Whatever went wrong (network, 5xx after retries, bad JSON), the
                # pipeline continues with the fallback identity (03-F6).
                logger.warning("identification failed (%s); using fallback identity", exc)
                reading, source = self._fallback_reading(count), "fallback"
                self._bus.publish(SystemStatus(component="identifier", ok=False, detail=str(exc)))
        logger.info("identified %d visitor(s) %.1f s after they were spotted", count,
                    time.monotonic() - started)

        for sighting_id, visitor, person in zip(sighting_ids, event.visitors, reading.people,
                                                strict=True):
            self._bus.publish(CostumeIdentified(
                sighting_id=sighting_id,
                visitor_id=visitor.visitor_id,
                costume=person.costume,
                confidence=person.confidence,
                # A lone visitor's words ARE the greeting; in a group, each
                # sighting keeps its own shout-out (falling back to the greeting).
                comment=(reading.greeting if count == 1
                         else person.shout_out or reading.greeting),
                source=source,
                snapshot_jpeg=visitor.snapshot_jpeg,
                box=visitor.box,
                detector=self._detector_name,
                group_id=event.group_id,
                group_size=count,
                visitor_type=visitor.visitor_type,
            ))
        if greeted_early:
            # The greeting is already being spoken: follow it with the shout-outs.
            rest = self.shout_outs_text(reading)
            if rest and source == "claude":
                self._bus.publish(GreetingReady(group_id=event.group_id, text=rest,
                                                sighting_ids=sighting_ids))
        else:
            self._bus.publish(GreetingReady(group_id=event.group_id,
                                            text=self.spoken_text(reading),
                                            sighting_ids=sighting_ids))

    def spoken_text(self, reading: GroupReading) -> str:
        """What the speaker says (04-F9): the greeting, then shout-outs for small groups."""
        return " ".join(part for part in (reading.greeting, self.shout_outs_text(reading))
                        if part)

    def shout_outs_text(self, reading: GroupReading) -> str:
        """The shout-outs spoken after the greeting: only for groups of 2 up to
        SHOUT_OUT_MAX_GROUP, so a big group isn't kept waiting (04-F9)."""
        count = len(reading.people)
        if count == 1 or count > self._shout_out_max_group:
            return ""
        return " ".join(p.shout_out for p in reading.people if p.shout_out)

    # -- the three sources of words ---------------------------------------------

    def _pretend_reading(self, kinds: list[str]) -> GroupReading:
        count = len(kinds)
        picks = [next(self._pretend) if kind == "person" else next(self._pretend_pets)
                 for kind in kinds]
        people = tuple(PersonReading(costume, confidence, shout_out)
                       for costume, confidence, _, shout_out in picks)
        greeting = picks[0][2] if count == 1 else next(self._pretend_group)
        return GroupReading(greeting, people)

    @staticmethod
    def _fallback_reading(count: int) -> GroupReading:
        costume, confidence = prompts.FALLBACK_COSTUME
        greeting = prompts.FALLBACK_GREETING if count == 1 else prompts.FALLBACK_GROUP_GREETING
        return GroupReading(greeting,
                            tuple(PersonReading(costume, confidence, "") for _ in range(count)))

    async def _identify_with_claude(
            self, snapshots: list[tuple[tuple[bytes, ...], str]],
            on_greeting: Callable[[str], None] | None = None) -> GroupReading:
        """One vision call for the whole group — 03-F2/F9.

        ``snapshots`` is (JPEGs, kind) per visitor: the best photo first, then
        other moments of the same visitor (02-F8); kind is the detector's
        person/dog/cat, or "" when unknown (try_photo).

        ``on_greeting`` (03-F15) is called with the greeting as soon as it has
        streamed in, before the rest of the reply. Once it has been called the
        call is never retried: the porch has already started talking.
        """
        allowed = allocate_images([len(jpegs) for jpegs, _ in snapshots],
                                  self._max_images_per_call)
        content: list[dict] = []
        for index, ((jpegs, kind), count) in enumerate(zip(snapshots, allowed, strict=True),
                                                       start=1):
            content.append({"type": "text", "text": prompts.photo_label(index, kind, count)})
            for jpeg in jpegs[:count]:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64.standard_b64encode(jpeg).decode("ascii"),
                    },
                })
        sarcastic = self._rng.random() < self._sarcasm_rate
        content.append({"type": "text", "text": prompts.user_prompt(
            len(snapshots), list(self._recent_costumes), sarcastic=sarcastic)})

        request = {
            "model": self._model,
            # Greeting ~40 tokens, then ~75 per visitor (clues + age + costume
            # + shout-out), with headroom.
            "max_tokens": 150 + 110 * len(snapshots),
            # Cached (03-F15): the system prompt is the same on every call, so
            # visitors within 5 minutes of each other skip re-reading it.
            "system": [{"type": "text", "text": prompts.SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": content}],
        }
        greeted = [False]

        def greeting_streamed(greeting: str) -> None:
            greeted[0] = True
            if on_greeting is not None:
                on_greeting(greeting)

        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            if attempt:
                await asyncio.sleep(_BACKOFF_SECONDS[attempt - 1])
            try:
                text = await asyncio.wait_for(self._complete(request, greeting_streamed),
                                              timeout=self._timeout)
                reading = self._parse(text, len(snapshots))
                for index, person in enumerate(reading.people, start=1):
                    logger.info("visitor %d (%s%s): clues=%r -> costume=%r (%s)", index,
                                person.age or "?", ", sarcastic" if sarcastic else "",
                                person.clues, person.costume, person.confidence)
                return reading
            except UnicodeEncodeError:
                # Encoding failures happen before any network I/O and can never
                # succeed on retry (defense in depth behind the __init__ key
                # check). Surface immediately → fallback identity (03-F6).
                raise
            except Exception as exc:  # noqa: BLE001 — every other failure retries the same way
                if greeted[0]:
                    raise  # already speaking: a retry would greet them twice
                last_error = exc
                logger.info("claude attempt %d/%d failed: %s", attempt + 1, _MAX_RETRIES + 1, exc)
        raise last_error  # type: ignore[misc]  # loop ran at least once

    async def _complete(self, request: dict, on_greeting: Callable[[str], None]) -> str:
        """The model's whole reply. Streamed when the client supports it, so
        ``on_greeting`` fires as soon as the greeting is complete (03-F15)."""
        messages = self._client.messages
        if not hasattr(messages, "stream"):  # test stubs, older SDKs
            response = await messages.create(**request)
            return response.content[0].text
        text, sent = "", False
        async with messages.stream(**request) as stream:
            async for chunk in stream.text_stream:
                text += chunk
                if not sent and (found := _GREETING.search(text)):
                    greeting = json.loads(f'"{found.group(1)}"').strip()
                    if greeting:
                        sent = True
                        on_greeting(greeting)
        return text

    @staticmethod
    def _parse(text: str, count: int = 1) -> GroupReading:
        """Parse the model's JSON, tolerating stray prose around it.

        The prompt demands bare JSON, but LLM outputs deserve seatbelts: we grab
        the first {...} block and validate every field before trusting it. A
        short or long ``people`` list is padded/trimmed to ``count`` so every
        visitor still gets a sighting. The pre-group shape
        ``{"costume", "confidence", "comment"}`` is accepted too.
        """
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"no JSON object in model output: {text[:120]!r}")
        data = json.loads(match.group(0))

        if "people" not in data and "comment" in data:  # single-visitor legacy shape
            data = {"greeting": data.get("comment"),
                    "people": [{"costume": data.get("costume"),
                                "confidence": data.get("confidence"), "shout_out": ""}]}

        raw_people = data.get("people")
        if not isinstance(raw_people, list):
            raw_people = []
        people = [_person(p) for p in raw_people[:count] if isinstance(p, dict)]
        costume, confidence = prompts.FALLBACK_COSTUME
        while len(people) < count:
            people.append(PersonReading(costume, confidence, ""))

        greeting = str(data.get("greeting") or "").strip()
        if not greeting and count == 1:
            greeting = people[0].shout_out
        if not greeting:
            raise ValueError("model returned an empty greeting")
        return GroupReading(greeting, tuple(people))


def allocate_images(available: list[int], budget: int) -> list[int]:
    """How many photos to send per visitor (02-F8).

    Everyone gets their best photo, even past the budget (identification needs
    at least one per visitor). Leftover budget goes to extra moments, one round
    at a time in visitor order, so a pair gets 3+3 but a group of six gets 1-2 each.
    """
    counts = [1 if n else 0 for n in available]
    left = budget - sum(counts)
    while left > 0:
        progressed = False
        for i, n in enumerate(available):
            if left > 0 and counts[i] < n:
                counts[i] += 1
                left -= 1
                progressed = True
        if not progressed:
            break
    return counts


def _person(raw: dict) -> PersonReading:
    costume = raw.get("costume")
    if costume is not None:
        costume = str(costume).strip()[:120] or None
    confidence = str(raw.get("confidence", "")).lower()
    if confidence not in _VALID_CONFIDENCE:
        confidence = "low"
    return PersonReading(costume, confidence, str(raw.get("shout_out") or "").strip(),
                         clues=str(raw.get("clues") or "").strip()[:300],
                         age=str(raw.get("age") or "").strip().lower()[:20])
