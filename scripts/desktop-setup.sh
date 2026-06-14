#!/bin/bash
# =============================================================================
# Cloud Rover — Desktop GPU Setup (Windows + WSL2)
#
# Run this INSIDE WSL2 (Ubuntu) on the Windows desktop with the 3070.
# Sets up Python 3.11, PyTorch 2.4.1 + CUDA 12.4, and downloads OpenVLA.
#
# Stack:
#   OS:         Ubuntu 22.04+ on WSL2
#   Python:     3.11
#   Env:        venv (no conda)
#   PyTorch:    2.4.1 + CUDA 12.4 (via pip wheel — no system CUDA needed)
#   Model:      openvla/openvla-7b loaded in 4-bit NF4 (~5 GB VRAM)
#   GPU:        RTX 3070 (8 GB, compute capability 8.6)
#
# Prerequisites:
#   - Windows 11 with WSL2 (wsl --install)
#   - NVIDIA GPU drivers installed on Windows (not inside WSL)
#   - nvidia-smi works inside WSL2
#
# Usage (inside WSL2):
#   git clone https://github.com/viktor1223/cloud-rover.git ~/cloud-rover
#   cd ~/cloud-rover
#   bash scripts/desktop-setup.sh
# =============================================================================
set -e

PYTHON_VERSION="3.11"
PYTORCH_VERSION="2.4.1"
TORCHVISION_VERSION="0.19.1"
CUDA_TAG="cu124"
REPO_DIR="$HOME/cloud-rover"

echo "============================================================"
echo "  Cloud Rover — Desktop GPU Setup (WSL2)"
echo "============================================================"
echo "  Python:   $PYTHON_VERSION"
echo "  PyTorch:  $PYTORCH_VERSION + $CUDA_TAG"
echo "  Model:    openvla/openvla-7b (4-bit NF4)"
echo "============================================================"
echo ""

# ------------------------------------------------------------------
# 1. Verify GPU access
# ------------------------------------------------------------------
echo "[1/7] Checking GPU access..."
if ! command -v nvidia-smi &>/dev/null; then
    echo "  ✗ nvidia-smi not found."
    echo "    Install NVIDIA GPU drivers on Windows (not inside WSL)."
    echo "    Then restart WSL: wsl --shutdown && wsl"
    exit 1
fi

GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
GPU_VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -1)
DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
echo "  ✓ GPU:    $GPU_NAME ($GPU_VRAM)"
echo "  ✓ Driver: $DRIVER_VERSION"

# ------------------------------------------------------------------
# 2. System packages + Python 3.11
# ------------------------------------------------------------------
echo "[2/7] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    software-properties-common git curl openssh-server

# Ensure Python 3.11 is available
if ! command -v "python${PYTHON_VERSION}" &>/dev/null; then
    echo "  Installing Python ${PYTHON_VERSION}..."
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get update -qq
    sudo apt-get install -y -qq \
        "python${PYTHON_VERSION}" \
        "python${PYTHON_VERSION}-venv" \
        "python${PYTHON_VERSION}-dev"
    echo "  ✓ Python ${PYTHON_VERSION} installed"
else
    echo "  ✓ Python ${PYTHON_VERSION} already installed"
fi

"python${PYTHON_VERSION}" --version

# ------------------------------------------------------------------
# 3. Enable SSH server (so Mac can connect)
# ------------------------------------------------------------------
echo "[3/7] Configuring SSH server..."
if ! systemctl is-active --quiet ssh 2>/dev/null; then
    sudo systemctl enable ssh
    sudo systemctl start ssh
    echo "  ✓ SSH server started"
else
    echo "  ✓ SSH server already running"
fi

DESKTOP_IP=$(hostname -I | awk '{print $1}')
echo "  Desktop WSL2 IP: $DESKTOP_IP"
echo ""
echo "  ⚠  IMPORTANT: WSL2 uses a virtual network. To SSH from your Mac,"
echo "     you need to forward ports on Windows. Run this in PowerShell (Admin):"
echo ""
echo "     # SSH access"
echo "     netsh interface portproxy add v4tov4 listenport=22 listenaddress=0.0.0.0 connectport=22 connectaddress=$DESKTOP_IP"
echo "     netsh advfirewall firewall add rule name=\"WSL2 SSH\" dir=in action=allow protocol=tcp localport=22"
echo ""
echo "     # Brain server ports"
echo "     netsh interface portproxy add v4tov4 listenport=9090 listenaddress=0.0.0.0 connectport=9090 connectaddress=$DESKTOP_IP"
echo "     netsh interface portproxy add v4tov4 listenport=9091 listenaddress=0.0.0.0 connectport=9091 connectaddress=$DESKTOP_IP"
echo "     netsh advfirewall firewall add rule name=\"Cloud Rover Brain\" dir=in action=allow protocol=tcp localport=9090,9091"
echo ""
echo "     Then from Mac: ssh <wsl-username>@<windows-lan-ip>"
echo ""

