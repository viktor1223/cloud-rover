#!/bin/bash
# =============================================================================
# Cloud Rover — Start All Components
#
# Launches the brain server + dashboard on Mac, and edge_stream on Pi.
# Run from repo root on Mac.
#
# Usage:
#   bash scripts/start.sh                    # defaults: heuristic brain
#   bash scripts/start.sh --brain dreamer    # choose brain
#   bash scripts/start.sh --no-pi            # skip Pi (local dev only)
# =============================================================================
set -e

BRAIN="heuristic"
SKIP_PI=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --brain)
            BRAIN="$2"
            shift 2
            ;;
        --no-pi)
            SKIP_PI=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: bash scripts/start.sh [--brain heuristic|openvla|dreamer] [--no-pi]"
            exit 1
            ;;
    esac
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Get Mac's LAN IP for the Pi to connect to
MAC_IP=$(python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(('8.8.8.8', 80))
print(s.getsockname()[0])
s.close()
" 2>/dev/null || echo "127.0.0.1")

echo "========================================="
echo "  Cloud Rover — Starting All Components"
echo "========================================="
echo "  Brain:   $BRAIN"
echo "  Mac IP:  $MAC_IP"
echo "  Skip Pi: $SKIP_PI"
echo "========================================="
echo ""

# --- Cleanup on exit ---
PIDS=()
cleanup() {
    echo ""
    echo "Shutting down..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null
    done
    if [ "$SKIP_PI" = false ]; then
        ssh pi "pkill -f 'python.*edge_stream' 2>/dev/null" || true
    fi
    wait 2>/dev/null
    echo "All components stopped."
}
trap cleanup EXIT INT TERM

# --- 1. Start Brain Server (Mac) ---
echo "[1/3] Starting brain server (--brain $BRAIN)..."
conda run --no-capture-output python cloud/brain_server.py --brain "$BRAIN" &
PIDS+=($!)
sleep 2

# --- 2. Start Dashboard (Mac) ---
# Only needed if dashboard.py is separate from brain_server.
# Check if brain_server already serves the dashboard on :9090.
# If brain_server handles both, skip this step.
if lsof -i :9090 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "[2/3] Dashboard already served by brain server on :9090 — skipping."
else
    echo "[2/3] Starting dashboard..."
    conda run --no-capture-output python cloud/dashboard.py &
    PIDS+=($!)
    sleep 1
fi

# --- 3. Start Pi edge_stream ---
if [ "$SKIP_PI" = false ]; then
    echo "[3/3] Starting edge_stream on Pi → ws://$MAC_IP:9091 ..."
    # Deploy latest code first
    bash scripts/deploy.sh
    ssh pi "cd ~/cloud-rover && source .venv/bin/activate && python3 pi/edge_stream.py --dashboard ws://$MAC_IP:9091" &
    PIDS+=($!)
else
    echo "[3/3] Skipping Pi (--no-pi)."
fi

echo ""
echo "========================================="
echo "  All components running!"
echo "  Dashboard: http://$MAC_IP:9090"
echo "  Brain WS:  ws://$MAC_IP:9091"
echo "  Press Ctrl+C to stop everything."
echo "========================================="

# Wait for all background processes
wait
