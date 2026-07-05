"""Costume identification: snapshot in, costume + witty comment out.

The one cloud-AI component (docs/decisions/002-claude-vision.md), with the
offline behavior required by 03-F6/F7: no key → pretend mode, API failure →
fallback identity. The show always goes on.
"""

from costume_spotter.vision.identifier import CostumeIdentifier

__all__ = ["CostumeIdentifier"]