# ------------------------------------------------------------------
# 4. Python venv
# ------------------------------------------------------------------
echo "[4/7] Setting up Python ${PYTHON_VERSION} venv..."
cd "$REPO_DIR" 2>/dev/null || { echo "  ✗ $REPO_DIR not found. Clone the repo first."; exit 1; }

if [ ! -d .venv ]; then
    "python${PYTHON_VERSION}" -m venv .venv
    echo "  ✓ venv created with Python ${PYTHON_VERSION}"
else
    echo "  ✓ venv already exists"
fi

source .venv/bin/activate
pip install --upgrade pip -q

# ------------------------------------------------------------------
# 5. PyTorch + CUDA
# ------------------------------------------------------------------
echo "[5/7] Installing PyTorch ${PYTORCH_VERSION} + CUDA ${CUDA_TAG}..."
pip install \
    "torch==${PYTORCH_VERSION}" \
    "torchvision==${TORCHVISION_VERSION}" \
    --index-url "https://download.pytorch.org/whl/${CUDA_TAG}" -q

# Verify CUDA works
python3 -c "
import torch
assert torch.cuda.is_available(), 'CUDA not available in PyTorch!'
print(f'  ✓ PyTorch {torch.__version__} + CUDA {torch.version.cuda}')
print(f'  ✓ GPU: {torch.cuda.get_device_name(0)}')
vram = torch.cuda.get_device_properties(0).total_mem / 1e9
print(f'  ✓ VRAM: {vram:.1f} GB')
assert vram >= 7, f'Need >=8 GB VRAM, got {vram:.1f} GB'
"

# ------------------------------------------------------------------
# 6. Project dependencies
# ------------------------------------------------------------------
echo "[6/7] Installing project dependencies..."
pip install -r cloud/requirements.txt -q

# Quick sanity check
python3 -c "
import transformers, accelerate, bitsandbytes
print(f'  ✓ transformers {transformers.__version__}')
print(f'  ✓ accelerate {accelerate.__version__}')
print(f'  ✓ bitsandbytes {bitsandbytes.__version__}')
"

# ------------------------------------------------------------------
# 7. Download OpenVLA model weights
# ------------------------------------------------------------------
echo "[7/7] Downloading OpenVLA model weights (~14 GB, one-time)..."
echo "  Model will be cached at ~/.cache/huggingface/hub/"
python3 -c "
from transformers import AutoProcessor, AutoModelForVision2Seq, BitsAndBytesConfig
import torch

model_id = 'openvla/openvla-7b'

print('  Downloading processor...')
AutoProcessor.from_pretrained(model_id, trust_remote_code=True)

print('  Downloading model in 4-bit NF4 (this takes a while)...')
quant_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_quant_type='nf4',
)
model = AutoModelForVision2Seq.from_pretrained(
    model_id,
    quantization_config=quant_config,
    device_map='auto',
    low_cpu_mem_usage=True,
    trust_remote_code=True,
)
vram_used = torch.cuda.memory_allocated() / 1e9
print(f'  ✓ Model loaded — {vram_used:.1f} GB VRAM used')
del model
torch.cuda.empty_cache()
print('  ✓ Weights cached at ~/.cache/huggingface/hub/')
"

echo ""
echo "============================================================"
echo "  ✓ Desktop GPU setup complete!"
echo "============================================================"
echo "  GPU:      $GPU_NAME ($GPU_VRAM)"
echo "  Driver:   $DRIVER_VERSION"
echo "  Python:   ${PYTHON_VERSION} in $REPO_DIR/.venv"
echo "  PyTorch:  ${PYTORCH_VERSION} + CUDA ${CUDA_TAG}"
echo "  Model:    OpenVLA-7B (4-bit NF4)"
echo ""
echo "  Next steps:"
echo "    1. Forward ports in PowerShell (see instructions above)"
echo "    2. On your Mac: bash scripts/mac-setup.sh --desktop-ip <WINDOWS_LAN_IP>"
echo "    3. Test: bash scripts/start.sh --brain openvla"
echo "============================================================"
