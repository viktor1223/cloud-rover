---
title: "Experiment Plan: VLA vs World Model for Robotic Navigation"
description: "Structured evaluation comparing Vision-Language-Action and World Model approaches for real-world rover navigation tasks"
author: Viktor Ciroski
ms.date: 2026-06-09
ms.topic: concept
---

## Motivation

I come from the old school of self-driving cars, where perception meant training
CNNs to run on-vehicle in real time, every model was hand-tuned for the hardware,
and the entire pipeline lived on the car. That world was about squeezing every
last FLOP out of an embedded GPU to detect lanes and obstacles at 30 FPS.

The landscape has shifted. Foundation models now offer general-purpose vision,
language understanding, and action prediction out of the box. Inference can
happen in the cloud or on a beefy desktop rather than on the robot itself.
As a robotics engineer, I want to understand what that shift means in practice:
can these new approaches actually control a physical robot, and how do they
compare to each other?

This is a hobbyist project built on nights and weekends. The rover is a
Raspberry Pi with a camera on wheels, the "cloud brain" is my desktop with a
3070, and the evaluation environment is my (messy) home. The constraints are
real, the budget is small, and the goal is to learn by building.

## Project Goal

Compare two fundamentally different AI approaches for controlling a physical rover,
using the same hardware, same tasks, and same evaluation criteria.
The outcome is a documented, data-driven answer to the question:

> Given a camera-equipped rover with discrete motor controls,
> which approach produces more capable, efficient, and robust navigation:
> learning from human demonstrations (VLA) or learning from exploration (World Model)?

Secondary goals include building transferable infrastructure for future projects
(laundry folding with a robot arm) and understanding which approach generalizes
better to new tasks and sensor configurations.

## Hardware Platform

| Component | Spec |
|-----------|------|
| Edge body | Raspberry Pi 3 Model B (1 GB RAM, aarch64) |
| Camera | ArduCam IMX708 (12 MP, 640x480 @ ~16 FPS via video pipeline) |
| Motor driver | PCA9685 (16-ch PWM, I2C) → 2× L298N H-bridge → 4× TT DC motors |
| Sensors | HC-SR04 ultrasonic (front), ADXL345 accelerometer (I2C) |
| Motor power | 4× AA NiMH (4.8-6V) via battery holder with kill switch |
| Pi power | 5V USB power bank (5000 mAh, 2.5A) |
| Brain compute | Desktop with NVIDIA RTX 3070 (8 GB VRAM) |
| Fallback compute | Azure cloud (GPU instances) |
| Network | Local WiFi (Pi to Desktop, same LAN) |

## Observation and Action Spaces

### Observations (inputs to the brain)

| Sensor | Shape | Rate | Notes |
|--------|-------|------|-------|
| Camera | (480, 640, 3) RGB | ~16 FPS | Primary input for all brains (video pipeline, ADR-001b) |
| Language command | string | On demand | Text instruction from Dev HUD (e.g., "go to the red cup") |
| IMU (ADXL345) | {x, y, z} float g | ~16 FPS | Acceleration, tilt, collision detection. I2C at 0x53 |
| Ultrasonic (HC-SR04) | float cm | ~16 FPS | Front distance (2-400 cm). GPIO trigger + echo |
| Motor state | {left_duty, right_duty, left_dir, right_dir} | ~16 FPS | Actual commands sent to PCA9685 (post-safety override) |

All sensor data is sent from the Pi on every frame for logging and future
training, even during heuristic operation (see ADR-004).

### Actions (outputs from the brain)

**Discrete action space (heuristic brain):**

| Action | Effect |
|--------|--------|
| `FORWARD` | Move forward at 75% duty cycle |
| `LEFT` | Rotate left at 50% duty cycle |
| `RIGHT` | Rotate right at 50% duty cycle |
| `STOP` | Halt all motors |

**Continuous action space (VLA and world model brains):**

| Field | Range | Effect |
|-------|-------|--------|
| `left_speed` | -1.0 to 1.0 | Left wheel pair speed (negative = reverse) |
| `right_speed` | -1.0 to 1.0 | Right wheel pair speed (negative = reverse) |

The Pi motor controller handles both modes. Continuous mode enables the
differential drive needed for learned policies (see ADR-005).

