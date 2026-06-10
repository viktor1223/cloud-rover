"""Brain Server — receives frames from Pi, runs inference, relays to dashboard.

This is the hot path: Pi → Brain Server → Dashboard.
The brain processes every frame and sends back detections + actions.

Architecture:
    Pi ──ws:9091──▶ Brain Server ──ws:9091──▶ Dashboard (browser)
                        │
                    runs YOLO + planner
                    on every frame

Usage:
    python3 cloud/brain_server.py [--brain heuristic|openvla|dreamer]
"""

import argparse
import asyncio
import base64
import io
import json
import socket
import time
import threading
from collections import deque
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import numpy as np
from PIL import Image

try:
    import websockets
except ImportError:
    print("Missing dependency: pip install websockets")
    raise SystemExit(1)

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.protocol import Action, BrainResult

HTTP_PORT = 9090
WS_PORT = 9091

browsers: set = set()
active_brain = None
current_command: str = ""  # set via dashboard text input


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def load_brain(brain_name: str):
    """Load and start a brain by name."""
    if brain_name == "heuristic":
        from cloud.brains.heuristic import HeuristicBrain
        brain = HeuristicBrain()
    elif brain_name == "openvla":
        from cloud.brains.openvla import OpenVLABrain
        brain = OpenVLABrain()
    elif brain_name == "dreamer":
        from cloud.brains.dreamer import DreamerBrain
        brain = DreamerBrain()
    else:
        raise ValueError(f"Unknown brain: {brain_name}")

    brain.startup()
    return brain


def decode_frame(b64_jpeg: str) -> np.ndarray:
    """Decode a base64 JPEG into a numpy RGB array."""
    jpeg_bytes = base64.b64decode(b64_jpeg)
    img = Image.open(io.BytesIO(jpeg_bytes))
    return np.array(img)


async def handle_pi(ws):
    """Receive frames from Pi, run brain, relay results to browsers."""
    global browsers
    print("  ✓ Pi connected")
    try:
        async for message in ws:
            data = json.loads(message)
            if data.get("type") != "frame":
                continue

            # Decode frame
            frame = decode_frame(data["frame"])

            # Run brain inference
            result = active_brain.act(frame, current_command)

            # Compute network latency
            now = time.time()
            network_ms = max(0, (now - data["ts"]) * 1000)

            # Build message for dashboard
            out = {
                "type": "frame",
                "seq": data["seq"],
                "ts": data["ts"],
                "capture_ms": data["capture_ms"],
                "encode_ms": data["encode_ms"],
                "network_ms": round(network_ms, 1),
                "jpeg_kb": data["jpeg_kb"],
                "frame": data["frame"],  # pass through for display
                "brain": result.to_dict(),
                "command": current_command,
                "total_ms": round(
                    data["capture_ms"] + data["encode_ms"]
                    + network_ms + result.inference_ms, 1
                ),
            }

            # Relay to browsers (best-effort)
            msg = json.dumps(out)
            gone = set()
            for b in browsers:
                try:
                    await b.send(msg)
                except Exception:
                    gone.add(b)
            browsers -= gone

    except websockets.ConnectionClosed:
        pass
    finally:
        print("  ✗ Pi disconnected")


async def handle_browser(ws):
    """Handle browser connections. Receives commands, sends frames."""
    global browsers, current_command
    browsers.add(ws)
    print(f"  ✓ Browser connected ({len(browsers)} total)")
    try:
        async for message in ws:
            data = json.loads(message)
            if data.get("type") == "command":
                current_command = data.get("text", "")
                print(f"  ⟫ Command: '{current_command}'")
    except websockets.ConnectionClosed:
        pass
    finally:
        browsers.discard(ws)
        print(f"  ✗ Browser disconnected ({len(browsers)} total)")


async def ws_handler(websocket, *args):
    """Route connections by role handshake."""
    try:
        msg = await asyncio.wait_for(websocket.recv(), timeout=5)
    except (asyncio.TimeoutError, websockets.ConnectionClosed):
        return

    hello = json.loads(msg)
    role = hello.get("role")

    if role == "pi":
        await handle_pi(websocket)
    elif role == "browser":
        await handle_browser(websocket)
    else:
        await websocket.close(1008, "Send {'role': 'pi'|'browser'} first")


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        d = str(Path(__file__).parent / "static")
        super().__init__(*args, directory=d, **kwargs)

    def do_GET(self):
        if self.path == "/":
            self.path = "/dashboard.html"
        super().do_GET()

    def log_message(self, format, *args):
        pass


def run_http():
    HTTPServer(("0.0.0.0", HTTP_PORT), DashboardHandler).serve_forever()


async def main(brain_name: str):
    global active_brain

    ip = get_local_ip()

    print(f"\n  Loading brain: {brain_name}")
    active_brain = load_brain(brain_name)

    print()
    print(f"  Cloud Rover — Brain Server [{active_brain.name}]")
    print(f"  Dashboard : http://localhost:{HTTP_PORT}")
    print(f"  WebSocket : ws://{ip}:{WS_PORT}")
    print()
    print("  Run on Pi:")
    print(f"    python3 pi/edge_stream.py --dashboard ws://{ip}:{WS_PORT}")
    print()

    threading.Thread(target=run_http, daemon=True).start()

    async with websockets.serve(ws_handler, "0.0.0.0", WS_PORT):
        await asyncio.Future()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cloud Rover — Brain Server")
    parser.add_argument(
        "--brain", default="heuristic",
        choices=["heuristic", "openvla", "dreamer"],
        help="Which brain to use (default: heuristic)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.brain))
