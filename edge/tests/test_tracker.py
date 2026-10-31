"""VisitorTracker: the requirements in docs/requirements/02-tracking.md, as tests.

The tracker takes ``now`` as a parameter and does no I/O, so every scenario here
is a plain scripted sequence of frames — no sleeps, no cameras (02-N3).
"""

import numpy as np

from costume_spotter.tracking import VisitorTracker
from tests.conftest import detection, frame

F = frame()


def make_tracker(min_hits: int = 3) -> VisitorTracker:
    return VisitorTracker(iou_threshold=0.3, min_hits=min_hits, retire_seconds=30.0)


def test_stable_person_is_announced_exactly_once():  # 02-F2, 02-F3
    tracker = make_tracker(min_hits=3)
    announced = []
    for i in range(10):  # same spot for 10 frames
        announced += tracker.update([detection(100, 100)], F, now=i * 0.1)
    assert len(announced) == 1
    assert announced[0].visitor_id == 1


def test_single_frame_flicker_is_ignored():  # 02-F3: a shadow YOLO fires on once
    tracker = make_tracker(min_hits=3)
    announced = tracker.update([detection(100, 100)], F, now=0.0)
    announced += tracker.update([], F, now=0.1)  # gone next frame
    announced += tracker.update([], F, now=0.2)
    assert announced == []


def test_a_detector_blink_does_not_restart_the_count():  # 02-F3: tolerance
    """hit, miss, hit, hit: one blink (capes and masks make YOLO blink) is
    tolerated, so the person is announced on their 3rd hit, not delayed."""
    tracker = make_tracker(min_hits=3)
    announced = []
    script = [[detection(100, 100)], [], [detection(100, 100)], [detection(100, 100)]]
    for i, dets in enumerate(script):
        announced += tracker.update(dets, F, now=i * 0.1)
    assert len(announced) == 1


def test_too_many_misses_restart_the_count():  # 02-F3: hit, 3 misses, hit, hit
    tracker = VisitorTracker(iou_threshold=0.3, min_hits=3, max_misses=2, retire_seconds=30.0)
    announced = []
    script = [[detection(100, 100)], [], [], [], [detection(100, 100)], [detection(100, 100)]]
    for i, dets in enumerate(script):
        announced += tracker.update(dets, F, now=i * 0.1)
    assert announced == []  # 3 misses > max_misses: only 2 hits since the restart


def test_pending_count_sees_people_about_to_be_announced():  # feeds grouping (02-F7)
    tracker = make_tracker(min_hits=3)
    tracker.update([detection(100, 100)], F, now=0.0)
    assert tracker.pending_count() == 0  # one sighting could be a shadow
    tracker.update([detection(100, 100)], F, now=0.1)
    assert tracker.pending_count() == 1
    tracker.update([detection(100, 100)], F, now=0.2)  # announced now
    assert tracker.pending_count() == 0


def test_moving_person_keeps_their_identity():  # 02-F1: IoU matching across drift
    tracker = make_tracker(min_hits=3)
    announced = []
    for i in range(8):  # walks right ~5px/frame — boxes overlap heavily frame-to-frame
        announced += tracker.update([detection(100 + i * 5, 100)], F, now=i * 0.1)
    assert len(announced) == 1


def test_returning_visitor_is_greeted_again():  # 02-F4: retire, then re-announce
    tracker = make_tracker(min_hits=2)
    announced = []
    for i in range(4):
        announced += tracker.update([detection(100, 100)], F, now=i * 0.1)
    assert len(announced) == 1
    # Gone for 60s (> retire_seconds=30), then back at the same spot.
    announced += tracker.update([], F, now=61.0)
    for i in range(4):
        announced += tracker.update([detection(100, 100)], F, now=62.0 + i * 0.1)
    assert len(announced) == 2
    assert announced[1].visitor_id != announced[0].visitor_id  # no identity across visits (05-N2)


def test_two_simultaneous_visitors():  # 02-F6
    tracker = make_tracker(min_hits=3)
    announced = []
    for i in range(5):  # two people far apart — zero IoU between them
        announced += tracker.update(
            [detection(50, 100), detection(220, 100)], F, now=i * 0.1
        )
    assert len(announced) == 2
    assert {a.visitor_id for a in announced} == {1, 2}


