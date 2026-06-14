# Architecture Decisions

Technical decisions, benchmarks, and known limitations for the Cloud Rover project.

## ADR-001: Camera Capture Pipeline Selection (IMX708 + picamera2)

**Date:** 2026-06-09
**Updated:** 2026-06-09
**Status:** Superseded by ADR-001b

### Context

Benchmarked the ArduCam IMX708 camera module on a Raspberry Pi 3 Model B using `picamera2`'s still capture pipeline (`create_still_configuration`). Tested across multiple resolutions and JPEG quality levels.

### Benchmark Results (Still Pipeline)

| Config | Capture (ms) | Encode (ms) | Total (ms) | Max FPS | JPEG Size (KB) |
|--------|-------------|-------------|------------|---------|----------------|
| 640x480 q=85 | 63.5 | 62.9 | 126.5 | 7.9 | 13.7 |
| 640x480 q=50 | 62.7 | 75.7 | 138.4 | 7.2 | 5.9 |
| 640x480 q=30 | 59.0 | 62.4 | 121.5 | 8.2 | 5.6 |
| 320x240 q=50 | 105.0 | 16.1 | 121.0 | 8.3 | 2.2 |
| 320x240 q=30 | 96.8 | 24.7 | 121.5 | 8.2 | 1.9 |
| 480x360 q=50 | 55.2 | 67.9 | 123.1 | 8.1 | 3.8 |

### Original Findings

- The sensor readout was the bottleneck at 55-105 ms per frame.
- ~8 FPS was the hard ceiling with the still pipeline.

---

## ADR-001b: Switch to Video Pipeline (2x FPS Improvement)

**Date:** 2026-06-09
**Status:** Accepted

### Context

The still pipeline (`create_still_configuration`) applies heavy per-frame ISP
processing designed for photography. The video pipeline
(`create_video_configuration`) uses a lighter processing path designed for
continuous streaming. We benchmarked both on the same hardware.

### Benchmark Results (Still vs Video)

| Config | Capture (ms) | Encode (ms) | Total (ms) | Max FPS | JPEG Size (KB) |
|--------|-------------|-------------|------------|---------|----------------|
| 640x480 q=50 [still] | 64.0 | 59.6 | 123.5 | 8.1 | 6.2 |
| 640x480 q=50 [video] | 4.2 | 59.0 | 63.2 | 15.8 | 6.7 |
| 640x480 q=85 [video] | 4.1 | 61.1 | 65.2 | 15.3 | 25.4 |
| 640x480 q=30 [video] | 4.0 | 58.6 | 62.6 | 16.0 | 5.7 |
| 320x240 q=50 [video] | 16.5 | 15.1 | 31.7 | 31.6 | 2.3 |
| 480x360 q=50 [video] | 3.0 | 33.8 | 36.8 | 27.2 | 4.1 |

### Key Findings

- **Video pipeline reduces capture time from 64 ms to 4 ms** (16x improvement).
- **FPS doubled at 640x480**: 8 FPS (still) to 16 FPS (video).
- **The new bottleneck is JPEG encoding** (~59 ms via Pillow software encode), no longer the camera.
- **Lower resolutions now actually help**: 480x360 reaches 27 FPS, 320x240 reaches 32 FPS.
- **Image quality difference is negligible** for ML inference (slightly different color space metadata, same visual output).

### Decision

Use `create_video_configuration` with **640x480 at JPEG quality 50** as the
default. This delivers 16 FPS at 6.7 KB per frame with no quality loss that
matters for the brain.

### Future Optimization

The remaining bottleneck is PIL's software JPEG encoding (59 ms). Options to
push FPS higher:

- Use `turbojpeg` (libjpeg-turbo Python bindings) for ~3-5x faster JPEG encode
- Drop resolution to 480x360 for 27 FPS with acceptable quality
- Send raw frames over the network and encode on the desktop GPU

### Hardware

- Board: Raspberry Pi 3 Model B v1.2 (1 GB RAM, aarch64)
- Camera: ArduCam IMX708 (12 MP)
- Sensor driver: libcamera v0.7.1+rpt20260429
- Software: picamera2 0.3.34, Pillow 11.1.0

---

## ADR-002: Motor Control Architecture (Cloud Brain → Pi Executor)

