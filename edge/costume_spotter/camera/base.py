"""The FrameSource port: the pipeline's only view of a camera."""

from abc import ABC, abstractmethod

import numpy as np


class FrameSource(ABC):
    """Produces RGB frames on demand.

    Contract:
    - ``read()`` blocks (briefly) until the next frame and returns an RGB uint8
      ndarray of shape (H, W, 3). It is called from a worker thread by the
      pipeline, so blocking is fine — implementations should NOT spin their own
      threads unless the underlying SDK forces it.
    - ``close()`` releases the device; safe to call twice.
    """

    @abstractmethod
    def read(self) -> np.ndarray: ...

    def close(self) -> None:  # optional for sources with nothing to release
        return None
