"""Abstract base class for all rover brains."""

from abc import ABC, abstractmethod
import numpy as np

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from shared.protocol import BrainResult


class Brain(ABC):
    """Base class for rover brains."""

    name: str = "base"

    @abstractmethod
    def act(self, frame: np.ndarray, command: str = "") -> BrainResult:
        """Process a camera frame and return an action."""
        ...

    def startup(self):
        """Called once when the brain is loaded."""
        pass

    def shutdown(self):
        """Called when the brain is unloaded."""
        pass
