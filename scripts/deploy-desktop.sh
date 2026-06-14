#!/bin/bash
# =============================================================================
# Cloud Rover — Deploy to Desktop GPU (WSL2)
#
# Syncs cloud brain code to the desktop. Run from repo root on Mac.
#
# Usage:
#   bash scripts/deploy-desktop.sh
# =============================================================================
set -e

echo "Deploying to desktop..."

# Sync cloud/ directory (brain server + brains)
rsync -avz --exclude='__pycache__' --exclude='.venv' \
    cloud/ desktop:~/cloud-rover/cloud/

# Sync shared/ directory (protocol definitions)
rsync -avz --exclude='__pycache__' \
    shared/ desktop:~/cloud-rover/shared/

# Sync YOLO model weights if present
if [ -f yolov8n.pt ]; then
    rsync -avz yolov8n.pt desktop:~/cloud-rover/yolov8n.pt
fi

echo "✓ Code deployed to desktop"