**Date:** 2026-06-09
**Status:** Accepted

### Context

The cloud brain (running on the desktop) processes camera frames and decides
actions (FORWARD, LEFT, RIGHT, STOP). Those actions must be translated into
physical motor movement on the rover. The question is where the motor control
logic lives and how the signal path works.

### Decision

Split motor control into two layers:

1. **Cloud brain** outputs high-level actions (direction + optional speed).
2. **Pi executor** receives actions over WebSocket and translates them to I2C
   register writes for the PCA9685 PWM driver, which in turn drives 2× L298N
   H-bridges controlling 4 DC motors.

### Signal Path

```
Cloud Brain ──{"action":"FORWARD","speed":0.75}──ws──▶ Pi (edge_stream.py)
                                                            │
                                                     motor_controller.py
                                                            │ maps action → 12 duty-cycle values
                                                            │ I2C writes on SDA/SCL (2 wires)
                                                            ▼
                                                        PCA9685 (0x40)
                                                     16-ch hardware PWM
                                                       │            │
                                                  6 PWM signals  6 PWM signals
                                                       ▼            ▼
                                                   L298N #1      L298N #2
                                                   (FL + FR)     (RL + RR)
                                                     │   │         │   │
                                                    FL   FR       RL   RR
```

### PCA9685 Channel Mapping (matches diagram.json)

Direction pins (IN1-IN4) are grouped first, speed pins (ENA/ENB) follow.

| PCA Channel | L298N Board | L298N Pin | Motor | Purpose |
|-------------|-------------|-----------|-------|---------|
| 0 | #1 (bridge_ab) | IN1 | Front-Left | Direction A (HIGH/LOW) |
| 1 | #1 (bridge_ab) | IN2 | Front-Left | Direction B (HIGH/LOW) |
| 2 | #1 (bridge_ab) | IN3 | Front-Right | Direction A (HIGH/LOW) |
| 3 | #1 (bridge_ab) | IN4 | Front-Right | Direction B (HIGH/LOW) |
| 4 | #1 (bridge_ab) | ENA | Front-Left | Speed (PWM duty cycle) |
| 5 | #1 (bridge_ab) | ENB | Front-Right | Speed (PWM duty cycle) |
| 6 | #2 (bridge_cd) | IN1 | Rear-Left | Direction A (HIGH/LOW) |
| 7 | #2 (bridge_cd) | IN2 | Rear-Left | Direction B (HIGH/LOW) |
| 8 | #2 (bridge_cd) | IN3 | Rear-Right | Direction A (HIGH/LOW) |
| 9 | #2 (bridge_cd) | IN4 | Rear-Right | Direction B (HIGH/LOW) |
| 10 | #2 (bridge_cd) | ENA | Rear-Left | Speed (PWM duty cycle) |
| 11 | #2 (bridge_cd) | ENB | Rear-Right | Speed (PWM duty cycle) |
| 12-15 | — | — | Spare | Camera servos or gripper |

### Motor Direction Truth Table (per motor)

| IN1 | IN2 | ENA | Result |
|-----|-----|-----|--------|
| HIGH | LOW | PWM | Forward at duty-cycle speed |
| LOW | HIGH | PWM | Reverse at duty-cycle speed |
| HIGH | HIGH | any | Brake (motor locked) |
| LOW | LOW | any | Coast (motor free-spins) |

### Why the PCA9685

- Uses only **2 GPIO pins** (I2C: SDA + SCL) to control all 12 motor signals.
  Frees GPIO for ultrasonic, accelerometer, and future sensors.
- **Hardware PWM** at 12-bit resolution (4096 steps). The Pi's software PWM is
  jittery and CPU-intensive.
- **Autonomous output**: once programmed, the PCA9685 keeps generating PWM with
  zero CPU involvement until the next I2C write. The Pi only talks to it when
  the action changes.

### Why Motor Translation Lives on the Pi

1. **Physical necessity**: the I2C bus is local to the Pi. The cloud cannot write
   to PCA9685 registers.
2. **Safety**: if the network drops, the Pi can immediately set all channels to 0
   (STOP). If the logic lived on the cloud side, a disconnection means the PCA
   keeps outputting the last command and the rover drives into a wall.