## The Three Brains

### Brain 1: Heuristic Baseline

A handcoded policy with no learning. Provides a performance floor.

| Property | Value |
|----------|-------|
| Type | Rule-based |
| Runs on | Raspberry Pi (no GPU needed) |
| Training data | None |
| How it works | Detects large objects growing in frame center, turns away. Defaults to forward. |
| Purpose | Sanity check. If learned models cannot beat this, something is wrong. |

### Brain 2: OpenVLA (Vision-Language-Action)

An open-source VLA model that maps images and language instructions directly to actions.
Same architecture pattern as Pi-0, which will be used in future projects.

| Property | Value |
|----------|-------|
| Type | End-to-end VLA |
| Model | OpenVLA (7B parameters, quantized for 3070) |
| Runs on | Desktop RTX 3070 |
| Training data | ~50 human demonstrations per task |
| How it works | Takes (image, text instruction) and outputs an action directly. No explicit planning. |
| Learns from | Imitation: "watch me do it" |

The VLA pipeline:

```text
camera frame + "go to the red cup"
        │
        ▼
   OpenVLA (7B)
        │
        ▼
   action: LEFT
```

### Brain 3: DreamerV3 (World Model)

A world model that learns to simulate the environment internally,
then trains an actor policy by planning in imagination.

| Property | Value |
|----------|-------|
| Type | World Model + learned actor + critic |
| Model | DreamerV3 |
| Runs on | Desktop RTX 3070 |
| Training data | Self-generated through exploration |
| How it works | Builds an internal simulation of the world. Imagines future trajectories. Picks actions that maximize predicted reward. |
| Learns from | Trial and error: "let me try and see what happens" |

The DreamerV3 pipeline:

```text
camera frame + reward signal
        │
        ▼
  ┌─────────────────────┐
  │    World Model       │
  │  (learned simulator) │
  └──────────┬──────────┘
             │ imagined rollouts
             ▼
  ┌─────────────────────┐
  │   Actor (Policy)     │
  │  (trained in dreams) │
  └──────────┬──────────┘
             │
             ▼
        action: FORWARD
```

DreamerV3 trains three internal components as one system:

1. The world model learns "if I do action A in state S, what happens next?"
2. The actor learns "given this state, what action maximizes long-term reward?"
3. The critic learns "how good is this state for achieving my goal?"

### Reward Design (DreamerV3 only)

| Signal | Value | Trigger |
|--------|-------|---------|
| Goal reached | +1.0 | Rover within 30 cm of target |
| Collision | -1.0 | Contact with obstacle |
| Step penalty | -0.01 | Every timestep (encourages efficiency) |
| Progress | +0.1 | Closer to target than previous step |

## Task Suite

Five tasks of increasing difficulty. Each task is run five trials per brain.

### T1: Drive to Object

| Property | Value |
|----------|-------|
| Command | "Drive to the red cup" |
| Setup | Single target object on the floor, 1-3 meters away, clear path |
| Success | Rover stops within 30 cm of the target |
| Measures | Basic visual grounding and approach behavior |

### T2: Avoid Obstacle

| Property | Value |
|----------|-------|
| Command | "Go forward, avoid the box" |
| Setup | Target ahead with one obstacle between rover and target |
| Success | Reaches target without collision |
| Measures | Obstacle avoidance while maintaining goal direction |

### T3: Room Navigation

| Property | Value |
|----------|-------|
| Command | "Go to the kitchen" |
| Setup | Rover starts in a different room, must navigate through doorway |
| Success | Rover enters correct room |
| Measures | Spatial reasoning, long-horizon planning |

### T4: Hallway Following

| Property | Value |
|----------|-------|
| Command | "Follow the hallway to the end" |
| Setup | Hallway with walls on both sides |
| Success | Reaches end of hallway without bumping walls |
| Measures | Continuous course correction, wall avoidance |

### T5: Recovery Under Perturbation

| Property | Value |
|----------|-------|
| Command | Same as T1 (drive to object) |
| Setup | Mid-task, manually push the rover 30-50 cm off course |
| Success | Rover recovers and completes the original task |
| Measures | Robustness, closed-loop correction |

## Evaluation Strategy

