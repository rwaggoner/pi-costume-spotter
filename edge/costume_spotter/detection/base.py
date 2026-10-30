"""The Detector port: the pipeline's only view of an inference backend."""

from abc import ABC, abstractmethod

import numpy as np

from costume_spotter.events.events import Detection

# COCO class ids the porch cares about. Detection.label carries the name, so
# nothing downstream ever sees a vendor class id (01-F4).
PERSON_CLASSES: dict[int, str] = {0: "person"}
PET_CLASSES: dict[int, str] = {15: "cat", 16: "dog"}


def wanted_classes(detect_pets: bool) -> dict[int, str]:
    """People always; dogs and cats when DETECT_PETS is on (01-F7)."""
    return {**PERSON_CLASSES, **PET_CLASSES} if detect_pets else dict(PERSON_CLASSES)


class Detector(ABC):
    """Finds people (and, where supported, pets) in a single RGB frame.

    Contract (enforced by tests/contracts/test_detector_contract.py):
    - stateless per call: same frame in, same detections out (tracking is NOT
      the detector's job — see docs/requirements/02-tracking.md);
    - returned boxes lie within frame bounds;
    - detections below the configured confidence threshold are already
      filtered out (01-F5);
    - called from a worker thread; may block for the duration of inference.
    """

    #: Name recorded on sightings so the data says which backend produced it.
    name: str = "unknown"

    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[Detection]: ...

    def close(self) -> None:
        return None
