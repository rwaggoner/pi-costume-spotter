"""Repository over the sightings table: the only code that writes or reads SQL.

Synchronous SQLAlchemy on purpose: SQLite has no useful async driver story, write
volume is tiny, and callers run these methods via ``asyncio.to_thread`` so the
event loop never blocks (05-N4). Keeping the repository sync also makes tests
plain functions.
"""

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, delete, func, inspect, select
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
        self._add_missing_columns()
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False)

    # Columns added after the first release: (name, SQLite definition).
    _LATER_COLUMNS = (
        ("visitor_type", "VARCHAR(10) NOT NULL DEFAULT 'person'"),
        ("group_id", "VARCHAR(32) NOT NULL DEFAULT ''"),
        ("group_size", "INTEGER NOT NULL DEFAULT 1"),
    )

    def _add_missing_columns(self) -> None:
        """create_all() never alters an existing table: add newer columns to a
        database made by an older version, keeping its sightings."""
        existing = {c["name"] for c in inspect(self._engine).get_columns("sightings")}
        with self._engine.begin() as conn:
            for name, definition in self._LATER_COLUMNS:
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE sightings ADD COLUMN {name} {definition}")

    # -- writes ---------------------------------------------------------------

    def add(self, *, sighting_id: str, spotted_at: datetime, costume: str | None,
            confidence: str, comment: str, spoken: bool, snapshot_file: str | None,
            detector: str, box: dict, source: str, visitor_type: str = "person",
            group_id: str = "", group_size: int = 1) -> None:
        with self._session_factory() as session:
            session.add(SightingRow(
                id=sighting_id, spotted_at=spotted_at, costume=costume,
                confidence=confidence, comment=comment, spoken=spoken,
                snapshot_file=snapshot_file, detector=detector,
                box_json=json.dumps(box), source=source, visitor_type=visitor_type,
                group_id=group_id, group_size=group_size,
            ))
            session.commit()

    def reset(self) -> int:
        """Delete every sighting (06-F12, the dashboard's reset button)."""
        with self._session_factory() as session:
            result = session.execute(delete(SightingRow))
            session.commit()
            return result.rowcount

    def mark_spoken(self, sighting_id: str) -> bool:
        """'spoken' is a follow-up update; False when the row doesn't exist (yet)."""
        with self._session_factory() as session:
            row = session.get(SightingRow, sighting_id)
            if row is None:
                return False
            row.spoken = True
            session.commit()
            return True

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

    def night_stats(self, hours: float | None = 2.0, now: datetime | None = None) -> dict:
        """Everything the stats page draws (06-F11), for the last ``hours``
        (None = every sighting kept). Times are naive UTC in, ISO "Z" out.

        Computed in Python: a Halloween night is hundreds of rows, not millions,
        and the categories (costume / no costume / pet / unidentified) and the
        costume-name merging are clearer here than in SQL.
        """
        now = now or datetime.now(UTC).replace(tzinfo=None)
        since = now - timedelta(hours=hours) if hours else None
        with self._session_factory() as session:
            query = select(SightingRow.spotted_at, SightingRow.costume, SightingRow.visitor_type,
                           SightingRow.group_id, SightingRow.group_size, SightingRow.source,
                           SightingRow.confidence).order_by(SightingRow.spotted_at)
            if since is not None:
                query = query.where(SightingRow.spotted_at >= since)
            rows = session.execute(query).all()
        return summarize_night(rows, since=since, now=now)

    @staticmethod
    def _to_record(row: SightingRow) -> SightingRecord:
        return SightingRecord(
            id=row.id, spotted_at=row.spotted_at, costume=row.costume,
            confidence=row.confidence, comment=row.comment, spoken=row.spoken,
            snapshot_file=row.snapshot_file, detector=row.detector,
            box=json.loads(row.box_json), source=row.source,
        )


# -- stats page (06-F11) -------------------------------------------------------------

CATEGORIES = ("costume", "no_costume", "pet", "unidentified")
_BUCKET_MINUTES = (5, 10, 15, 30, 60, 120, 240)
_TOP_COSTUMES = 15