def test_snapshot_is_from_the_largest_appearance():  # 02-F5: closest ≈ biggest box
    tracker = make_tracker(min_hits=4)
    announced = []
    # Person approaches: box grows each frame. min_hits=4 fires on frame 4,
    # by which point the largest box seen is the 60x120 one from frame 4 itself.
    sizes = [(30, 60), (40, 80), (50, 100), (60, 120)]
    for i, (w, h) in enumerate(sizes):
        announced += tracker.update([detection(100, 100, w, h)], F, now=i * 0.1)
    assert len(announced) == 1
    snap_h, snap_w = announced[0].snapshot.shape[:2]
    # Crop = box + 25% padding on each side (imaging.crop_box), clipped to frame.
    assert snap_w >= 60 and snap_h >= 120


def test_memory_is_bounded_by_retirement():  # 02-N2
    tracker = make_tracker(min_hits=3)
    # 50 one-frame flickers at different spots and times: all must retire.
    for i in range(50):
        tracker.update([detection(10 + i * 4, 10)], F, now=float(i * 40))  # 40s apart
    assert len(tracker._visitors) <= 1  # noqa: SLF001 — asserting the bound is the test


def test_snapshot_prefers_a_sharp_frame_over_a_slightly_bigger_blurry_one():  # 02-F5
    """Same person, two frames: a crisp one, then a slightly closer but blurred
    (mid-stride) one. The crisp frame is the better photo to identify from."""
    rng = np.random.default_rng(0)
    crisp = np.zeros((480, 640, 3), np.uint8)
    crisp[100:300, 100:200] = rng.integers(0, 255, (200, 100, 3), dtype=np.uint8)  # detailed
    blurry = np.zeros((480, 640, 3), np.uint8)
    blurry[100:310, 100:205] = 128  # bigger, but no detail at all
    tracker = make_tracker(min_hits=2)
    tracker.update([detection(100, 100, 100, 200)], crisp, now=0.0)
    [visitor] = tracker.update([detection(100, 100, 105, 210)], blurry, now=0.1)
    assert visitor.snapshot.std() > 30  # the detailed crop, not the flat grey one


def test_a_dog_beside_a_kid_is_its_own_visitor():  # 01-F7
    from costume_spotter.events.events import BoundingBox, Detection

    tracker = make_tracker(min_hits=2)
    kid = Detection(box=BoundingBox(100, 100, 80, 200), confidence=0.9)
    dog = Detection(box=BoundingBox(110, 200, 70, 100), confidence=0.9, label="dog")  # overlaps
    announced = tracker.update([kid, dog], F, now=0.0)
    announced += tracker.update([kid, dog], F, now=0.1)
    assert sorted(v.visitor_type for v in announced) == ["dog", "person"]


def _frame_with(value: int):
    f = np.zeros((480, 640, 3), np.uint8)
    f[:] = value
    return f


def test_announcement_carries_extra_moments_best_first():  # 02-F8
    tracker = make_tracker(min_hits=3)
    frames = [_frame_with(v) for v in (10, 20, 30)]
    sizes = [(40, 80), (60, 120), (50, 100)]  # best (largest) is the 2nd sighting
    announced = []
    for i, ((w, h), f) in enumerate(zip(sizes, frames, strict=True)):
        announced += tracker.update([detection(100, 100, w, h)], f, now=i * 0.1)
    [v] = announced
    assert v.snapshot.mean() == 20  # primary = best (2nd) moment
    assert [int(s.mean()) for s in v.extra_snapshots] == [30, 10]  # announce frame, first


def test_extras_are_never_duplicates_of_the_primary():  # 02-F8
    tracker = make_tracker(min_hits=2)
    announced = tracker.update([detection(100, 100, 40, 80)], _frame_with(10), now=0.0)
    announced += tracker.update([detection(100, 100, 60, 120)], _frame_with(20), now=0.1)
    [v] = announced  # best IS the announce frame: one extra (the first sighting)
    assert v.snapshot.mean() == 20 and [int(s.mean()) for s in v.extra_snapshots] == [10]


def test_snapshots_per_visitor_one_means_best_only():
    tracker = VisitorTracker(min_hits=3, max_snapshots=1)
    announced = []
    for i in range(3):
        announced += tracker.update([detection(100, 100, 40 + i, 80)], _frame_with(i), now=i)
    assert announced[0].extra_snapshots == ()
