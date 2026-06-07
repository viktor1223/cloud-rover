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

### Pi Setup
```bash
ssh pi
cd ~/cloud-rover
python3 -m venv .venv
source .venv/bin/activate
pip install -r pi/requirements.txt
```

### Dev Workflow
- Develop on Mac (VS Code Remote-SSH or local)
- Push to GitHub
- Pull on Pi: `git pull && source .venv/bin/activate && python3 pi/main.py`

