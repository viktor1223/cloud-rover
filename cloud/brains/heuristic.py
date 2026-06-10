"""Heuristic Brain — YOLO detection + rule-based planner.

Uses YOLOv8-nano for real-time object detection and a simple
heuristic planner that maps detections to discrete rover actions.

Planning rules:
    1. If a goal object is specified (command), steer toward it.
    2. If an obstacle is large and centered, stop or steer away.
    3. If the path ahead is clear, go forward.
    4. If no goal is specified, default to obstacle avoidance.
"""

import time
import numpy as np

import sys, os
_root = os.path.join(os.path.dirname(__file__), "..", "..")
if _root not in sys.path:
    sys.path.insert(0, _root)

from cloud.brains.base import Brain
from shared.protocol import Action, Detection, BrainResult


# Objects considered obstacles (COCO classes)
OBSTACLES = {
    "person", "cat", "dog", "chair", "couch", "bed", "dining table",
    "toilet", "tv", "laptop", "refrigerator", "oven", "suitcase",
    "backpack", "handbag", "bicycle", "motorcycle", "car", "truck",
}

# Frame is divided into thirds for steering decisions
LEFT_ZONE = 0.33
RIGHT_ZONE = 0.67

# If a detection covers more than this fraction of the frame, it's "close"
CLOSE_THRESHOLD = 0.15  # 15% of frame area


class HeuristicBrain(Brain):
    """YOLO detection + rule-based navigation planner."""

    name = "heuristic"

    def __init__(self, model_size: str = "yolov8n.pt", confidence: float = 0.4):
        self.model_size = model_size
        self.confidence = confidence
        self.model = None

    def startup(self):
        from ultralytics import YOLO
        print(f"  Loading {self.model_size}...")
        self.model = YOLO(self.model_size)
        print(f"  ✓ {self.model_size} loaded")

    def shutdown(self):
        self.model = None

    def _detect(self, frame: np.ndarray) -> list[Detection]:
        """Run YOLO on a frame and return detections."""
        results = self.model(frame, conf=self.confidence, verbose=False)
        detections = []
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                label = self.model.names[cls_id]
                conf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append(Detection(
                    label=label,
                    confidence=conf,
                    x1=x1, y1=y1, x2=x2, y2=y2,
                ))
        return detections

    def _plan(self, detections: list[Detection], command: str,
              frame_w: int, frame_h: int) -> tuple[Action, str]:
        """Map detections + command to an action with reasoning."""
        frame_area = frame_w * frame_h

        # Parse the goal from the command (simple keyword match)
        goal_object = None
        if command:
            cmd_lower = command.lower()
            for d in detections:
                if d.label.lower() in cmd_lower:
                    goal_object = d
                    break

        # If we have a goal object, steer toward it
        if goal_object:
            cx_norm = goal_object.center_x / frame_w
            obj_area_frac = goal_object.area / frame_area

            # Close enough? Stop.
            if obj_area_frac > 0.25:
                return Action.STOP, (
                    f"Goal '{goal_object.label}' is close "
                    f"({obj_area_frac:.0%} of frame). Stopping."
                )

            # Steer toward goal
            if cx_norm < LEFT_ZONE:
                return Action.LEFT, (
                    f"Goal '{goal_object.label}' is on the left "
                    f"(x={cx_norm:.0%}). Turning left."
                )
            elif cx_norm > RIGHT_ZONE:
                return Action.RIGHT, (
                    f"Goal '{goal_object.label}' is on the right "
                    f"(x={cx_norm:.0%}). Turning right."
                )
            else:
                return Action.FORWARD, (
                    f"Goal '{goal_object.label}' is centered "
                    f"(x={cx_norm:.0%}). Moving forward."
                )

        # No goal — obstacle avoidance mode
        obstacles = [
            d for d in detections
            if d.label in OBSTACLES and d.area / frame_area > CLOSE_THRESHOLD
        ]

        if not obstacles:
            if not detections:
                return Action.FORWARD, "No objects detected. Path clear, moving forward."
            return Action.FORWARD, (
                f"{len(detections)} objects detected, none blocking. "
                "Moving forward."
            )

        # Find the largest obstacle
        biggest = max(obstacles, key=lambda d: d.area)
        cx_norm = biggest.center_x / frame_w
        area_frac = biggest.area / frame_area

        # Very close — stop
        if area_frac > 0.4:
            return Action.STOP, (
                f"Large obstacle '{biggest.label}' "
                f"({area_frac:.0%} of frame). Emergency stop."
            )

        # Obstacle left of center — go right
        if cx_norm < 0.5:
            return Action.RIGHT, (
                f"Obstacle '{biggest.label}' on the left "
                f"(x={cx_norm:.0%}, area={area_frac:.0%}). Steering right."
            )
        else:
            return Action.LEFT, (
                f"Obstacle '{biggest.label}' on the right "
                f"(x={cx_norm:.0%}, area={area_frac:.0%}). Steering left."
            )

    def act(self, frame: np.ndarray, command: str = "") -> BrainResult:
        t0 = time.monotonic()
        h, w = frame.shape[:2]

        detections = self._detect(frame)
        action, reasoning = self._plan(detections, command, w, h)

        inference_ms = (time.monotonic() - t0) * 1000

        return BrainResult(
            action=action,
            detections=detections,
            reasoning=reasoning,
            inference_ms=inference_ms,
            brain_name=self.name,
        )
