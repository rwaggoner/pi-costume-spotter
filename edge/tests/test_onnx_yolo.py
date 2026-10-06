"""ONNX YOLOv8 decode logic (ADR-010), tested without a model file.

Builds raw outputs in YOLOv8's (1, 84, N) layout by hand, so the letterbox
un-mapping, thresholding and NMS are verified on any machine (CI included).
"""

import numpy as np

from costume_spotter.detection.onnx_yolo import decode, letterbox, nms


def raw_output(*boxes, classes: int = 80) -> np.ndarray:
    """Each box: (cx, cy, w, h, person_score[, other_class, other_score])."""
    out = np.zeros((1, 4 + classes, len(boxes)), dtype=np.float32)
    for i, (cx, cy, w, h, score, *other) in enumerate(boxes):
        out[0, :4, i] = (cx, cy, w, h)
        out[0, 4, i] = score
        if other:
            out[0, 4 + other[0], i] = other[1]
    return out


def test_letterbox_keeps_aspect_and_centres_the_frame():
    frame = np.zeros((360, 640, 3), dtype=np.uint8)  # 16:9
    tensor, scale, left, top = letterbox(frame, 640)
    assert tensor.shape == (1, 3, 640, 640) and tensor.dtype == np.float32
    assert scale == 1.0 and left == 0 and top == 140  # (640 - 360) / 2 of grey on each side
    assert np.isclose(tensor[0, 0, 0, 0], 114 / 255)  # padding
    assert tensor[0, 0, 320, 320] == 0.0  # image content


def test_decode_maps_letterboxed_boxes_back_to_frame_pixels():
    # 1280x720 frame -> scale 0.5, top padding 140 in a 640 input.
    out = raw_output((320, 320, 100, 200, 0.9))
    [det] = decode(out, scale=0.5, left=0, top=140, frame_w=1280, frame_h=720, threshold=0.5)
    # input box x 270..370, y 220..420 -> frame x 540..740, y (220-140)/0.5=160..560
    assert (det.box.x, det.box.y, det.box.width, det.box.height) == (540, 160, 200, 400)
    assert det.confidence == 0.9 and det.label == "person"


def test_decode_ignores_low_scores_and_other_classes():
    out = raw_output(
        (100, 100, 50, 50, 0.3),            # person, below threshold
        (300, 300, 50, 50, 0.0, 16, 0.95),  # a confident dog — not our business
    )
    assert decode(out, scale=1.0, left=0, top=0, frame_w=640, frame_h=640, threshold=0.5) == []


def test_decode_suppresses_duplicate_boxes_for_one_person():
    out = raw_output((200, 200, 100, 200, 0.9), (205, 202, 100, 200, 0.8), (500, 300, 80, 160, 0.7))
    dets = decode(out, scale=1.0, left=0, top=0, frame_w=640, frame_h=640, threshold=0.5)
    assert [d.confidence for d in dets] == [0.9, 0.7]


def test_decode_clamps_boxes_to_the_frame():
    out = raw_output((10, 10, 100, 100, 0.9))  # hangs off the top-left corner
    [det] = decode(out, scale=1.0, left=0, top=0, frame_w=640, frame_h=480, threshold=0.5)
    assert det.box.x == 0 and det.box.y == 0 and det.box.width == 60


def test_nms_keeps_the_best_of_overlapping_boxes():
    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]], dtype=np.float32)
    assert nms(boxes, np.array([0.5, 0.9, 0.4]), 0.45) == [1, 2]
