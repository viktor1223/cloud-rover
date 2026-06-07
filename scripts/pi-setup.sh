#!/bin/bash
# =============================================================================
# Cloud Rover — Raspberry Pi Setup Script
#
# Automated setup for a fresh Raspberry Pi OS (64-bit Trixie) install.
# Installs all system packages, configures camera, and clones the repo.
#
# Usage:
#   bash pi-setup.sh
#
# Prerequisites:
#   - Raspberry Pi OS Desktop 64-bit (Debian 13 Trixie)
#   - Internet connection
#   - ArduCam IMX708 camera connected via CSI
# =============================================================================
set -e

REPO_URL="https://github.com/viktor1223/cloud-rover.git"
REPO_DIR="$HOME/cloud-rover"

echo "============================================================"
echo "  Cloud Rover — Pi Setup"
echo "============================================================"
echo ""

# ------------------------------------------------------------------
# 1. Fix common first-boot issues
# ------------------------------------------------------------------
echo "[1/7] Fixing first-boot issues..."
sudo chown -R "$(whoami):$(whoami)" "$HOME"
if ! grep -q "pi-brain" /etc/hosts 2>/dev/null; then
    sudo sh -c 'echo "127.0.1.1 pi-brain" >> /etc/hosts'
fi
echo "  ✓ Home directory ownership and hostname fixed"

# ------------------------------------------------------------------
# 2. System update
# ------------------------------------------------------------------
echo "[2/7] Updating system packages..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
echo "  ✓ System updated"

# ------------------------------------------------------------------
# 3. Install required packages
# ------------------------------------------------------------------
echo "[3/7] Installing system packages..."
sudo apt-get install -y -qq \
    git \
    curl \
    python3-pip \
    python3-venv \
    python3-gpiozero \
    python3-pigpio \
    python3-picamera2 \
    python3-requests \
    python3-pil \
    python3-libcamera \
    i2c-tools \
    rpicam-apps
echo "  ✓ System packages installed"

# ------------------------------------------------------------------
# 4. Install GitHub CLI
# ------------------------------------------------------------------
echo "[4/7] Installing GitHub CLI..."
if ! command -v gh &>/dev/null; then
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg 2>/dev/null
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
    sudo apt-get update -qq
    sudo apt-get install -y -qq gh
    echo "  ✓ GitHub CLI installed"
else
    echo "  ✓ GitHub CLI already installed ($(gh --version | head -1))"
fi

# ------------------------------------------------------------------
# 5. Configure ArduCam IMX708 camera
# ------------------------------------------------------------------
echo "[5/7] Configuring ArduCam IMX708 camera..."
CONFIG="/boot/firmware/config.txt"
NEEDS_REBOOT=false

if grep -q "camera_auto_detect=1" "$CONFIG" 2>/dev/null; then
    sudo sed -i 's/camera_auto_detect=1/camera_auto_detect=0/' "$CONFIG"
    NEEDS_REBOOT=true
    echo "  ✓ Disabled camera_auto_detect"
fi

if ! grep -q "dtoverlay=imx708" "$CONFIG" 2>/dev/null; then
    echo "dtoverlay=imx708" | sudo tee -a "$CONFIG" > /dev/null
    NEEDS_REBOOT=true
    echo "  ✓ Added dtoverlay=imx708"
fi

if [ "$NEEDS_REBOOT" = false ]; then
    echo "  ✓ Camera already configured"
fi

# ------------------------------------------------------------------
# 6. Clone repository
# ------------------------------------------------------------------
echo "[6/7] Setting up repository..."
if [ -d "$REPO_DIR" ]; then
    echo "  ✓ Repository already exists at $REPO_DIR"
    cd "$REPO_DIR" && git pull --ff-only 2>/dev/null || true
else
    if command -v gh &>/dev/null && gh auth status &>/dev/null 2>&1; then
        gh repo clone viktor1223/cloud-rover "$REPO_DIR"
        echo "  ✓ Repository cloned via GitHub CLI"
    else
        echo "  ⚠ GitHub CLI not authenticated. Clone manually after running:"
        echo "    gh auth login"
        echo "    gh repo clone viktor1223/cloud-rover ~/cloud-rover"
    fi
fi

# ------------------------------------------------------------------
# 7. Print summary
# ------------------------------------------------------------------
echo ""
echo "============================================================"
echo "  Setup Complete!"
echo "============================================================"
echo ""
echo "  Installed versions:"
echo "    Python:     $(python3 --version 2>&1 | cut -d' ' -f2)"
echo "    Git:        $(git --version | cut -d' ' -f3)"
echo "    GitHub CLI: $(gh --version 2>/dev/null | head -1 | cut -d' ' -f3 || echo 'not installed')"
echo "    picamera2:  $(python3 -c 'import picamera2; print(picamera2.__version__)' 2>/dev/null || echo 'installed')"
echo "    gpiozero:   $(python3 -c 'import gpiozero; print(gpiozero.__version__)' 2>/dev/null || echo 'installed')"
echo ""

if [ "$NEEDS_REBOOT" = true ]; then
    echo "  ⚠  REBOOT REQUIRED for camera changes!"
    echo "     Run: sudo reboot"
    echo ""
fi

echo "  Next steps:"
echo "    1. Reboot if prompted above"
echo "    2. Authenticate GitHub: gh auth login"
echo "    3. Test camera: rpicam-hello --list-cameras"
echo "    4. Test capture: python3 ~/cloud-rover/pi/camera_test.py"
echo ""
echo "============================================================"
