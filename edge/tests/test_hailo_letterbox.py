"""Letterbox geometry for Hailo inference (issue #9).

Pure math, tested off-device — the same reason person_rows() is module-level.
Reference case throughout: 1280×720 frame into a 640×640 model input, which
gives scale 0.5, a 640×360 scaled image, and 140px gray bars top and bottom.
"""

from costume_spotter.detection.hailo import letterbox_params, map_normalized_box

FRAME_W, FRAME_H = 1280, 720
MODEL_W, MODEL_H = 640, 640


def params():
    return letterbox_params(FRAME_W, FRAME_H, MODEL_W, MODEL_H)


def test_params_for_16_9_into_square():
    p = params()
    assert p.scale == 0.5
    assert (p.scaled_w, p.scaled_h) == (640, 360)
    assert (p.pad_x, p.pad_y) == (0, 140)


def test_square_frame_needs_no_padding():
    p = letterbox_params(640, 640, MODEL_W, MODEL_H)
    assert (p.scale, p.pad_x, p.pad_y) == (1.0, 0, 0)


def test_centered_box_round_trips():
    # A person at frame pixels (400..500, 200..600) → normalized model coords
    # under scale 0.5 + 140px top pad → mapped back must land where it started.
    p = params()
    x0, x1 = (400 * 0.5) / MODEL_W, (500 * 0.5) / MODEL_W
    y0, y1 = (200 * 0.5 + 140) / MODEL_H, (600 * 0.5 + 140) / MODEL_H
    box = map_normalized_box(y0, x0, y1, x1, p, FRAME_W, FRAME_H, MODEL_W, MODEL_H)
    assert (box.x, box.y) == (400, 200)
    assert (box.width, box.height) == (100, 400)


def test_box_reaching_into_the_gray_bars_clamps_to_frame():
    # Model-space box spanning the full canvas height: its top/bottom lie in
    # the padding; mapped back it must clamp to the frame's real extent.
    p = params()
    box = map_normalized_box(0.0, 0.25, 1.0, 0.75, p, FRAME_W, FRAME_H, MODEL_W, MODEL_H)
    assert box.y == 0
    assert box.height == FRAME_H
    assert 0 <= box.x and box.x + box.width <= FRAME_W


def test_mapped_boxes_always_within_frame_bounds():
    p = params()
    for coords in [(-0.1, -0.1, 1.1, 1.1), (0.9, 0.9, 1.0, 1.0), (0.0, 0.0, 0.05, 0.05)]:
        y0, x0, y1, x1 = coords
        box = map_normalized_box(y0, x0, y1, x1, p, FRAME_W, FRAME_H, MODEL_W, MODEL_H)
        assert box.x >= 0 and box.y >= 0
        assert box.x + box.width <= FRAME_W
        assert box.y + box.height <= FRAME_H
