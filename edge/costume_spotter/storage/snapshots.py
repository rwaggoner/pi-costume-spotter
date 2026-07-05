"""Snapshot files: save, serve, prune.

The privacy-relevant half of storage (05-N1..N3): JPEGs live in one directory on
the device, named by sighting UUID, deleted after the retention window, and this
module is the only code that writes them. Retention 0 = never write at all.
"""

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_SECONDS_PER_DAY = 86_400


class SnapshotStore:
    """Filesystem home for sighting snapshots."""

    def __init__(self, directory: Path, retention_days: int) -> None:
        self._dir = directory
        self.retention_days = retention_days
        if self.enabled:
            self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        """False = metadata-only mode (05-N3): no pixels are ever persisted."""
        return self.retention_days > 0

    def save(self, sighting_id: str, jpeg: bytes) -> str | None:
        """Write the snapshot; returns the filename recorded on the sighting row."""
        if not self.enabled:
            return None
        filename = f"{sighting_id}.jpg"
        (self._dir / filename).write_bytes(jpeg)
        return filename

    def path_for(self, filename: str) -> Path | None:
        """Resolve a stored filename for serving — refusing path traversal."""
        if not self.enabled or "/" in filename or "\\" in filename or ".." in filename:
            return None
        path = self._dir / filename
        return path if path.is_file() else None

    def prune(self) -> int:
        """Delete snapshots older than the retention window (05-F3).

        Uses file mtime rather than parsing DB rows: files and rows are pruned
        independently with the same window, so neither can strand the other.
        """
        if not self.enabled:
            return 0
        cutoff = time.time() - self.retention_days * _SECONDS_PER_DAY
        removed = 0
        for f in self._dir.glob("*.jpg"):
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                removed += 1
        if removed:
            logger.info("pruned %d snapshots older than %d days", removed, self.retention_days)
        return removed
