#!/bin/bash
# =============================================================================
# Cloud Rover - Isaac Sim Cloud Setup (RunPod)
#
# Deploys NVIDIA Isaac Sim on a RunPod GPU pod for headless simulation
# and synthetic data generation. Includes AUTO-SHUTDOWN to prevent runaway costs.
#
# Prerequisites:
#   - RunPod account with a deployed GPU pod (RTX 4090 / A6000 / A100)
#   - NVIDIA NGC API key (free at https://ngc.nvidia.com)
#   - This repo cloned on the pod
#
# Usage (inside RunPod pod):
#   git clone https://github.com/viktor1223/cloud-rover.git ~/cloud-rover
#   cd ~/cloud-rover
#   bash scripts/cloud-sim-setup.sh
#
# Streaming (GUI in browser):
#   bash scripts/cloud-sim-setup.sh --stream
#
# Custom timeout (default 2 hours):
#   bash scripts/cloud-sim-setup.sh --timeout 4h
#
# Disable timeout (DANGEROUS - remember to stop manually!):
#   bash scripts/cloud-sim-setup.sh --no-timeout
# =============================================================================
set -e

ISAAC_SIM_VERSION="2026.1.0"
WORKSPACE="$HOME/cloud-rover"
MODE="headless"
TIMEOUT="2h"  # DEFAULT: auto-shutdown after 2 hours to prevent runaway costs

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --stream) MODE="stream"; shift ;;
        --version) ISAAC_SIM_VERSION="$2"; shift 2 ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        --no-timeout) TIMEOUT=""; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "============================================================"
echo "  Cloud Rover - Isaac Sim Cloud Setup"
echo "============================================================"
echo "  Isaac Sim:     $ISAAC_SIM_VERSION"
echo "  Mode:          $MODE"
echo "  Auto-shutdown: ${TIMEOUT:-DISABLED (be careful!)}"
echo "  Workspace:     $WORKSPACE"
echo "============================================================"
echo ""

# ------------------------------------------------------------------
# COST PROTECTION: Schedule auto-shutdown
# ------------------------------------------------------------------
if [ -n "$TIMEOUT" ]; then
    echo "[COST GUARD] Scheduling auto-shutdown in $TIMEOUT"
    echo "  To cancel:  bash scripts/cloud-sim-stop.sh"
    echo "  To extend:  bash scripts/cloud-sim-extend.sh 1h"
    echo ""

    # Kill any existing shutdown timer
    if [ -f /tmp/cloud-rover-shutdown.pid ]; then
        kill $(cat /tmp/cloud-rover-shutdown.pid) 2>/dev/null || true
    fi

    # Start shutdown timer in background
    (
        SECONDS_LEFT=0
        if [[ "$TIMEOUT" == *h ]]; then
            SECONDS_LEFT=$(( ${TIMEOUT%h} * 3600 ))
        elif [[ "$TIMEOUT" == *m ]]; then
            SECONDS_LEFT=$(( ${TIMEOUT%m} * 60 ))
        else
            SECONDS_LEFT=$TIMEOUT
        fi

        sleep $SECONDS_LEFT

        echo ""
        echo "============================================================"
        echo "  [COST GUARD] TIME IS UP ($TIMEOUT elapsed)"
        echo "  Shutting down Isaac Sim and stopping the pod..."
        echo "============================================================"

        docker stop cloud-rover-sim 2>/dev/null || true

        if [ -n "$RUNPOD_POD_ID" ]; then
            echo "  Stopping RunPod pod $RUNPOD_POD_ID..."
            runpodctl stop pod $RUNPOD_POD_ID 2>/dev/null || true
        fi

        sudo shutdown now 2>/dev/null || true
    ) &
    echo $! > /tmp/cloud-rover-shutdown.pid
    echo "  Timer PID: $(cat /tmp/cloud-rover-shutdown.pid)"
    echo ""
fi

# ------------------------------------------------------------------
# 1. Verify GPU access
# ------------------------------------------------------------------
echo "[1/5] Checking GPU access..."
if ! command -v nvidia-smi &>/dev/null; then
    echo "  ERROR: nvidia-smi not found. Deploy a GPU pod."
    exit 1
fi

GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
GPU_VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -1)
echo "  GPU: $GPU_NAME ($GPU_VRAM)"

VRAM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
if [ "$VRAM_MB" -lt 16000 ]; then
    echo "  ERROR: Isaac Sim needs 16+ GB VRAM. You have ${VRAM_MB} MB."
    exit 1
fi

# ------------------------------------------------------------------
# 2. NGC Login
# ------------------------------------------------------------------
echo "[2/5] Logging into NVIDIA NGC..."
if [ -z "$NGC_API_KEY" ]; then
    echo "  NGC_API_KEY not set."
    echo "  Get one free at: https://ngc.nvidia.com/setup/api-key"
    read -p "  Enter NGC API key: " NGC_API_KEY
fi
echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin
echo "  Logged into NGC"

# ------------------------------------------------------------------
# 3. Pull Isaac Sim container
# ------------------------------------------------------------------
echo "[3/5] Pulling Isaac Sim (10-20 min first time)..."
docker pull "nvcr.io/nvidia/isaac-sim:${ISAAC_SIM_VERSION}"
echo "  Isaac Sim ${ISAAC_SIM_VERSION} ready"

# ------------------------------------------------------------------
# 4. Workspace directories
# ------------------------------------------------------------------
echo "[4/5] Setting up workspace..."
mkdir -p "$WORKSPACE/sim/environments"
mkdir -p "$WORKSPACE/sim/datasets"
mkdir -p "$WORKSPACE/sim/checkpoints"
mkdir -p "$WORKSPACE/sim/logs"
echo "  Directories created"

# ------------------------------------------------------------------
# 5. Launch Isaac Sim
# ------------------------------------------------------------------
echo "[5/5] Launching Isaac Sim ($MODE)..."

if [ "$MODE" = "stream" ]; then
    echo "  WebRTC streaming enabled"
    echo "  Open: http://<your-pod-ip>:3000"
    docker run --gpus all --rm -it \
        --shm-size=16g \
        -e ACCEPT_EULA=Y \
        -e NVIDIA_DRIVER_CAPABILITIES=all \
        -v "$WORKSPACE:/workspace" \
        --name cloud-rover-sim \
        -p 3000:3000 -p 8080:8080 -p 8899:8899 \
        "nvcr.io/nvidia/isaac-sim:${ISAAC_SIM_VERSION}"
else
    echo "  Headless mode (script-driven)"
    docker run --gpus all --rm -d \
        --shm-size=16g \
        -e ACCEPT_EULA=Y \
        -e NVIDIA_DRIVER_CAPABILITIES=all \
        -v "$WORKSPACE:/workspace" \
        --name cloud-rover-sim \
        "nvcr.io/nvidia/isaac-sim:${ISAAC_SIM_VERSION}" \
        bash -c "sleep infinity"
    echo "  Isaac Sim running (container: cloud-rover-sim)"
fi

echo ""
echo "============================================================"
echo "  Isaac Sim is ready!"
echo "  Auto-shutdown in: ${TIMEOUT:-DISABLED}"
echo "============================================================"
echo "  docker exec cloud-rover-sim ./python.sh /workspace/sim/script.py"
echo "  bash scripts/cloud-sim-status.sh"
echo "  bash scripts/cloud-sim-extend.sh 1h"
echo "  bash scripts/cloud-sim-stop.sh"
echo "============================================================"
