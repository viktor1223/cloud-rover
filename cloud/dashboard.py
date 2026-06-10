"""Dev HUD — out-of-band telemetry dashboard for Cloud Rover.

Runs on Mac. Receives frames from Pi via WebSocket, serves a
real-time dashboard to the browser. This is cold-path observability
only — the hot path (capture → brain → motors) is never affected.

Architecture:
    Pi ──ws:9091──▶ Dashboard Server ──ws:9091──▶ Browser
    (push frames)     (this script)              (HUD)

    HTTP :9090 serves the dashboard HTML.

Usage:
    python3 cloud/dashboard.py
    # Open http://localhost:9090 in browser
    # On Pi: python3 pi/edge_stream.py --dashboard ws://<mac-ip>:9091
"""

import asyncio
import json
import socket
import time
from collections import deque
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import threading

try:
    import websockets
except ImportError:
    print("Missing dependency: pip install websockets")
    raise SystemExit(1)

HTTP_PORT = 9090
WS_PORT = 9091

browsers: set = set()
metrics: deque = deque(maxlen=300)


def get_local_ip():
    """Get this machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


async def handle_pi(ws):
    """Receive frames from Pi, compute metrics, relay to browsers."""
    global browsers
    print("  ✓ Pi connected")
    try:
        async for message in ws:
            data = json.loads(message)
            if data.get("type") != "frame":
                continue

            # Compute network latency (approximate — depends on clock sync)
            now = time.time()
            network_ms = max(0, (now - data["ts"]) * 1000)
            data["network_ms"] = round(network_ms, 1)
            data["total_ms"] = round(
                data["capture_ms"] + data["encode_ms"] + network_ms, 1
            )
            metrics.append(data)

            # Relay to all connected browsers (best-effort)
            msg = json.dumps(data)
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
    """Hold browser connection open for frame relay."""
    global browsers
    browsers.add(ws)
    print(f"  ✓ Browser connected ({len(browsers)} total)")
    try:
        async for _ in ws:
            pass  # browsers don't send, just wait for close
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
    """Serve dashboard static files."""

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
    """Run HTTP server in a background thread."""
    HTTPServer(("0.0.0.0", HTTP_PORT), DashboardHandler).serve_forever()


async def main():
    ip = get_local_ip()
    print()
    print("  Cloud Rover — Dev HUD")
    print(f"  Dashboard : http://localhost:{HTTP_PORT}")
    print(f"  WebSocket : ws://{ip}:{WS_PORT}")
    print()
    print("  Run on Pi:")
    print(f"    python3 pi/edge_stream.py --dashboard ws://{ip}:{WS_PORT}")
    print()

    threading.Thread(target=run_http, daemon=True).start()

    async with websockets.serve(ws_handler, "0.0.0.0", WS_PORT):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
