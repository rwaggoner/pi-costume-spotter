"""SQLAlchemy table definitions — the schema documented in
docs/requirements/05-storage.md, as code.

Schema management is ``create_all()`` at startup rather than migrations: the edge
DB holds auto-pruned, disposable data, so "delete the file" is a valid migration
path (argued in ADR-004). The cloud tier's durable Postgres gets real Flyway
migrations — rigor proportional to durability.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SightingRow(Base):
    """One visitor sighting. Mirrors (a superset of) the cloud tier's table."""

    __tablename__ = "sightings"

    # UUID minted on the edge; the cloud tier reuses it as its primary key so
    # Pub/Sub redelivery can't create duplicates (07-F4).
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    spotted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # UTC
    costume: Mapped[str | None] = mapped_column(String(120))  # NULL = no costume (03-F3)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    spoken: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    snapshot_file: Mapped[str | None] = mapped_column(String(80))  # NULL in metadata-only mode
    detector: Mapped[str] = mapped_column(String(20), nullable=False)
    box_json: Mapped[str] = mapped_column(Text, nullable=False)  # for the dashboard overlay
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # claude|pretend|fallback

    __table_args__ = (Index("ix_sightings_spotted_at", "spotted_at"),)
