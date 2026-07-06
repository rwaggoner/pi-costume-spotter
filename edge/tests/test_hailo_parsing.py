"""person_rows(): the Hailo result-shape normalizer (issue #7).

The picamera2 Hailo helper returns per-class results whose shape depends on
content; the empty case crashed the pipeline on the first real on-Pi frame.
These tests run anywhere — the normalizer is module-level precisely so it
doesn't need the hardware the rest of hailo.py needs.
"""

import numpy as np

from costume_spotter.detection.hailo import person_rows


def test_empty_python_list_yields_zero_rows():
    # The (1, 0) np.atleast_2d trap that took the pipeline down (issue #7).
    assert person_rows([[], []]).shape == (0, 5)


def test_empty_ndarray_yields_zero_rows():
    assert person_rows([np.empty((0, 5)), np.empty((0, 5))]).shape == (0, 5)


def test_single_flat_detection_is_reshaped():
    rows = person_rows([np.array([0.1, 0.2, 0.5, 0.4, 0.9]), []])
    assert rows.shape == (1, 5)
    y0, x0, y1, x1, score = rows[0]
    assert float(score) == np.float32(0.9)


def test_normal_matrix_passes_through():
    two = np.array([[0.1, 0.2, 0.5, 0.4, 0.9], [0.3, 0.3, 0.8, 0.6, 0.7]])
    assert person_rows([two]).shape == (2, 5)


def test_missing_person_class_yields_zero_rows():
    # Defensive: a model with an unexpected class layout must not crash us.
    assert person_rows([]).shape == (0, 5)
