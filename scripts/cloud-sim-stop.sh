#!/bin/bash
# =============================================================================
# Cloud Rover - Stop Isaac Sim and cancel shutdown timer
# =============================================================================
echo "Stopping Isaac Sim..."
docker stop cloud-rover-sim 2>/dev/null || echo "  (not running)"

echo "Cancelling shutdown timer..."
if [ -f /tmp/cloud-rover-shutdown.pid ]; then
    kill $(cat /tmp/cloud-rover-shutdown.pid) 2>/dev/null || true
    rm -f /tmp/cloud-rover-shutdown.pid
    echo "  Timer cancelled"
else
    echo "  (no timer found)"
fi

echo ""
echo "All stopped. Pod is still running - stop it at runpod.io"
echo "or: runpodctl stop pod $RUNPOD_POD_ID"
