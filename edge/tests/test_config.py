"""Settings: profile-driven hardware defaults.

Regression tests for a field bug: a Pi configured with EDGE_PROFILE=pi (and
nothing else) ran the synthetic test scene, because camera/detector defaults
ignored the profile. The profile must be the one switch that re-wires hardware
(ADR-008); explicit values remain overrides.
"""

from costume_spotter.config import Profile, Settings


def make(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)  # _env_file=None: a developer's .env must not leak in


def test_dev_profile_defaults_to_synthetic_and_mock():
    settings = make(edge_profile=Profile.DEV)
    assert settings.camera_source == "synthetic"
    assert settings.detector == "mock"


def test_pi_profile_defaults_to_picamera2_and_hailo():
    settings = make(edge_profile=Profile.PI)
    assert settings.camera_source == "picamera2"
    assert settings.detector == "hailo"


def test_explicit_values_override_the_profile():
    settings = make(edge_profile=Profile.PI, camera_source="webcam", detector="hog")
    assert settings.camera_source == "webcam"
    assert settings.detector == "hog"
