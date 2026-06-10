"""Shared protocol definitions for Cloud Rover.

Defines the action space, message schemas, and data structures
used across Pi (edge), brain (cloud/desktop), and dashboard.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Action(str, Enum):
    """Discrete action space for the rover."""
    FORWARD = "FORWARD"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    STOP = "STOP"


@dataclass
class Detection:
    """A single object detection with bounding box."""
    label: str
    confidence: float
    x1: float  # top-left x (pixels)
    y1: float  # top-left y (pixels)
    x2: float  # bottom-right x (pixels)
    y2: float  # bottom-right y (pixels)

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.width * self.height

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "confidence": round(self.confidence, 3),
            "x1": round(self.x1, 1),
            "y1": round(self.y1, 1),
            "x2": round(self.x2, 1),
            "y2": round(self.y2, 1),
        }


@dataclass
class BrainResult:
    """Output from a brain after processing a frame."""
    action: Action
    detections: list[Detection] = field(default_factory=list)
    reasoning: str = ""            # why this action was chosen
    inference_ms: float = 0.0      # how long the brain took
    brain_name: str = ""           # which brain produced this

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "detections": [d.to_dict() for d in self.detections],
            "reasoning": self.reasoning,
            "inference_ms": round(self.inference_ms, 1),
            "brain_name": self.brain_name,
        }