3. **Clean separation**: the cloud brain doesn't know about PCA9685 or L298N. It
   says "go forward." If the motor driver changes, only the Pi code changes.

---

## ADR-003: Speed Control Strategy (Phased Approach)

**Date:** 2026-06-09
**Status:** Accepted

### Context

The current action space is discrete (FORWARD/LEFT/RIGHT/STOP) with no speed
information. Motors need a duty-cycle value. The question is how speed is
determined and how this evolves as brains get more capable.

### Decision

Three phases, each building on the last:

**Phase 1 — Fixed per-action (heuristic brain, v1):**

Hardcoded lookup table in the Pi motor controller:

| Action | Duty Cycle |
|--------|-----------|
| FORWARD | 0.75 (75%) |
| LEFT | 0.50 (50%) |
| RIGHT | 0.50 (50%) |
| STOP | 0.00 (0%) |

No protocol changes needed. Gets the hardware validated.

**Phase 2 — Pi safety cap (ultrasonic override):**

The HC-SR04 ultrasonic sensor is wired directly to the Pi. Regardless of what
the brain commands, the Pi modulates speed based on proximity:

| Distance | Behavior |
|----------|----------|
| < 15 cm | Emergency stop (override to 0.0) |
| 15-40 cm | Cap speed at 0.3 |
| > 40 cm | Use brain-requested speed |

This is reactive safety that doesn't depend on network latency.

**Phase 3 — Brain sends speed (continuous action space):**

Extend the protocol with a `speed` field (0.0–1.0). For VLA and world models,
extend further to continuous differential drive:

```json
{"action": "CONTINUOUS", "left_speed": 0.3, "right_speed": 0.7}
```

The discrete action space (4 options) is too coarse for learned models. A VLA or
world model needs to express "go slightly left at medium speed."

### Why Phase It

- Phase 1 proves the hardware.
- Phase 2 adds safety before learned models take control.
- Phase 3 is required for VLA/DreamerV3 but doesn't make sense until those
  brains exist.

---

## ADR-004: Full Sensor Telemetry (Pi → Cloud → Dashboard)

**Date:** 2026-06-09
**Status:** Accepted

### Context

The Pi currently sends only camera frames to the cloud. For world model training
(DreamerV3) and imitation learning (OpenVLA), richer observation data is needed.
The question is what to send and when.

### Decision

Send **all sensor data** from the Pi on every frame, starting from day one. Even
during heuristic operation, the data is logged for future training.

### Observation Packet Schema

```json
{
  "type": "frame",
  "seq": 142,
  "ts": 1718000000.123,

  "frame": "<base64 JPEG>",

  "accel": {"x": 0.02, "y": -0.01, "z": 9.81},
  "distance_cm": 47.3,

  "motors": {
    "left_duty": 0.75,
    "right_duty": 0.75,
    "left_dir": "forward",
    "right_dir": "forward"
  },

  "capture_ms": 4.2,
  "encode_ms": 59.0,
  "sensor_ms": 15.3
}
```

### Why Each Sensor Matters for Learning

| Sensor | Training Value |
|--------|---------------|
| Camera | Visual state: where objects are, scene context |
| IMU (ADXL345) | Physics: acceleration, tilt, collision detection, surface type |
| Ultrasonic (HC-SR04) | Depth ground truth: calibrates the model's distance estimates from vision |
| Motor state | The action *actually executed* after safety overrides, not what the brain requested |

### Critical Detail: Motor State as Ground-Truth Action Label

If the brain requests FORWARD at 0.8 but the ultrasonic safety cap reduces it to
0.3, the world model must know the rover went at 0.3. The motor state field
records what was actually commanded to the PCA9685, making it the true action
label for training.

### Performance Budget

| Sensor Read | Time | Method |
|-------------|------|--------|
| Camera capture | ~4 ms | Video pipeline (ADR-001b) |
| IMU (ADXL345) | ~0.1 ms | I2C read (address 0x53) |
| Ultrasonic (HC-SR04) | ~15 ms | GPIO trigger + echo timing |
| Motor state | ~0 ms | Local variable, no I/O |
| JPEG encode | ~59 ms | Pillow (bottleneck) |
| **Total** | **~78 ms** | **~13 FPS** |

