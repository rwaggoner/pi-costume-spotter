"""SnapshotStore: the privacy-relevant file handling (docs/requirements/05-storage.md)."""

import os
import time

from costume_spotter.storage import SnapshotStore


def test_save_and_resolve(tmp_path):
    store = SnapshotStore(tmp_path / "snaps", retention_days=7)
    filename = store.save("abc-123", b"\xff\xd8jpegdata")
    assert filename == "abc-123.jpg"
    assert store.path_for(filename).read_bytes() == b"\xff\xd8jpegdata"


def test_metadata_only_mode_never_writes(tmp_path):  # 05-N3
    store = SnapshotStore(tmp_path / "snaps", retention_days=0)
    assert store.enabled is False
    assert store.save("abc-123", b"pixels") is None
    assert not (tmp_path / "snaps").exists()  # not even the directory


def test_path_traversal_is_refused(tmp_path):
    store = SnapshotStore(tmp_path / "snaps", retention_days=7)
    store.save("legit", b"x")
    for evil in ("../secrets.txt", "..\\secrets.txt", "a/../../b.jpg"):
        assert store.path_for(evil) is None


def test_prune_removes_only_expired_files(tmp_path):  # 05-F3
    store = SnapshotStore(tmp_path / "snaps", retention_days=7)
    store.save("old", b"x")
    store.save("new", b"y")
    # Backdate 'old' by 8 days via mtime — prune keys off file age, not DB rows.
    old_path = store.path_for("old.jpg")
    eight_days_ago = time.time() - 8 * 86_400
    os.utime(old_path, (eight_days_ago, eight_days_ago))

    assert store.prune() == 1
    assert store.path_for("old.jpg") is None
    assert store.path_for("new.jpg") is not None
