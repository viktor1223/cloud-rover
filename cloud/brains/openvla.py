"""OpenVLA Brain — Vision-Language-Action model (stub).

This brain will be implemented after:
1. Motors are working and teleoperation is built
2. ~50 demonstrations per task are collected
3. OpenVLA is fine-tuned on the demonstration dataset

For now, this returns a placeholder result.
"""

import time
import numpy as np

from .base import Brain

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from shared.protocol import Action, BrainResult


class OpenVLABrain(Brain):

    name = "openvla"

    def startup(self):
        print("  ⚠ OpenVLA brain is a stub. Fine-tuning required.")

    def act(self, frame: np.ndarray, command: str = "") -> BrainResult:
        return BrainResult(
            action=Action.STOP,
            detections=[],
            reasoning="OpenVLA not yet trained. Requires demonstration data.",
            inference_ms=0.0,
            brain_name=self.name,
        )
