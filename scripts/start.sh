#!/bin/bash
# =============================================================================
# Cloud Rover — Start All Components
#
# Single command to launch the entire system from any machine:
#   Mac (operator) → Desktop 3070 (brain) → Pi (rover)
#
# Architecture:
#   Mac ──ssh──▶ Desktop:  brain_server.py (inference on GPU)
#   Mac ──ssh──▶ Pi:       edge_stream.py  (sensors + motors)
#   Mac ──http─▶ Desktop:9090 (dashboard in browser)
#   Pi  ──ws───▶ Desktop:9091 (frames + actions)
#
# Usage:
#   bash scripts/start.sh                          # full system
#   bash scripts/start.sh --brain heuristic        # choose brain
#   bash scripts/start.sh --no-pi                  # skip Pi (test brain only)
#   bash scripts/start.sh --local                  # everything on this machine
# =============================================================================
set -e

BRAIN="heuristic"
SKIP_PI=false
LOCAL_MODE=false

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
        --local)
            LOCAL_MODE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: bash scripts/start.sh [--brain heuristic|openvla|dreamer] [--no-pi] [--local]"
            exit 1
            ;;
    esac
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# --- Resolve IPs ---
get_local_ip() {
    python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(('8.8.8.8', 80))
print(s.getsockname()[0])
s.close()
" 2>/dev/null || echo "127.0.0.1"
}

if [ "$LOCAL_MODE" = true ]; then
    BRAIN_IP=$(get_local_ip)
    BRAIN_HOST="localhost"
else
    # Get desktop IP from SSH config
    BRAIN_HOST="desktop"
    BRAIN_IP=$(ssh -G desktop 2>/dev/null | awk '/^hostname / {print $2}')
    if [ -z "$BRAIN_IP" ] || [ "$BRAIN_IP" = "desktop" ]; then
        echo "✗ Cannot resolve desktop IP."
        echo "  Run: bash scripts/mac-setup.sh --desktop-ip <IP>"
        echo "  Or use --local to run everything on this machine."
        exit 1
    fi
fi

echo "========================================="
echo "  Cloud Rover — Starting All Components"
echo "========================================="
echo "  Brain:    $BRAIN"
echo "  Brain at: $BRAIN_IP ($BRAIN_HOST)"
echo "  Skip Pi:  $SKIP_PI"
echo "  Local:    $LOCAL_MODE"
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
    if [ "$LOCAL_MODE" = false ]; then
        ssh desktop "pkill -f 'python.*brain_server' 2>/dev/null" 2>/dev/null || true
    fi
    if [ "$SKIP_PI" = false ]; then
        ssh pi "pkill -f 'python.*edge_stream' 2>/dev/null" 2>/dev/null || true
    fi
    wait 2>/dev/null
    echo "All components stopped."
}
trap cleanup EXIT INT TERM

# --- 1. Deploy latest code ---
echo "[1/3] Deploying code..."
if [ "$LOCAL_MODE" = false ]; then
    bash scripts/deploy-desktop.sh
fi
if [ "$SKIP_PI" = false ]; then
    bash scripts/deploy.sh
fi
echo ""

# --- 2. Start Brain Server ---
if [ "$LOCAL_MODE" = true ]; then
    echo "[2/3] Starting brain server locally (--brain $BRAIN)..."
    python3 cloud/brain_server.py --brain "$BRAIN" &
    PIDS+=($!)
else
    echo "[2/3] Starting brain server on desktop (--brain $BRAIN)..."
    ssh desktop "cd ~/cloud-rover && source .venv/bin/activate && python3 cloud/brain_server.py --brain $BRAIN" &
    PIDS+=($!)
fi
sleep 3

# --- 3. Start Pi edge_stream ---
if [ "$SKIP_PI" = false ]; then
    echo "[3/3] Starting edge_stream on Pi → ws://$BRAIN_IP:9091 ..."
    bash scripts/deploy.sh
    ssh pi "cd ~/cloud-rover && source .venv/bin/activate && python3 pi/edge_stream.py --dashboard ws://$BRAIN_IP:9091" &
    PIDS+=($!)
else
    echo "[3/3] Skipping Pi (--no-pi)."
fi

echo ""
echo "========================================="
echo "  All components running!"
echo "  Dashboard: http://$BRAIN_IP:9090"
echo "  Brain WS:  ws://$BRAIN_IP:9091"
echo "  Press Ctrl+C to stop everything."
echo "========================================="

# Open dashboard in browser (macOS)
if command -v open &>/dev/null; then
    open "http://$BRAIN_IP:9090" 2>/dev/null || true
fi

# Wait for all background processes
wait
