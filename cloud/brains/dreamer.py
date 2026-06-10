"""DreamerV3 Brain — World Model + learned actor (stub).

This brain will be implemented after:
1. Motors are working
2. The heuristic brain has collected initial experience data
3. DreamerV3 is trained on the replay buffer

For now, this returns a placeholder result.
"""

import time
import numpy as np

from .base import Brain

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from shared.protocol import Action, BrainResult


class DreamerBrain(Brain):

    name = "dreamer"

    def startup(self):
        print("  ⚠ DreamerV3 brain is a stub. Exploration training required.")

    def act(self, frame: np.ndarray, command: str = "") -> BrainResult:
        return BrainResult(
            action=Action.STOP,
            detections=[],
            reasoning="DreamerV3 not yet trained. Requires exploration data.",
            inference_ms=0.0,
            brain_name=self.name,
        )