The sonar adds ~15 ms to the loop but still fits within the frame budget. Can be
moved to a separate thread if it becomes a bottleneck.

---

## ADR-005: Action Space Evolution (Discrete → Continuous)

**Date:** 2026-06-09
**Status:** Accepted

### Context

The heuristic brain uses a 4-option discrete action space. VLA and world model
brains need continuous control to express nuanced movement.

### Decision

Support both discrete and continuous actions through the same protocol. The Pi
motor controller handles both:

**Discrete (heuristic brain):**

```json
{"action": "FORWARD"}
```

Pi maps to fixed duty cycles via lookup table.

**Continuous (VLA / DreamerV3):**

```json
{"action": "CONTINUOUS", "left_speed": 0.3, "right_speed": 0.7}
```

Pi maps directly to PCA9685 duty cycles for differential drive. Left and right
values are -1.0 (full reverse) to 1.0 (full forward).

### Why Differential Drive

The rover has 4 wheels in a skid-steer configuration (left pair + right pair).
Two values (left_speed, right_speed) fully describe the motion:

| Left | Right | Motion |
|------|-------|--------|
| 0.5 | 0.5 | Forward at 50% |
| -0.5 | -0.5 | Reverse at 50% |
| 0.0 | 0.5 | Pivot left |
| 0.5 | 0.0 | Pivot right |
| 0.3 | 0.7 | Gentle right curve |
| -0.3 | 0.3 | Spin in place (left) |

This maps naturally to what both VLAs and world models want to output: a
low-dimensional continuous action vector.

---

## ADR-006: Single Repo with Directory-Based Separation

**Date:** 2026-06-09
**Status:** Accepted

### Context

The project has code for three execution targets: the Raspberry Pi, the cloud
(Mac/desktop), and shared libraries. The question is whether to use one repo or
multiple.

### Decision

Single repo (`cloud-rover/`) with directory-based separation. Three repos would
add git submodule overhead for ~15 files.

### Layout

```
cloud-rover/
├── shared/              ← Installed on BOTH sides
│   ├── __init__.py
│   └── protocol.py      ← Action, Detection, BrainResult
│
├── pi/                  ← ONLY deployed to the Pi
│   ├── requirements.txt ← picamera2, adafruit-pca9685, gpiozero
│   ├── edge_stream.py   ← Camera + sensors + receive actions
│   └── motor_controller.py ← Action → PCA9685 I2C writes
│
├── cloud/               ← ONLY runs on the Mac
│   ├── requirements.txt ← ultralytics, websockets, numpy
│   ├── brain_server.py  ← WebSocket router + HTTP dashboard
│   └── brains/
│       ├── base.py      ← Brain ABC (shared across all brains)
│       ├── heuristic.py ← YOLO + rules (heuristic only)
│       ├── openvla.py   ← VLA brain (stub)
│       └── dreamer.py   ← World model brain (stub)
│
├── scripts/
│   └── deploy.sh        ← rsync pi/ + shared/ to Pi (never cloud/)
│
└── yolov8n.pt           ← Heuristic brain weights (Mac only)
```

### Separation Mechanisms

| Mechanism | How |
|-----------|-----|
| **Deployment** | `deploy.sh` rsyncs only `pi/` and `shared/` to the Pi |
| **Dependencies** | Each side has its own `requirements.txt` |
| **Brain selection** | `--brain heuristic` flag on `brain_server.py` |
| **Pi is brain-agnostic** | `edge_stream.py` and `motor_controller.py` work identically regardless of which brain is active |

### What's Shared vs Brain-Specific

| Component | Shared or Brain-Specific |
|-----------|--------------------------|
| `brain_server.py` | Shared — routes frames to any brain |
| `base.py` (Brain ABC) | Shared — all brains implement this |
| `protocol.py` | Shared — message schemas |
| `edge_stream.py` | Shared — camera + sensors + action receiver |
| `motor_controller.py` | Shared — translates any brain's action to PCA writes |
| `heuristic.py` | Heuristic only — YOLO + rule planner |
| `yolov8n.pt` | Heuristic only — model weights |
| `openvla.py` | OpenVLA only (future) |
| `dreamer.py` | DreamerV3 only (future) |
