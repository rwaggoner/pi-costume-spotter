"""API endpoints against a real app with real (temp) storage — only hardware is absent."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from costume_spotter.api.app import create_app
from costume_spotter.config import Settings
from costume_spotter.events import EventBus
from costume_spotter.storage import SightingRepository, SnapshotStore


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=tmp_path, _env_file=None)
    bus = EventBus()
    repository = SightingRepository(settings.db_path)
    snapshots = SnapshotStore(settings.snapshots_dir, retention_days=7)

    # Seed one sighting the way the logger would.
    snapshot_file = snapshots.save("s1", b"\xff\xd8fakejpeg")
    repository.add(
        sighting_id="s1", spotted_at=datetime.now(UTC).replace(tzinfo=None),
        costume="dinosaur", confidence="high", comment="Rawr means welcome!",
        spoken=True, snapshot_file=snapshot_file, detector="mock",
        box={"x": 1, "y": 2, "width": 3, "height": 4}, source="pretend",
    )

    app = create_app(settings, bus, repository, snapshots)
    return TestClient(app)


def test_list_sightings(client):
    body = client.get("/api/sightings").json()
    assert body["sightings"][0]["costume"] == "dinosaur"
    assert body["sightings"][0]["has_snapshot"] is True


def test_snapshot_is_served(client):
    response = client.get("/api/sightings/s1/snapshot")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == b"\xff\xd8fakejpeg"


def test_snapshot_404_for_unknown_sighting(client):
    assert client.get("/api/sightings/nope/snapshot").status_code == 404


def test_stats(client):
    body = client.get("/api/stats").json()
    assert body["total_sightings"] == 1
    assert body["top_costumes"] == [{"costume": "dinosaur", "count": 1}]


def test_health_reports_bus_subscribers(client):
    body = client.get("/api/health").json()
    names = {s["subscriber"] for s in body["bus"]}
    # The app wired its own read-side subscribers at construction.
    assert "api.latest_frame" in names
    assert "api.ws_broadcaster" in names
