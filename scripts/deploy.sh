#!/bin/bash
# =============================================================================
# Cloud Rover — Deploy to Pi
#
# Syncs local code to the Pi. Run from repo root on Mac.
#
# Usage:
#   bash scripts/deploy.sh           # sync all Pi code
#   bash scripts/deploy.sh --run     # sync and run camera test
# =============================================================================
set -e

RUN_AFTER=false
if [ "$1" = "--run" ]; then
    RUN_AFTER=true
fi

echo "Deploying to Pi..."

# Sync pi/ directory
rsync -avz --exclude='__pycache__' --exclude='.venv' --exclude='data/' \
    pi/ pi:~/cloud-rover/pi/

# Sync shared/ directory
rsync -avz --exclude='__pycache__' \
    shared/ pi:~/cloud-rover/shared/ 2>/dev/null || true

echo "✓ Code deployed to Pi"

if [ "$RUN_AFTER" = true ]; then
    echo ""
    echo "Running camera test..."
    ssh pi "cd ~/cloud-rover && python3 pi/camera_test.py"
fi
