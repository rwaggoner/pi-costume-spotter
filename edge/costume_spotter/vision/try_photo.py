"""Try costume identification on your own photos — no porch, camera or speaker needed.

    python -m costume_spotter.vision.try_photo witch.jpg robot.jpg
    python -m costume_spotter.vision.try_photo costume-test   (every photo in a folder)
    python -m costume_spotter.vision.try_photo --group kid1.jpg kid2.jpg kid3.jpg
    python -m costume_spotter.vision.try_photo --model claude-haiku-5-5 witch.jpg

Each photo is treated as ONE visitor, a person or a pet (crop it to them for
best results).
By default each photo gets its own Claude call; ``--group`` sends them together
the way the porch does when friends arrive at once. Photos get the same
preparation as live snapshots (resize, contrast and low-light correction), so
the results match what the porch would say.

Reads ANTHROPIC_API_KEY and CLAUDE_MODEL from edge/.env like the app; run it
from the edge folder. Useful for comparing models or prompt changes on a few
known costumes before Halloween night.
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from costume_spotter.config import Settings
from costume_spotter.events import EventBus
from costume_spotter.pipeline import _encode_snapshot
from costume_spotter.vision.identifier import CostumeIdentifier

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def expand(paths: list[Path]) -> list[Path]:
    """Folders become the photos inside them (sorted); files pass through."""
    out: list[Path] = []
    for path in paths:
        if path.is_dir():
            out += sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
        else:
            out.append(path)
    return out


def _load(path: Path) -> bytes:
    return _encode_snapshot(np.asarray(Image.open(path).convert("RGB")))


async def _run(paths: list[Path], group: bool, model: str, settings: Settings) -> None:
    identifier = CostumeIdentifier(EventBus(), api_key=settings.anthropic_api_key, model=model,
                                   timeout_seconds=max(settings.identify_timeout_seconds, 30),
                                   detector_name="try_photo",
                                   shout_out_max_group=settings.shout_out_max_group)
    batches = [paths] if group else [[p] for p in paths]
    for batch in batches:
        started = time.monotonic()
        # kind "" = let Claude decide person vs pet (the porch gets it from YOLO).
        reading = await identifier._identify_with_claude(  # noqa: SLF001
            [(_load(p), "") for p in batch])
        elapsed = time.monotonic() - started
        print(f"\n{model}  ({elapsed:.1f} s)")
        for path, person in zip(batch, reading.people, strict=True):
            costume = person.costume or "(no costume)"
            print(f"  {path.name}: {costume}  [{person.confidence}]"
                  + (f"  shout-out: {person.shout_out}" if len(batch) > 1 else ""))
        print(f"  would say: \"{identifier.spoken_text(reading)}\"")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m costume_spotter.vision.try_photo",
        description="Identify costumes in photos with the same prompt the porch uses.")
    parser.add_argument("photos", nargs="+", type=Path,
                        help="one photo per person, or a folder of them")
    parser.add_argument("--group", action="store_true",
                        help="send all photos as one group (one call, one greeting)")
    parser.add_argument("--model", help="override CLAUDE_MODEL from .env")
    args = parser.parse_args()

    settings = Settings()
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY isn't set: add it to edge/.env (and remove the leading #).",
              file=sys.stderr)
        return 2
    photos = expand(args.photos)
    missing = [p for p in photos if not p.is_file()]
    if missing:
        print(f"not found: {', '.join(map(str, missing))}", file=sys.stderr)
        return 2
    if not photos:
        print("no photos found (.jpg, .jpeg, .png, .webp, .bmp)", file=sys.stderr)
        return 2
    asyncio.run(_run(photos, args.group, args.model or settings.claude_model, settings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
