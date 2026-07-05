"""Edge persistence: SQLite sighting rows + snapshot JPEGs, with retention pruning.

The privacy contract lives here: snapshots never leave this machine
(docs/requirements/05-storage.md).
"""

from costume_spotter.storage.repository import SightingRepository
from costume_spotter.storage.snapshots import SnapshotStore

__all__ = ["SightingRepository", "SnapshotStore"]
