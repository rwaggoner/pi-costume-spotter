"""The Detector port: the pipeline's only view of an inference backend."""

from abc import ABC, abstractmethod

import numpy as np

from costume_spotter.events.events import Detection


class Detector(ABC):
    """Finds people in a single RGB frame.

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
