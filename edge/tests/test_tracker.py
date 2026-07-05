"""VisitorTracker: the requirements in docs/requirements/02-tracking.md, as tests.

The tracker takes ``now`` as a parameter and does no I/O, so every scenario here
is a plain scripted sequence of frames — no sleeps, no cameras (02-N3).
"""

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


def test_consecutive_means_consecutive():  # 02-F3: hit, miss, hit, hit ≠ 3 consecutive
    tracker = make_tracker(min_hits=3)
    announced = []
    script = [[detection(100, 100)], [], [detection(100, 100)], [detection(100, 100)]]
    for i, dets in enumerate(script):
        announced += tracker.update(dets, F, now=i * 0.1)
    assert announced == []  # the miss reset the count; only 2 consecutive since


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
    # Crop = box + 15% padding on each side (imaging.crop_box), clipped to frame.
    assert snap_w >= 60 and snap_h >= 120


def test_memory_is_bounded_by_retirement():  # 02-N2
    tracker = make_tracker(min_hits=3)
    # 50 one-frame flickers at different spots and times: all must retire.
    for i in range(50):
        tracker.update([detection(10 + i * 4, 10)], F, now=float(i * 40))  # 40s apart
    assert len(tracker._visitors) <= 1  # noqa: SLF001 — asserting the bound is the test
