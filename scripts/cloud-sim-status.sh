#!/bin/bash
# =============================================================================
# Cloud Rover - Check Isaac Sim and timer status
# =============================================================================
echo "=== Isaac Sim ==="
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q cloud-rover-sim; then
    echo "  Container: RUNNING"
    docker ps --filter name=cloud-rover-sim --format "  Uptime: {{.RunningFor}}"
else
    echo "  Container: STOPPED"
fi

echo ""
echo "=== GPU ==="
nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu \
    --format=csv,noheader 2>/dev/null || echo "  unavailable"

echo ""
echo "=== Cost Guard ==="
if [ -f /tmp/cloud-rover-shutdown.pid ]; then
    PID=$(cat /tmp/cloud-rover-shutdown.pid)
    if kill -0 $PID 2>/dev/null; then
        START=$(stat -c %Y /tmp/cloud-rover-shutdown.pid 2>/dev/null || echo 0)
        NOW=$(date +%s)
        ELAPSED=$(( (NOW - START) / 60 ))
        echo "  Timer: ACTIVE (${ELAPSED}m elapsed, PID $PID)"
        echo "  Extend: bash scripts/cloud-sim-extend.sh 1h"
    else
        echo "  Timer: EXPIRED"
    fi
else
    echo "  Timer: NOT SET (no cost protection!)"
fi
