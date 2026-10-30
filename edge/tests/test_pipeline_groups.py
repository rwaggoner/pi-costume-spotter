"""Pipeline + tracker + grouping together (02-F7): friends who walk up a frame
apart become ONE GroupSpotted, and each still gets a NewVisitorSpotted."""

import asyncio

import numpy as np

from costume_spotter.camera.base import FrameSource
from costume_spotter.detection.base import Detector
from costume_spotter.events import EventBus, GroupSpotted, NewVisitorSpotted
from costume_spotter.pipeline import FramePipeline
from costume_spotter.tracking import GroupAssembler, VisitorTracker
from tests.conftest import detection, eventually


class Blank(FrameSource):
    def read(self):
        return np.zeros((480, 640, 3), np.uint8)


class Scripted(Detector):
    """Person A from frame 0; person B joins one frame later, then both stay."""

    name = "scripted"

    def __init__(self):
        self.frame = 0

    def detect(self, frame):
        self.frame += 1
        people = [detection(50, 50, 100, 200)]
        if self.frame >= 2:
            people.append(detection(400, 50, 100, 200))
        return people


async def test_friends_a_frame_apart_form_one_group():
    bus = EventBus()
    groups: list = []
    visitors: list = []

    async def on_group(e):
        groups.append(e)

    async def on_visitor(e):
        visitors.append(e)

    bus.subscribe(on_group, to=(GroupSpotted,), name="t.groups")
    bus.subscribe(on_visitor, to=(NewVisitorSpotted,), name="t.visitors")
    await bus.start()
    pipeline = FramePipeline(bus, Blank(), Scripted(), VisitorTracker(min_hits=3),
                             target_fps=100, confidence_threshold=0.5,
                             grouper=GroupAssembler(wait_seconds=5.0))
    task = asyncio.create_task(pipeline.run())
    await eventually(lambda: len(groups) == 1, timeout=5)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert [v.visitor_id for v in groups[0].visitors] == [1, 2]
    assert {v.group_id for v in visitors} == {groups[0].group_id}
    assert all(v.snapshot_jpeg[:2] == b"\xff\xd8" for v in groups[0].visitors)
    await bus.stop()


def test_far_away_visitors_are_not_identified():  # 01-F8
    from costume_spotter.events.events import BoundingBox, Detection

    pipeline = FramePipeline(EventBus(), Blank(), Scripted(), VisitorTracker(),
                             target_fps=10, confidence_threshold=0.5,
                             min_person_height=0.2, min_pet_height=0.1)
    tiny_person = Detection(box=BoundingBox(0, 0, 47, 40), confidence=0.9)
    near_person = Detection(box=BoundingBox(0, 0, 150, 300), confidence=0.9)
    small_dog = Detection(box=BoundingBox(0, 0, 90, 80), confidence=0.9, label="dog")
    kept = pipeline.close_enough([tiny_person, near_person, small_dog], frame_height=720)
    assert kept == [near_person, small_dog]  # 80 px dog >= 10% of 720; 40 px person < 20%
