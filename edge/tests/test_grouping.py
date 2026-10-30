"""Group assembly (02-F7): friends arriving together get one greeting, and a
lone visitor is never made to wait."""

import numpy as np

from costume_spotter.events.events import BoundingBox
from costume_spotter.tracking.grouping import GroupAssembler
from costume_spotter.tracking.tracker import NewVisitor


def visitor(vid: int) -> NewVisitor:
    return NewVisitor(vid, BoundingBox(0, 0, 10, 10), np.zeros((10, 10, 3), np.uint8))


def ids(groups):
    return [[v.visitor_id for v in g] for g in groups]


def test_lone_visitor_closes_immediately():
    g = GroupAssembler(wait_seconds=1.0)
    assert ids(g.update([visitor(1)], pending=0, now=0.0)) == [[1]]


def test_group_waits_for_people_about_to_be_announced():
    g = GroupAssembler(wait_seconds=1.0)
    assert g.update([visitor(1)], pending=1, now=0.0) == []    # a friend is right behind
    assert ids(g.update([visitor(2)], pending=0, now=0.2)) == [[1, 2]]  # friend arrives


def test_simultaneous_arrivals_form_one_group():
    g = GroupAssembler()
    assert ids(g.update([visitor(1), visitor(2), visitor(3)], pending=0, now=0.0)) == [[1, 2, 3]]


def test_group_never_waits_longer_than_the_limit():
    g = GroupAssembler(wait_seconds=1.0)
    assert g.update([visitor(1)], pending=1, now=0.0) == []
    assert g.update([], pending=1, now=0.5) == []            # straggler still dawdling
    assert ids(g.update([], pending=1, now=1.0)) == [[1]]   # deadline: greet who's here


def test_big_crowds_are_split():
    g = GroupAssembler(max_size=2)
    groups = g.update([visitor(i) for i in range(1, 6)], pending=0, now=0.0)
    assert ids(groups) == [[1, 2], [3, 4], [5]]


def test_nothing_open_nothing_emitted():
    g = GroupAssembler()
    assert g.update([], pending=3, now=0.0) == []
    assert not g.is_open