### Metrics

Each trial records the following:

| Metric | Unit | How Measured |
|--------|------|-------------|
| Success rate | % (over 5 trials) | Did the rover achieve the goal? |
| Path efficiency | Ratio (actual path length / optimal) | Wheel encoder or step count vs straight-line distance |
| Collision count | Integer | Contact sensor or manual observation |
| Inference latency | ms | Time from frame received to action returned |
| Total loop latency | ms | Capture to motor actuation (full round trip) |
| Time to completion | seconds | Start to goal reached |
| Recovery success | boolean (T5 only) | Did it recover after perturbation? |

### Evaluation Protocol

1. Reset rover to the same start position for each trial
2. Issue the language command via the Dev HUD
3. Record telemetry through the dashboard (cold path, no interference)
4. Human observer marks collisions and goal completion
5. Each task runs five trials per brain (75 total trials: 5 tasks x 5 trials x 3 brains)

### Controlling for Variability

The home environment is not a controlled lab. To manage this:

| Concern | Mitigation |
|---------|-----------|
| Furniture moves | Photograph the room before each session, note changes |
| Lighting varies | Run all three brains in the same session, back-to-back |
| Start position drift | Mark start position with tape on the floor |
| Human bias in scoring | Record video of every trial for review |

### Reporting

Results will be presented as:

1. A summary table: task x brain x metric
2. Latency waterfall comparison (from Dev HUD data)
3. Per-task analysis noting qualitative behavior differences
4. A "lessons learned" section covering practical challenges

## Training Plan

### OpenVLA

| Phase | Description |
|-------|-------------|
| Data collection | Teleoperate the rover through each task 50 times, recording (image, action) pairs via the Dev HUD |
| Fine-tuning | Fine-tune OpenVLA on the demonstration dataset using the desktop 3070 |
| Deployment | Load quantized model, serve inference over WebSocket to Pi |

### DreamerV3

| Phase | Description |
|-------|-------------|
| Exploration | Let the rover drive randomly while DreamerV3 builds its world model (estimated 2-4 hours of real-world interaction) |
| Imagination training | Actor and critic train on imagined rollouts inside the learned world model (runs on GPU, no rover needed) |
| Deployment | Serve trained actor over WebSocket to Pi |

### Heuristic

No training required. Hardcoded logic, tuned by hand.

## Architecture (Software)

```text
pi/
  edge_stream.py       — capture + push frames via WebSocket
  motor_controller.py  — execute discrete actions on GPIO
  edge_agent.py        — main loop: receive action, execute, send next frame

cloud/
  dashboard.py         — Dev HUD server (cold path observability)
  brain_server.py      — WebSocket server, routes frames to active brain
  brains/
    base.py            — abstract Brain interface
    heuristic.py       — rule-based baseline
    openvla.py         — VLA brain
    dreamer.py         — DreamerV3 brain

shared/
  protocol.py          — message schemas (Frame, Action, Telemetry)
  actions.py           — action space definition

eval/
  runner.py            — evaluation harness (runs N trials, records metrics)
  metrics.py           — metric computation
  results/             — raw trial data (JSON per trial)
  reports/             — generated comparison reports
```

All three brains implement the same interface:

```python
class Brain:
    def act(self, frame: ndarray, command: str) -> Action:
        """Given camera frame + language command, return an action."""
        ...
```

## Open Questions

1. How do we define "goal reached" automatically? (Vision-based? ArUco marker at target? Manual button press?)
2. Should DreamerV3 exploration be sim-first (train in a simulator, transfer to real) or real-only?
3. For OpenVLA, do we collect demonstrations via keyboard teleoperation or a joystick?
4. Can a digital twin (simulated PCA9685 + L298N + physics) validate the motor control code before hardware assembly?

## Timeline

| Phase | Tasks |
|-------|-------|
| Phase 1 (current) | Camera streaming, Dev HUD, motor control, edge agent loop |
| Phase 2 | Brain interface, heuristic baseline, teleoperation for data collection |
| Phase 3 | OpenVLA fine-tuning and deployment |
| Phase 4 | DreamerV3 training and deployment |
| Phase 5 | Evaluation: run all 75 trials, collect data |
| Phase 6 | Analysis and report |
