"""06-F11 stats page data, 06-F12 reset, and the schema back-fill for older DBs."""

import sqlite3
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from costume_spotter.api.app import create_app
from costume_spotter.config import Settings
from costume_spotter.events import DataReset, EventBus
from costume_spotter.storage import SightingRepository, SnapshotStore
from costume_spotter.storage.repository import bucket_minutes

NOW = datetime(2026, 10, 31, 23, 0, 0)  # naive UTC, like the rows


def add(repo, n, minutes_ago, costume, visitor_type="person", group="", size=1,
        source="claude", confidence="high"):
    repo.add(sighting_id=f"s{n}", spotted_at=NOW - timedelta(minutes=minutes_ago),
             costume=costume, confidence=confidence, comment="hi", spoken=True,
             snapshot_file=None, detector="mock", box={}, source=source,
             visitor_type=visitor_type, group_id=group, group_size=size)


@pytest.fixture
def repo(tmp_path):
    repo = SightingRepository(tmp_path / "t.db")
    add(repo, 1, 100, "Spider-Man", group="g1", size=3)
    add(repo, 2, 100, "spider-man ", group="g1", size=3)
    add(repo, 3, 100, None, group="g1", size=3)  # their big brother, no costume
    add(repo, 4, 50, "Witch", confidence="medium")
    add(repo, 5, 40, None, visitor_type="dog", group="g2", size=2)
    add(repo, 6, 40, "Pumpkin dog", visitor_type="dog", group="g2", size=2)
    add(repo, 7, 10, "mystery guest", source="fallback", confidence="unknown")
    add(repo, 8, 200, "Ghost")  # outside a 2-hour window
    return repo


def test_totals_split_costume_no_costume_pets_and_unidentified(repo):
    stats = repo.night_stats(hours=2, now=NOW)
    t = stats["totals"]
    assert (t["visitors"], t["people"]) == (7, 5)
    assert (t["costume"], t["no_costume"], t["pet"], t["unidentified"]) == (3, 1, 2, 1)
    assert (t["dogs"], t["cats"]) == (2, 0)
    assert (t["groups"], t["largest_group"], t["average_group"]) == (4, 3, 1.8)
    assert t["first_visit"] == "2026-10-31T21:20:00Z" and t["last_visit"] == "2026-10-31T22:50:00Z"


def test_costume_names_are_merged_and_ranked(repo):
    stats = repo.night_stats(hours=2, now=NOW)
    assert stats["costumes"][0] == {"costume": "Spider-Man", "count": 2}
    assert {c["costume"] for c in stats["costumes"]} == {"Spider-Man", "Witch", "Pumpkin dog"}
    assert stats["confidence"] == {"high": 2, "medium": 1, "low": 0}  # people only


def test_timeline_buckets_cover_the_window(repo):
    stats = repo.night_stats(hours=2, now=NOW)
    assert stats["window"]["bucket_minutes"] == 10
    timeline = stats["timeline"]
    assert timeline[0]["start"] == "2026-10-31T21:00:00Z"
    assert timeline[-1]["start"] == "2026-10-31T23:00:00Z"
    by_start = {b["start"]: b for b in timeline}
    assert by_start["2026-10-31T21:20:00Z"]["costume"] == 2
    assert by_start["2026-10-31T21:20:00Z"]["no_costume"] == 1
    assert by_start["2026-10-31T22:20:00Z"]["pet"] == 2
    assert stats["totals"]["busiest"] == {"start": "2026-10-31T21:20:00Z", "count": 3}


def test_all_time_window_starts_at_the_first_visit(repo):
    stats = repo.night_stats(hours=None, now=NOW)
    assert stats["totals"]["visitors"] == 8
    assert stats["window"]["hours"] is None


def test_group_sizes_histogram(repo):
    sizes = {g["size"]: g["count"] for g in repo.night_stats(hours=2, now=NOW)["group_sizes"]}
    assert sizes == {"1": 2, "2": 1, "3": 1, "4": 0, "5": 0, "6+": 0}


def test_empty_night(tmp_path):
    stats = SightingRepository(tmp_path / "e.db").night_stats(hours=2, now=NOW)
    assert stats["totals"]["visitors"] == 0 and stats["totals"]["busiest"] is None
    assert len(stats["timeline"]) == 13


def test_bucket_sizes_keep_the_line_readable():
    assert bucket_minutes(timedelta(hours=1)) == 5
    assert bucket_minutes(timedelta(hours=4)) == 15
    assert bucket_minutes(timedelta(hours=6)) == 30


def test_an_older_database_gets_the_new_columns_and_keeps_its_rows(tmp_path):
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:  # the table as the first release made it
        conn.execute("CREATE TABLE sightings (id VARCHAR(36) PRIMARY KEY, spotted_at DATETIME "
                     "NOT NULL, costume VARCHAR(120), confidence VARCHAR(10) NOT NULL, comment "
                     "TEXT NOT NULL, spoken BOOLEAN NOT NULL, snapshot_file VARCHAR(80), "
                     "detector VARCHAR(20) NOT NULL, box_json TEXT NOT NULL, source VARCHAR(20) "
                     "NOT NULL)")
        conn.execute("INSERT INTO sightings VALUES ('old', '2026-10-31 22:00:00', 'Ghost', "
                     "'high', 'Boo', 1, NULL, 'mock', '{}', 'claude')")
    repo = SightingRepository(db)
    assert repo.get("old").costume == "Ghost"
    stats = repo.night_stats(hours=None, now=NOW)
    assert stats["totals"]["costume"] == 1 and stats["totals"]["groups"] == 1


# -- reset (06-F12) ------------------------------------------------------------------

@pytest.fixture
def app_parts(tmp_path):
    settings = Settings(data_dir=tmp_path, _env_file=None)
    bus = EventBus()
    repository = SightingRepository(settings.db_path)
    snapshots = SnapshotStore(settings.snapshots_dir, retention_days=7)
    snapshots.save("s1", b"\xff\xd8")
    add(repository, 1, 5, "Witch")
    published = []
    bus.publish = published.append  # capture without running the bus
    return TestClient(create_app(settings, bus, repository, snapshots)), repository, published


def test_reset_deletes_everything_and_tells_the_dashboards(app_parts):
    client, repository, published = app_parts
    body = client.post("/api/reset", json={"confirm": "reset"}).json()
    assert body == {"sightings_removed": 1, "snapshots_removed": 1}
    assert repository.recent() == []
    assert isinstance(published[-1], DataReset)
    assert client.get("/api/stats/night?hours=0").json()["totals"]["visitors"] == 0


def test_reset_needs_the_confirmation_word(app_parts):
    client, repository, _ = app_parts
    assert client.post("/api/reset", json={"confirm": "yes"}).status_code == 400
    assert client.post("/api/reset", json={}).status_code == 422
    assert len(repository.recent()) == 1


def test_night_stats_endpoint(app_parts):
    client, _, _ = app_parts
    body = client.get("/api/stats/night?hours=2").json()
    assert body["totals"]["costume"] == 1 and body["window"]["hours"] == 2


async def test_identifier_forgets_tonights_costumes_on_reset():
    from costume_spotter.vision.identifier import CostumeIdentifier

    identifier = CostumeIdentifier(EventBus(), api_key=None, model="x", timeout_seconds=1,
                                   detector_name="mock")
    identifier._recent_costumes.extend(["Witch", "Ghost"])  # noqa: SLF001
    await identifier.on_reset(DataReset(sightings_removed=2, snapshots_removed=0))
    assert list(identifier._recent_costumes) == []  # noqa: SLF001
