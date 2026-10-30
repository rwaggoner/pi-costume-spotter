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
import re
import uuid
from dataclasses import dataclass
from itertools import cycle

from costume_spotter.events import (
    CostumeIdentified,
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


@dataclass(frozen=True)
class PersonReading:
    costume: str | None  # None = regular clothes (03-F3)
    confidence: str
    shout_out: str
    clues: str = ""  # what Claude saw before deciding (03-F12) — logged, for tuning


@dataclass(frozen=True)
class GroupReading:
    greeting: str
    people: tuple[PersonReading, ...]  # one per visitor, in group order


class CostumeIdentifier:
    """Identifies costumes via the Claude Vision API — or pretends to (03-F7)."""

    def __init__(self, bus: EventBus, *, api_key: str | None, model: str,
                 timeout_seconds: float, detector_name: str,
                 shout_out_max_group: int = 3) -> None:
        self._bus = bus
        self._model = model
        self._timeout = timeout_seconds
        self._detector_name = detector_name
        # 04-F9: shout-outs are spoken for groups up to this size; bigger groups
        # get the greeting only, so the porch isn't talking for half a minute.
        self._shout_out_max_group = shout_out_max_group
        self._pretend = cycle(prompts.PRETEND_IDENTITIES)
        self._pretend_pets = cycle(prompts.PRETEND_PETS)
        self._pretend_group = cycle(prompts.PRETEND_GROUP_GREETINGS)

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

    async def on_group(self, event: BaseEvent) -> None:
        assert isinstance(event, GroupSpotted)
        count = len(event.visitors)
        if self._client is None:
            reading = self._pretend_reading([v.visitor_type for v in event.visitors])
            source = "pretend"
        else:
            try:
                reading = await self._identify_with_claude(
                    [(v.snapshot_jpeg, v.visitor_type) for v in event.visitors])
                source = "claude"
                self._bus.publish(SystemStatus(component="identifier", ok=True))
            except Exception as exc:
                # Whatever went wrong (network, 5xx after retries, bad JSON), the
                # pipeline continues with the fallback identity (03-F6).
                logger.warning("identification failed (%s); using fallback identity", exc)
                reading, source = self._fallback_reading(count), "fallback"
                self._bus.publish(SystemStatus(component="identifier", ok=False, detail=str(exc)))

        sighting_ids = []
        for visitor, person in zip(event.visitors, reading.people, strict=True):
            sighting_id = str(uuid.uuid4())
            sighting_ids.append(sighting_id)
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
        self._bus.publish(GreetingReady(group_id=event.group_id,
                                        text=self.spoken_text(reading),
                                        sighting_ids=tuple(sighting_ids)))

    def spoken_text(self, reading: GroupReading) -> str:
        """What the speaker says (04-F9): the greeting, then shout-outs for small groups."""
        count = len(reading.people)
        if count == 1 or count > self._shout_out_max_group:
            return reading.greeting
        shout_outs = [p.shout_out for p in reading.people if p.shout_out]
        return " ".join([reading.greeting, *shout_outs])

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

    async def _identify_with_claude(self, snapshots: list[tuple[bytes, str]]) -> GroupReading:
        """One vision call for the whole group — 03-F2/F9.

        ``snapshots`` is (JPEG, kind) per visitor; kind is the detector's
        person/dog/cat, or "" when unknown (try_photo).
        """
        content: list[dict] = []
        for index, (jpeg, kind) in enumerate(snapshots, start=1):
            content.append({"type": "text", "text": prompts.photo_label(index, kind)})
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(jpeg).decode("ascii"),
                },
            })
        content.append({"type": "text", "text": prompts.user_prompt(len(snapshots))})

        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            if attempt:
                await asyncio.sleep(_BACKOFF_SECONDS[attempt - 1])
            try:
                response = await asyncio.wait_for(
                    self._client.messages.create(
                        model=self._model,
                        # Greeting ~40 tokens, then ~70 per visitor (clues + costume
                        # + shout-out), with headroom.
                        max_tokens=150 + 110 * len(snapshots),
                        system=prompts.SYSTEM_PROMPT,
                        messages=[{"role": "user", "content": content}],
                    ),
                    timeout=self._timeout,
                )
                reading = self._parse(response.content[0].text, len(snapshots))
                for index, person in enumerate(reading.people, start=1):
                    logger.info("visitor %d: clues=%r -> costume=%r (%s)", index, person.clues,
                                person.costume, person.confidence)
                return reading
            except UnicodeEncodeError:
                # Encoding failures happen before any network I/O and can never
                # succeed on retry (defense in depth behind the __init__ key
                # check). Surface immediately → fallback identity (03-F6).
                raise
            except Exception as exc:  # noqa: BLE001 — every other failure retries the same way
                last_error = exc
                logger.info("claude attempt %d/%d failed: %s", attempt + 1, _MAX_RETRIES + 1, exc)
        raise last_error  # type: ignore[misc]  # loop ran at least once

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


def _person(raw: dict) -> PersonReading:
    costume = raw.get("costume")
    if costume is not None:
        costume = str(costume).strip()[:120] or None
    confidence = str(raw.get("confidence", "")).lower()
    if confidence not in _VALID_CONFIDENCE:
        confidence = "low"
    return PersonReading(costume, confidence, str(raw.get("shout_out") or "").strip(),
                         clues=str(raw.get("clues") or "").strip()[:300])
