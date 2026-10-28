"""Webcam backend selection (ADR-010). Pure mapping logic — no camera, no cv2."""

import pytest

from costume_spotter.camera.opencv_source import resolve_backend


def test_auto_picks_directshow_on_windows():
    assert resolve_backend("auto", platform="win32") == "CAP_DSHOW"


def test_auto_leaves_the_choice_to_opencv_elsewhere():
    assert resolve_backend("auto", platform="linux") == "CAP_ANY"


def test_explicit_backend_is_case_insensitive():
    assert resolve_backend("MSMF", platform="win32") == "CAP_MSMF"


def test_unknown_backend_fails_fast_with_the_options():
    with pytest.raises(ValueError, match="dshow"):
        resolve_backend("gstreamer")
