#!/bin/bash
# =============================================================================
# Cloud Rover - Extend auto-shutdown timer
# Usage: bash scripts/cloud-sim-extend.sh 1h
# =============================================================================
EXTRA="${1:-1h}"

if [ -z "$1" ]; then
    echo "Usage: bash scripts/cloud-sim-extend.sh <time>"
    echo "  Examples: 1h, 2h, 30m"
    exit 1
fi

echo "Cancelling current timer..."
if [ -f /tmp/cloud-rover-shutdown.pid ]; then
    kill $(cat /tmp/cloud-rover-shutdown.pid) 2>/dev/null || true
fi

echo "New shutdown in $EXTRA from now..."
(
    SECONDS_LEFT=0
    if [[ "$EXTRA" == *h ]]; then
        SECONDS_LEFT=$(( ${EXTRA%h} * 3600 ))
    elif [[ "$EXTRA" == *m ]]; then
        SECONDS_LEFT=$(( ${EXTRA%m} * 60 ))
    fi
    sleep $SECONDS_LEFT
    echo "[COST GUARD] Extended time up. Shutting down..."
    docker stop cloud-rover-sim 2>/dev/null || true
    [ -n "$RUNPOD_POD_ID" ] && runpodctl stop pod $RUNPOD_POD_ID 2>/dev/null
    sudo shutdown now 2>/dev/null || true
) &
echo $! > /tmp/cloud-rover-shutdown.pid
echo "  Timer set. Pod shuts down in $EXTRA"
