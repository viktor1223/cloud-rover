# Isaac Sim Cloud Setup Guide

Run NVIDIA Isaac Sim on cloud GPUs (RunPod) for simulation and synthetic data
generation — without needing a local high-end GPU.

## Why Cloud?

Your local RTX 3070 (8 GB) is great for the brain server (YOLO + OpenVLA), but
Isaac Sim requires 16+ GB VRAM. Cloud GPUs give you that on-demand for a few
dollars per session, with **automatic shutdown** to prevent runaway costs.

## Cost Estimate

| Usage               | GPU          | Cost/hr | Monthly (10 hrs/wk) |
|---------------------|--------------|---------|----------------------|
| Light sim sessions  | RTX 4090     | ~$0.34  | ~$14               |
| Heavy sim + training| RTX A6000    | ~$0.76  | ~$30               |
| Large-scale training| A100 80GB    | ~$1.39  | ~$56               |

## Prerequisites

1. **RunPod account** — [runpod.io](https://www.runpod.io/)
2. **NVIDIA NGC API key** (free) — [ngc.nvidia.com/setup/api-key](https://ngc.nvidia.com/setup/api-key)
3. **runpodctl CLI** (optional) — for scripted pod management

## Quick Start

### 1. Deploy a GPU Pod on RunPod

1. Go to [runpod.io/console/pods](https://www.runpod.io/console/pods)
2. Click **Deploy**
3. Select GPU: **RTX 4090** (24 GB, cheapest) or **RTX A6000** (48 GB, more headroom)
4. Template: **RunPod PyTorch 2.x** (has Docker + NVIDIA runtime)
5. Set volume: **50 GB** (for Isaac Sim container image + data)
6. Deploy and wait for it to start (~1-2 min)

### 2. SSH Into Your Pod

RunPod gives you an SSH command. Use it:

`ash
ssh root@<pod-ip> -p <port> -i ~/.ssh/id_ed25519
`

### 3. Clone and Run Setup

`ash
git clone https://github.com/viktor1223/cloud-rover.git ~/cloud-rover
cd ~/cloud-rover

# Set your NGC key (or it will prompt you)
export NGC_API_KEY="your-key-here"

# Run with 2-hour auto-shutdown (default)
bash scripts/cloud-sim-setup.sh

# Or with streaming GUI in your browser
bash scripts/cloud-sim-setup.sh --stream

# Or with custom timeout
bash scripts/cloud-sim-setup.sh --timeout 4h
`

### 4. Use Isaac Sim

`ash
# Run a simulation script
docker exec cloud-rover-sim ./python.sh /workspace/sim/my_scene.py

# Interactive Python shell inside Isaac Sim
docker exec -it cloud-rover-sim ./python.sh

# Check status
bash scripts/cloud-sim-status.sh
`

### 5. When You're Done

`ash
# Stop everything (container + timer)
bash scripts/cloud-sim-stop.sh

# Then stop your pod on RunPod dashboard (or it auto-stops on timeout)
`

## Cost Protection

**Every session has a 2-hour auto-shutdown by default.** When time is up:
1. Isaac Sim container stops
2. RunPod pod stops (if runpodctl is available)
3. System shuts down as a fallback

### Managing the Timer

`ash
# Check how long you have left
bash scripts/cloud-sim-status.sh

# Need more time? Extend by 1 hour
bash scripts/cloud-sim-extend.sh 1h

# Done early? Stop now
bash scripts/cloud-sim-stop.sh

# Living dangerously (NOT recommended)
bash scripts/cloud-sim-setup.sh --no-timeout
`

### Additional Protection Tips

- **Set a RunPod spend limit** in Account > Billing > Spend Limit
- **Use spot/interruptible instances** when possible (cheaper, auto-stops)
- **Check your RunPod dashboard** after each session to confirm pod stopped

## Scripts Reference

| Script                          | Purpose                              |
|---------------------------------|--------------------------------------|
| scripts/cloud-sim-setup.sh   | Deploy + launch Isaac Sim on the pod |
| scripts/cloud-sim-stop.sh    | Stop container + cancel timer        |
| scripts/cloud-sim-extend.sh  | Add more time to the shutdown timer  |
| scripts/cloud-sim-status.sh  | Check container + GPU + timer status |

## Architecture (Cloud Sim Integration)

`
|Local (Dell Desktop WSL2)|            |Cloud (RunPod GPU Pod)|
|                         |            |                      |
| Brain Server            |  SSH/sync  | Isaac Sim (Docker)   |
|  - YOLO detection       |<---------->|  - Physics sim       |
|  - OpenVLA inference    |            |  - Synthetic camera  |
|  - Dashboard            |            |  - Training data gen |
|                         |            |  - Domain randomize  |
|                         |            |                      |
`

**Workflow:**
1. Design rover sim environment in Isaac Sim (streaming mode)
2. Generate synthetic training data (headless batch mode)
3. Download datasets to local machine
4. Train/fine-tune models locally on RTX 3070
5. Deploy to real rover

## Links and Resources

### Accounts & Setup
- [RunPod - Sign Up](https://www.runpod.io/)
- [NVIDIA NGC - API Key](https://ngc.nvidia.com/setup/api-key)
- [RunPod CLI (runpodctl)](https://github.com/runpod/runpodctl)

### Isaac Sim Documentation
- [Isaac Sim Overview](https://developer.nvidia.com/isaac-sim)
- [Isaac Sim Container on NGC](https://catalog.ngc.nvidia.com/orgs/nvidia/containers/isaac-sim)
- [Isaac Sim Documentation](https://docs.isaacsim.omniverse.nvidia.com/latest/)
- [Headless Mode Guide](https://docs.isaacsim.omniverse.nvidia.com/latest/advanced_topics/headless.html)
- [Isaac Sim Python API](https://docs.isaacsim.omniverse.nvidia.com/latest/python_api/index.html)

### Isaac Lab (Reinforcement Learning)
- [Isaac Lab Documentation](https://isaac-sim.github.io/IsaacLab/)
- [Isaac Lab GitHub](https://github.com/isaac-sim/IsaacLab)
- [RL Training Examples](https://isaac-sim.github.io/IsaacLab/main/source/tutorials/index.html)

### Robotics Sim Tutorials
- [Isaac Sim + ROS2 Integration](https://docs.isaacsim.omniverse.nvidia.com/latest/ros2_tutorials/index.html)
- [Creating Custom Robots](https://docs.isaacsim.omniverse.nvidia.com/latest/gui_tutorials/tutorial_gui_simple_robot.html)
- [Synthetic Data Generation](https://docs.isaacsim.omniverse.nvidia.com/latest/replicator_tutorials/index.html)
- [Domain Randomization](https://docs.isaacsim.omniverse.nvidia.com/latest/replicator_tutorials/tutorial_replicator_randomizer.html)

### Cloud GPU Providers (Alternatives to RunPod)
- [Vast.ai](https://vast.ai/) — Marketplace, often cheapest
- [Lambda Labs](https://lambdalabs.com/service/gpu-cloud) — Premium, reliable
- [Google Colab Pro](https://colab.research.google.com/) — Cheap but limited

### Related Projects & Inspiration
- [NVIDIA Jetson for Edge AI](https://developer.nvidia.com/embedded-computing)
- [OpenVLA (Vision-Language-Action)](https://openvla.github.io/)
- [DreamerV3 (World Models)](https://danijar.com/project/dreamerv3/)