def category(costume: str | None, visitor_type: str, source: str) -> str:
    if visitor_type in ("dog", "cat"):
        return "pet"
    if source == "fallback":
        return "unidentified"  # the AI was unreachable: we don't know
    return "no_costume" if costume is None else "costume"


def bucket_minutes(span: timedelta) -> int:
    """Bucket size giving about 8-16 points: smooth enough to read a trend in
    a few dozen visitors."""
    minutes = span.total_seconds() / 60
    for size in _BUCKET_MINUTES:
        if minutes / size <= 16:
            return size
    return _BUCKET_MINUTES[-1]


def _floor(moment: datetime, minutes: int) -> datetime:
    day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = int((moment - day).total_seconds() // 60)
    return day + timedelta(minutes=elapsed - elapsed % minutes)


def _iso(moment: datetime | None) -> str | None:
    return None if moment is None else moment.replace(microsecond=0).isoformat() + "Z"


def summarize_night(rows, *, since: datetime | None, now: datetime) -> dict:
    """The stats page's numbers from (spotted_at, costume, visitor_type,
    group_id, group_size, source, confidence) rows, oldest first."""
    start = since or (rows[0][0] if rows else now - timedelta(hours=2))
    size = bucket_minutes(now - start)
    step = timedelta(minutes=size)
    first_bucket = _floor(start, size)
    timeline = []
    moment = first_bucket
    while moment <= now:
        timeline.append({"start": moment, **{c: 0 for c in CATEGORIES}})
        moment += step

    totals = Counter()
    costumes: Counter = Counter()
    spellings: dict[str, Counter] = {}
    confidence: Counter = Counter()
    groups: dict[str, int] = {}
    pets = Counter()
    for index, (spotted_at, costume, visitor_type, group_id, group_size, source,
                level) in enumerate(rows):
        kind = category(costume, visitor_type, source)
        totals[kind] += 1
        slot = int((spotted_at - first_bucket) / step)
        if 0 <= slot < len(timeline):
            timeline[slot][kind] += 1
        # Older rows have no group: each is its own group of one.
        groups[group_id or f"row-{index}"] = max(group_size or 1, 1)
        if kind == "pet":
            pets[visitor_type] += 1
        if costume and kind in ("costume", "pet"):
            key = " ".join(costume.lower().split())
            costumes[key] += 1
            spellings.setdefault(key, Counter())[costume.strip()] += 1
            if kind == "costume":
                confidence[level] += 1

    top = costumes.most_common(_TOP_COSTUMES)
    named = [{"costume": spellings[key].most_common(1)[0][0], "count": n} for key, n in top]
    other = sum(costumes.values()) - sum(n for _, n in top)
    sizes = Counter(min(n, 6) for n in groups.values())
    busiest = max(timeline, key=lambda b: sum(b[c] for c in CATEGORIES), default=None)
    busiest_count = sum(busiest[c] for c in CATEGORIES) if busiest else 0
    people = totals["costume"] + totals["no_costume"] + totals["unidentified"]
    return {
        "window": {"start": _iso(start), "end": _iso(now), "bucket_minutes": size,
                   "hours": None if since is None else round((now - since).total_seconds()
                                                             / 3600, 2)},
        "totals": {
            "visitors": len(rows), "people": people, **{c: totals[c] for c in CATEGORIES},
            "dogs": pets["dog"], "cats": pets["cat"],
            "groups": len(groups),
            "average_group": round(len(rows) / len(groups), 1) if groups else 0,
            "largest_group": max(groups.values(), default=0),
            "unique_costumes": len(costumes),
            "first_visit": _iso(rows[0][0]) if rows else None,
            "last_visit": _iso(rows[-1][0]) if rows else None,
            "busiest": ({"start": _iso(busiest["start"]), "count": busiest_count}
                        if busiest_count else None),
        },
        "timeline": [{**b, "start": _iso(b["start"])} for b in timeline],
        "costumes": named,
        "other_costumes": other,
        "group_sizes": [{"size": "6+" if n == 6 else str(n), "count": sizes[n]}
                        for n in range(1, 7)],
        "confidence": {level: confidence[level] for level in ("high", "medium", "low")},
    }
