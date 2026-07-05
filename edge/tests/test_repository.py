"""SightingRepository against a real (temp-file) SQLite database.

No mocking here on purpose: the repository IS the SQLite adapter, so the thing
worth testing is actual SQL against an actual engine.
"""

from datetime import UTC, datetime, timedelta

import pytest

from costume_spotter.storage import SightingRepository


@pytest.fixture
def repo(tmp_path):
    return SightingRepository(tmp_path / "test.db")


def add_sighting(repo, sighting_id="s1", costume="witch", when=None):
    repo.add(
        sighting_id=sighting_id,
        spotted_at=(when or datetime.now(UTC)).replace(tzinfo=None),
        costume=costume,
        confidence="high",
        comment="nice hat",
        spoken=False,
        snapshot_file=f"{sighting_id}.jpg",
        detector="mock",
        box={"x": 1, "y": 2, "width": 3, "height": 4},
        source="pretend",
    )


def test_add_and_read_back(repo):
    add_sighting(repo)
    records = repo.recent()
    assert len(records) == 1
    assert records[0].costume == "witch"
    assert records[0].box == {"x": 1, "y": 2, "width": 3, "height": 4}


def test_recent_is_newest_first_and_paginated(repo):
    base = datetime.now(UTC)
    for i in range(5):
        add_sighting(repo, sighting_id=f"s{i}", when=base + timedelta(minutes=i))
    page = repo.recent(limit=2, offset=0)
    assert [r.id for r in page] == ["s4", "s3"]
    page2 = repo.recent(limit=2, offset=2)
    assert [r.id for r in page2] == ["s2", "s1"]


def test_mark_spoken(repo):
    add_sighting(repo)
    repo.mark_spoken("s1")
    assert repo.get("s1").spoken is True


def test_mark_spoken_on_missing_row_is_a_noop(repo):
    repo.mark_spoken("nope")  # must not raise — see logger.on_comment_spoken


def test_stats_aggregates(repo):
    for i in range(3):
        add_sighting(repo, sighting_id=f"w{i}", costume="witch")
    add_sighting(repo, sighting_id="r1", costume="robot")
    add_sighting(repo, sighting_id="n1", costume=None)  # no costume: excluded from top list

    stats = repo.stats()
    assert stats["total_sightings"] == 5
    assert stats["top_costumes"][0] == {"costume": "witch", "count": 3}
    assert {c["costume"] for c in stats["top_costumes"]} == {"witch", "robot"}


def test_prune_deletes_only_old_rows(repo):  # 05-F3
    old = datetime.now(UTC) - timedelta(days=10)
    add_sighting(repo, sighting_id="old", when=old)
    add_sighting(repo, sighting_id="new")
    removed = repo.prune_older_than(days=7)
    assert removed == 1
    assert [r.id for r in repo.recent()] == ["new"]
