"""Repository over the sightings table: the only code that writes or reads SQL.

Synchronous SQLAlchemy on purpose: SQLite has no useful async driver story, write
volume is tiny, and callers run these methods via ``asyncio.to_thread`` so the
event loop never blocks (05-N4). Keeping the repository sync also makes tests
plain functions.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import sessionmaker

from costume_spotter.storage.models import Base, SightingRow


@dataclass(frozen=True)
class SightingRecord:
    """Read-model returned to the API layer — keeps ORM entities out of routes."""

    id: str
    spotted_at: datetime
    costume: str | None
    confidence: str
    comment: str
    spoken: bool
    snapshot_file: str | None
    detector: str
    box: dict
    source: str


class SightingRepository:
    """CRUD + the aggregate queries the dashboard needs (05-F4)."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{db_path}")
        # WAL: dashboard reads never block pipeline writes (ADR-004).
        with self._engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        Base.metadata.create_all(self._engine)  # 05-F5
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False)

    # -- writes ---------------------------------------------------------------

    def add(self, *, sighting_id: str, spotted_at: datetime, costume: str | None,
            confidence: str, comment: str, spoken: bool, snapshot_file: str | None,
            detector: str, box: dict, source: str) -> None:
        with self._session_factory() as session:
            session.add(SightingRow(
                id=sighting_id, spotted_at=spotted_at, costume=costume,
                confidence=confidence, comment=comment, spoken=spoken,
                snapshot_file=snapshot_file, detector=detector,
                box_json=json.dumps(box), source=source,
            ))
            session.commit()

    def mark_spoken(self, sighting_id: str) -> None:
        """Speech completes after the row exists, so 'spoken' is a follow-up update."""
        with self._session_factory() as session:
            row = session.get(SightingRow, sighting_id)
            if row is not None:
                row.spoken = True
                session.commit()

    def prune_older_than(self, days: int) -> int:
        """Delete rows past the retention window (05-F3); returns count for the log.

        Snapshot *files* are pruned by SnapshotStore; this handles the rows.
        """
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
        with self._session_factory() as session:
            result = session.execute(delete(SightingRow).where(SightingRow.spotted_at < cutoff))
            session.commit()
            return result.rowcount

    # -- reads ----------------------------------------------------------------

    def recent(self, limit: int = 50, offset: int = 0) -> list[SightingRecord]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(SightingRow).order_by(SightingRow.spotted_at.desc())
                .limit(limit).offset(offset)
            ).all()
            return [self._to_record(r) for r in rows]

    def get(self, sighting_id: str) -> SightingRecord | None:
        with self._session_factory() as session:
            row = session.get(SightingRow, sighting_id)
            return self._to_record(row) if row else None

    def stats(self) -> dict:
        """Aggregates for /api/stats: totals, today, top costumes, per-hour histogram."""
        with self._session_factory() as session:
            total = session.scalar(select(func.count()).select_from(SightingRow)) or 0
            midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            today = session.scalar(
                select(func.count()).select_from(SightingRow)
                .where(SightingRow.spotted_at >= midnight.replace(tzinfo=None))
            ) or 0
            by_costume = session.execute(
                select(SightingRow.costume, func.count().label("n"))
                .where(SightingRow.costume.is_not(None))
                .group_by(SightingRow.costume).order_by(func.count().desc()).limit(10)
            ).all()
            per_hour = session.execute(
                # SQLite-specific hour bucket; fine — this repository IS the SQLite adapter.
                select(func.strftime("%Y-%m-%dT%H:00", SightingRow.spotted_at).label("hour"),
                       func.count())
                .group_by("hour").order_by("hour").limit(48)
            ).all()
            return {
                "total_sightings": total,
                "sightings_today": today,
                "top_costumes": [{"costume": c, "count": n} for c, n in by_costume],
                "per_hour": [{"hour": h, "count": n} for h, n in per_hour],
            }

    @staticmethod
    def _to_record(row: SightingRow) -> SightingRecord:
        return SightingRecord(
            id=row.id, spotted_at=row.spotted_at, costume=row.costume,
            confidence=row.confidence, comment=row.comment, spoken=row.spoken,
            snapshot_file=row.snapshot_file, detector=row.detector,
            box=json.loads(row.box_json), source=row.source,
        )
