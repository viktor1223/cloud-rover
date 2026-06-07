# Cloud Rover

A vision-based rover platform using Raspberry Pi as the edge controller and cloud-hosted AI as the brain.

## Architecture

```
┌─────────────────┐          ┌──────────────────────┐
│   Raspberry Pi  │  API     │     Cloud Brain      │
│   (Edge Body)   │ ◄──────► │  (Vision + Planning) │
├─────────────────┤          ├──────────────────────┤
│ • Camera capture│          │ • VLA inference      │
│ • Motor control │          │ • Object detection   │
│ • Sensor reading│          │ • Path planning      │
│ • GPIO/I2C      │          │ • World model        │
└─────────────────┘          └──────────────────────┘
```

## Project Structure

```
pi/           — Code that runs on the Raspberry Pi (edge)
cloud/        — Cloud brain services (inference, planning)
shared/       — Shared protocols, message schemas
scripts/      — Setup, deployment, utilities
docs/         — Documentation and architecture decisions
```

## Getting Started

### From Scratch (new SD card)

```bash
# 1. Flash SD card with Pi OS + configure WiFi/SSH/camera
bash scripts/flash-sd.sh

# 2. Boot Pi, then set up Mac SSH + VS Code
bash scripts/mac-setup.sh

# 3. SSH in and install all Pi dependencies
scp scripts/pi-setup.sh pi:~/
ssh pi "bash ~/pi-setup.sh"
```

See [docs/PI_SETUP.md](docs/PI_SETUP.md) for detailed manual instructions.

### Day-to-Day Workflow

```bash
# Edit code on Mac, deploy to Pi
bash scripts/deploy.sh

# Or deploy and immediately test camera
bash scripts/deploy.sh --run

# Start mock cloud brain on Mac, stream from Pi
python3 cloud/mock_brain.py                              # Terminal 1 (Mac)
ssh pi "cd ~/cloud-rover && python3 pi/camera_to_cloud.py"  # Terminal 2
```

### Scripts

| Script | Where | What |
|--------|-------|------|
| `scripts/flash-sd.sh` | Mac | Flash + configure SD card |
| `scripts/mac-setup.sh` | Mac | SSH keys, VS Code Remote-SSH |
| `scripts/pi-setup.sh` | Pi | Install all packages + camera config |
| `scripts/deploy.sh` | Mac | Sync code to Pi via rsync |

