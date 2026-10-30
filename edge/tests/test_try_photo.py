"""The try-a-photo command: same snapshot prep and prompt path as the porch."""

import numpy as np
from PIL import Image

from costume_spotter.config import Settings
from costume_spotter.vision import try_photo
from costume_spotter.vision.identifier import CostumeIdentifier, GroupReading, PersonReading


def photo(tmp_path, name):
    path = tmp_path / name
    Image.fromarray(np.full((300, 150, 3), 90, np.uint8)).save(path)
    return path


async def test_group_mode_sends_every_photo_in_one_call(tmp_path, monkeypatch, capsys):
    calls = []

    async def fake_identify(self, snapshots):
        calls.append(snapshots)
        return GroupReading("Spooky squad!", tuple(
            PersonReading(c, "high", s) for c, s in [("Witch", "Nice hat!"), ("Robot", "Beep!")]))

    monkeypatch.setattr(CostumeIdentifier, "_identify_with_claude", fake_identify)
    settings = Settings(_env_file=None, anthropic_api_key="sk-test")
    await try_photo._run([photo(tmp_path, "a.jpg"), photo(tmp_path, "b.jpg")],
                         group=True, model="m", settings=settings)

    assert len(calls) == 1 and len(calls[0]) == 2
    assert all(jpeg[:2] == b"\xff\xd8" for jpeg in calls[0])  # prepared like live snapshots
    out = capsys.readouterr().out
    assert "a.jpg: Witch  [high]" in out and 'would say: "Spooky squad! Nice hat! Beep!"' in out


def test_without_an_api_key_it_says_how_to_fix_it(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["try_photo", str(photo(tmp_path, "a.jpg"))])
    assert try_photo.main() == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_a_folder_expands_to_the_photos_inside(tmp_path):
    folder = tmp_path / "set"
    folder.mkdir()
    for name in ["b.png", "a.jpg", "notes.txt"]:
        (folder / name).write_bytes(b"x")
    single = photo(tmp_path, "solo.jpg")
    assert [p.name for p in try_photo.expand([folder, single])] == ["a.jpg", "b.png", "solo.jpg"]
