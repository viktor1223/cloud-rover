# Cloud Rover

A vision-based autonomous rover using a Raspberry Pi as the edge body and a Mac/cloud-hosted AI brain for real-time object detection and navigation planning. Frames stream from the Pi to the brain over WebSocket; the brain runs YOLO detection, decides an action, and relays everything to a live dashboard in the browser.

## Architecture

```
┌─────────────────┐   ws:9091   ┌──────────────────────┐   ws:9091   ┌────────────┐
│   Raspberry Pi  │ ──────────▶ │     Brain Server     │ ──────────▶ │  Dashboard  │
│   (Edge Body)   │   frames    │       (Mac)          │  frames +   │  (Browser)  │
├─────────────────┤             ├──────────────────────┤  detections ├────────────┤
│ • Camera capture│             │ • YOLOv8 detection   │             │ • Live feed │
│ • Motor control │             │ • Heuristic planner  │             │ • Telemetry │
│ • Sensor reading│             │ • (future) OpenVLA   │             │ • Controls  │
│ • edge_stream.py│             │ • (future) DreamerV3 │             │ • Signal    │
└─────────────────┘             └──────────────────────┘             └────────────┘
```

**Hot path:** Pi captures frames → Brain Server processes with YOLO + planner → sends action back to Pi and relays annotated frames to the dashboard.

**Ports:** HTTP dashboard on `:9090`, WebSocket on `:9091`.

## Project Structure

```
pi/                         — Code that runs on the Raspberry Pi
  edge_stream.py            — Main capture loop, pushes frames to brain via WebSocket
  camera_test.py            — Quick camera diagnostic (capture + save one frame)
  camera_benchmark.py       — Benchmark capture/encode across resolutions
  camera_stream.py          — HTTP MJPEG stream for remote viewing

cloud/                      — Brain + dashboard that run on Mac
  brain_server.py           — WebSocket server: receives frames, runs brain, serves dashboard
  dashboard.py              — Standalone dev HUD (cold-path telemetry only)
  mock_brain.py             — HTTP mock brain for testing without YOLO
  brains/
    base.py                 — Abstract Brain base class
    heuristic.py            — YOLOv8-nano + rule-based planner (working)
    openvla.py              — OpenVLA stub (needs demonstration data)
    dreamer.py              — DreamerV3 stub (needs exploration data)
  static/
    dashboard.html          — Main HUD page
    signal-health.html      — Connection/latency monitor
    signal/camera.html      — Camera signal health

shared/
  protocol.py               — Action enum, Detection, BrainResult dataclasses

scripts/                    — Setup, deploy, and run scripts
docs/                       — Architecture decisions, experiment plan, Pi setup guide
```

## Quick Start

### Prerequisites

- **Mac:** Python 3.10+, conda environment with dependencies
- **Pi:** Raspberry Pi 3/4/5 with camera module, Pi OS, SSH enabled
- **Network:** Mac and Pi on the same LAN

### First-Time Setup (New SD Card)

```bash
# 1. Flash SD card with Pi OS + configure WiFi/SSH/camera
bash scripts/flash-sd.sh

# 2. Set up Mac SSH config + VS Code Remote-SSH
bash scripts/mac-setup.sh

# 3. Install all Pi dependencies
scp scripts/pi-setup.sh pi:~/
ssh pi "bash ~/pi-setup.sh"
```

See [docs/PI_SETUP.md](docs/PI_SETUP.md) for detailed manual steps.

### Install Mac Dependencies

```bash
pip install -r cloud/requirements.txt
```

### Run Everything

The start script launches the brain server, dashboard, and Pi edge stream in one command:

```bash
# Start all components (default: heuristic brain)
bash scripts/start.sh

# Use a different brain
bash scripts/start.sh --brain dreamer

# Mac-only mode (no Pi connected)
bash scripts/start.sh --no-pi
```

This will:

1. Start the brain server with YOLO detection on your Mac
2. Start the dashboard (or skip if the brain server already serves it)
3. Deploy latest code to the Pi and start `edge_stream.py`
4. Print the dashboard URL and WebSocket address
5. Clean up all processes (including Pi) on `Ctrl+C`

Then open the dashboard at `http://localhost:9090`.

### Manual Startup (Per-Terminal)

If you prefer starting each component separately:

```bash
# Terminal 1 — Brain server on Mac
conda run --no-capture-output python cloud/brain_server.py --brain heuristic

# Terminal 2 — Edge stream on Pi
ssh pi "cd ~/cloud-rover && source .venv/bin/activate && python3 pi/edge_stream.py --dashboard ws://<mac-ip>:9091"
```

### Deploy Code to Pi

```bash
# Sync latest code
bash scripts/deploy.sh

# Sync + run camera test
bash scripts/deploy.sh --run
```

## Brains

| Brain | Status | Description |
|-------|--------|-------------|
| `heuristic` | Working | YOLOv8-nano detection + rule-based planner. Steers toward goal objects, avoids obstacles. |
| `openvla` | Stub | Vision-Language-Action model. Requires ~50 human demonstrations to fine-tune. |
| `dreamer` | Stub | DreamerV3 world model. Learns through autonomous exploration. |

All brains implement the `Brain` base class in `cloud/brains/base.py` and return a `BrainResult` (action + detections + reasoning).

## Shared Protocol

Defined in `shared/protocol.py`:

- **`Action`** — Discrete action space: `FORWARD`, `LEFT`, `RIGHT`, `STOP`
- **`Detection`** — Bounding box with label, confidence, and geometry helpers
- **`BrainResult`** — Brain output: chosen action, detections list, reasoning string, inference timing

## Scripts

| Script | Runs On | Purpose |
|--------|---------|---------|
| `scripts/start.sh` | Mac | Start brain + dashboard + Pi in one command |
| `scripts/deploy.sh` | Mac | Sync code to Pi via rsync |
| `scripts/flash-sd.sh` | Mac | Flash + configure SD card |
| `scripts/mac-setup.sh` | Mac | SSH keys, VS Code Remote-SSH |
| `scripts/pi-setup.sh` | Pi | Install all packages + camera config |
| `scripts/check_setup_consistency.py` | Mac | Validate imports and setup scripts stay in sync |

## Docs

- [Architecture Decisions](docs/ARCHITECTURE_DECISIONS.md) — Camera pipeline benchmarks (still vs. video capture)
- [Experiment Plan](docs/EXPERIMENT_PLAN.md) — OpenVLA vs. DreamerV3 comparison plan
- [Pi Setup](docs/PI_SETUP.md) — Detailed Raspberry Pi setup instructions

