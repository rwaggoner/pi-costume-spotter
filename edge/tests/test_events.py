"""Event wire serialization — the WebSocket contract (06-F2).

The load-bearing rule: image bytes never ride the event socket (they'd bloat
every log message with base64). This holds for single ``bytes`` fields and for
the ``extra_jpegs`` tuple of bytes (issue #11).
"""

from costume_spotter.events.events import (
    BoundingBox,
    CostumeIdentified,
    NewVisitorSpotted,
)


def test_new_visitor_wire_dict_drops_all_image_bytes():
    event = NewVisitorSpotted(
        visitor_id=7,
        snapshot_jpeg=b"\xff\xd8primary",
        box=BoundingBox(1, 2, 3, 4),
        extra_jpegs=(b"\xff\xd8extra1", b"\xff\xd8extra2"),
    )
    wire = event.as_wire_dict()
    assert wire["kind"] == "NewVisitorSpotted"
    assert wire["visitor_id"] == 7
    assert wire["box"] == {"x": 1, "y": 2, "width": 3, "height": 4}
    # Neither the primary snapshot nor the extras appear on the wire.
    assert "snapshot_jpeg" not in wire
    assert "extra_jpegs" not in wire


def test_costume_identified_wire_dict_drops_snapshot_keeps_text():
    event = CostumeIdentified(
        sighting_id="s1", visitor_id=1, costume="witch", confidence="high",
        comment="Nice hat!", source="claude", snapshot_jpeg=b"\xff\xd8x",
        box=BoundingBox(0, 0, 5, 5), detector="hailo",
    )
    wire = event.as_wire_dict()
    assert wire["costume"] == "witch"
    assert wire["comment"] == "Nice hat!"
    assert "snapshot_jpeg" not in wire
