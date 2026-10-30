"""Snapshot helpers that decide what Claude gets to look at (03-F1)."""

import numpy as np

from costume_spotter import imaging
from costume_spotter.events.events import BoundingBox


def test_crop_leaves_room_for_hats_wings_and_props():
    frame = np.zeros((1000, 1000, 3), np.uint8)
    crop = imaging.crop_box(frame, BoundingBox(400, 400, 100, 200))
    assert crop.shape[:2] == (300, 150)  # 25% padding on every side


def test_sharpness_drops_when_an_image_is_blurred():
    rng = np.random.default_rng(1)
    detailed = rng.integers(0, 255, (200, 120, 3), dtype=np.uint8)
    flat = np.full_like(detailed, 128)
    assert imaging.sharpness(detailed) > 100 * (imaging.sharpness(flat) + 1)


def test_dark_snapshots_are_brightened_but_keep_their_colors():
    dark = np.zeros((100, 100, 3), np.uint8)
    dark[:, :50] = (40, 10, 10)   # dim red cape
    dark[:, 50:] = (10, 10, 40)   # dim blue suit
    out = imaging.enhance_for_identification(dark)
    assert out.mean() > dark.mean() * 2
    left, right = out[:, :50].reshape(-1, 3).mean(0), out[:, 50:].reshape(-1, 3).mean(0)
    assert left[0] > left[2] and right[2] > right[0]  # red stays red, blue stays blue


def test_well_lit_snapshots_are_barely_changed():
    rng = np.random.default_rng(2)
    lit = rng.integers(0, 256, (100, 100, 3), dtype=np.uint8)  # already full range
    out = imaging.enhance_for_identification(lit)
    assert abs(float(out.mean()) - float(lit.mean())) < 5


def test_shrink_caps_the_long_side_and_never_upscales():
    big = np.zeros((2000, 1000, 3), np.uint8)
    assert imaging.shrink(big, 1024).shape[:2] == (1024, 512)
    small = np.zeros((300, 200, 3), np.uint8)
    assert imaging.shrink(small, 1024).shape[:2] == (300, 200)
