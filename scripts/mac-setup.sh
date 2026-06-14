#!/bin/bash
# =============================================================================
# Cloud Rover — Mac Development Setup
#
# Sets up your Mac for developing and deploying to Pi + Desktop GPU.
# Run once after cloning the repo.
#
# Usage:
#   bash scripts/mac-setup.sh [--pi-ip IP] [--desktop-ip IP]
# =============================================================================
set -e

PI_IP=""
PI_USER="viktor"
PI_HOST="pi-brain.local"
DESKTOP_IP=""
DESKTOP_USER=""
DESKTOP_HOST=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --pi-ip) PI_IP="$2"; shift 2;;
        --pi-user) PI_USER="$2"; shift 2;;
        --desktop-ip) DESKTOP_IP="$2"; shift 2;;
        --desktop-user) DESKTOP_USER="$2"; shift 2;;
        *) echo "Unknown option: $1"; exit 1;;
    esac
done

echo "============================================================"
echo "  Cloud Rover — Mac Dev Setup"
echo "============================================================"

# ------------------------------------------------------------------
# 1. SSH key
# ------------------------------------------------------------------
echo "[1/4] Setting up SSH key..."
if [ ! -f ~/.ssh/id_ed25519 ]; then
    ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N "" -C "$(whoami)@mac-to-pi"
    echo "  ✓ SSH key generated"
else
    echo "  ✓ SSH key already exists"
fi

# ------------------------------------------------------------------
# 2. SSH config
# ------------------------------------------------------------------
echo "[2/4] Configuring SSH..."
if ! grep -q "Host pi" ~/.ssh/config 2>/dev/null; then
    cat >> ~/.ssh/config << EOF

# Raspberry Pi - Cloud Rover
Host pi
    HostName ${PI_HOST}
    User ${PI_USER}
    IdentityFile ~/.ssh/id_ed25519
EOF
    echo "  ✓ SSH config added (Host: pi)"
else
    echo "  ✓ SSH config already exists"
fi

# ------------------------------------------------------------------
# 3. Copy SSH key to Pi
# ------------------------------------------------------------------
echo "[3/4] Copying SSH key to Pi..."
TARGET="${PI_IP:-$PI_HOST}"
if ssh -o ConnectTimeout=5 -o BatchMode=yes pi "echo ok" &>/dev/null; then
    echo "  ✓ Passwordless SSH already working"
else
    echo "  Copying key to $TARGET (you'll need to enter the Pi password)..."
    ssh-copy-id -i ~/.ssh/id_ed25519 "${PI_USER}@${TARGET}"
    echo "  ✓ SSH key copied"
fi

# ------------------------------------------------------------------
# 4. Desktop GPU SSH config
# ------------------------------------------------------------------
echo "[4/6] Configuring desktop SSH..."
if [ -n "$DESKTOP_IP" ]; then
    DESKTOP_HOST="$DESKTOP_IP"
    if [ -z "$DESKTOP_USER" ]; then
        read -rp "  Desktop WSL2 username: " DESKTOP_USER
    fi

    if ! grep -q "Host desktop" ~/.ssh/config 2>/dev/null; then
        cat >> ~/.ssh/config << EOF

# Desktop GPU (3070) — Cloud Rover brain
Host desktop
    HostName ${DESKTOP_HOST}
    User ${DESKTOP_USER}
    IdentityFile ~/.ssh/id_ed25519
EOF
        echo "  ✓ SSH config added (Host: desktop → $DESKTOP_HOST)"
    else
        echo "  ✓ Desktop SSH config already exists"
    fi

    # Copy SSH key to desktop
    if ssh -o ConnectTimeout=5 -o BatchMode=yes desktop "echo ok" &>/dev/null; then
        echo "  ✓ Passwordless SSH to desktop already working"
    else
        echo "  Copying key to desktop (you'll need to enter the password)..."
        ssh-copy-id -i ~/.ssh/id_ed25519 "${DESKTOP_USER}@${DESKTOP_HOST}"
        echo "  ✓ SSH key copied to desktop"
    fi
else
    echo "  ⚠ Skipping desktop setup (use --desktop-ip IP to configure)"
fi

# ------------------------------------------------------------------
# 5. VS Code Remote-SSH
# ------------------------------------------------------------------
echo "[5/6] Setting up VS Code..."
CODE_BIN=$(find /Applications -name "code" -path "*/bin/*" 2>/dev/null | head -1)
if [ -n "$CODE_BIN" ]; then
    if ! "$CODE_BIN" --list-extensions 2>/dev/null | grep -q "remote-ssh"; then
        "$CODE_BIN" --install-extension ms-vscode-remote.remote-ssh
        echo "  ✓ Remote-SSH extension installed"
    else
        echo "  ✓ Remote-SSH extension already installed"
    fi
else
    echo "  ⚠ VS Code not found in /Applications. Install Remote-SSH manually."
fi

# ------------------------------------------------------------------
# 6. Verify connectivity
# ------------------------------------------------------------------
echo "[6/6] Testing connections..."
echo -n "  Pi: "
if ssh -o ConnectTimeout=3 -o BatchMode=yes pi "echo ok" 2>/dev/null; then
    echo "  ✓ Pi reachable"
else
    echo "  ⚠ Pi not reachable (may not be powered on)"
fi

if grep -q "Host desktop" ~/.ssh/config 2>/dev/null; then
    echo -n "  Desktop: "
    if ssh -o ConnectTimeout=3 -o BatchMode=yes desktop "echo ok" 2>/dev/null; then
        echo "  ✓ Desktop reachable"
    else
        echo "  ⚠ Desktop not reachable (check WSL2 port forwarding)"
    fi
fi

echo ""
echo "============================================================"
echo "  Mac Setup Complete!"
echo "============================================================"
echo ""
echo "  Connect to Pi:      ssh pi"
if [ -n "$DESKTOP_IP" ]; then
echo "  Connect to Desktop: ssh desktop"
fi
echo "  Deploy to Pi:       bash scripts/deploy.sh"
echo "  Deploy to Desktop:  bash scripts/deploy-desktop.sh"
echo "  Start everything:   bash scripts/start.sh --brain heuristic"
echo ""
echo "============================================================"
