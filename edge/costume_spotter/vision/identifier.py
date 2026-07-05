"""The costume identifier subscriber: NewVisitorSpotted → Claude → CostumeIdentified.

Failure philosophy (03-F6): this component sits between an unreliable network and
a porch full of kids. Every path out of ``on_new_visitor`` publishes a
CostumeIdentified event — a perfect one from Claude, a canned one in pretend
mode, or the fallback identity when the API is down. Downstream components
(storage, speech, dashboard) never need to know which.
"""

import asyncio
import base64
import json
import logging
import re
import uuid
from itertools import cycle

from costume_spotter.events import CostumeIdentified, EventBus, NewVisitorSpotted, SystemStatus
from costume_spotter.events.events import BaseEvent
from costume_spotter.vision import prompts

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2  # 03-F8: transient failures get 2 retries with exponential backoff
_VALID_CONFIDENCE = {"high", "medium", "low"}


class CostumeIdentifier:
    """Identifies costumes via the Claude Vision API — or pretends to (03-F7)."""

    def __init__(self, bus: EventBus, *, api_key: str | None, model: str,
                 timeout_seconds: float, detector_name: str) -> None:
        self._bus = bus
        self._model = model
        self._timeout = timeout_seconds
        self._detector_name = detector_name
        self._pretend = cycle(prompts.PRETEND_IDENTITIES)

        if api_key:
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
        bus.subscribe(self.on_new_visitor, to=(NewVisitorSpotted,),
                      name="vision.identifier", queue_size=8)

    async def on_new_visitor(self, event: BaseEvent) -> None:
        assert isinstance(event, NewVisitorSpotted)
        if self._client is None:
            costume, confidence, comment, source = *next(self._pretend), "pretend"
        else:
            try:
                costume, confidence, comment = await self._identify_with_claude(event.snapshot_jpeg)
                source = "claude"
                self._bus.publish(SystemStatus(component="identifier", ok=True))
            except Exception as exc:
                # Whatever went wrong (network, 5xx after retries, bad JSON), the
                # pipeline continues with the fallback identity (03-F6).
                logger.warning("identification failed (%s); using fallback identity", exc)
                costume, confidence, comment = prompts.FALLBACK_IDENTITY
                source = "fallback"
                self._bus.publish(SystemStatus(component="identifier", ok=False, detail=str(exc)))

        self._bus.publish(CostumeIdentified(
            sighting_id=str(uuid.uuid4()),
            visitor_id=event.visitor_id,
            costume=costume,
            confidence=confidence,
            comment=comment,
            source=source,
            snapshot_jpeg=event.snapshot_jpeg,
            box=event.box,
            detector=self._detector_name,
        ))

    async def _identify_with_claude(self, snapshot_jpeg: bytes) -> tuple[str | None, str, str]:
        """One vision call returning (costume, confidence, comment) — 03-F2."""
        image_block = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.standard_b64encode(snapshot_jpeg).decode("ascii"),
            },
        }
        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            if attempt:
                await asyncio.sleep(2 ** attempt)  # 2s, 4s — visitor is still walking up
            try:
                response = await asyncio.wait_for(
                    self._client.messages.create(
                        model=self._model,
                        max_tokens=200,
                        system=prompts.SYSTEM_PROMPT,
                        messages=[{"role": "user",
                                   "content": [image_block,
                                               {"type": "text", "text": prompts.USER_PROMPT}]}],
                    ),
                    timeout=self._timeout,
                )
                return self._parse(response.content[0].text)
            except Exception as exc:  # noqa: BLE001 — every failure type retries the same way
                last_error = exc
                logger.info("claude attempt %d/%d failed: %s", attempt + 1, _MAX_RETRIES + 1, exc)
        raise last_error  # type: ignore[misc]  # loop ran at least once

    @staticmethod
    def _parse(text: str) -> tuple[str | None, str, str]:
        """Parse the model's JSON, tolerating stray prose around it.

        The prompt demands bare JSON, but LLM outputs deserve seatbelts: we grab
        the first {...} block and validate every field before trusting it.
        """
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"no JSON object in model output: {text[:120]!r}")
        data = json.loads(match.group(0))
        costume = data.get("costume")
        if costume is not None:
            costume = str(costume).strip()[:120] or None
        confidence = str(data.get("confidence", "")).lower()
        if confidence not in _VALID_CONFIDENCE:
            confidence = "low"
        comment = str(data.get("comment", "")).strip()
        if not comment:
            raise ValueError("model returned an empty comment")
        return costume, confidence, comment
