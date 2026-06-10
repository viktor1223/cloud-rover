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

# Signal health tracking
signal_events: deque = deque(maxlen=2000)
last_pi_seq: int = -1
session_start: float = time.time()
pi_connected: bool = False


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


def emit_signal_event(event_type, signal="camera", **kwargs):
    """Record a signal event and relay it to browsers."""
    evt = {"type": "signal_event", "event": event_type, "signal": signal,
           "ts": time.time(), **kwargs}
    signal_events.append(evt)
    return evt


async def broadcast_signal_event(evt):
    """Best-effort broadcast of a signal event to browsers."""
    msg = json.dumps(evt)
    gone = set()
    for b in browsers:
        try:
            await b.send(msg)
        except Exception:
            gone.add(b)
    browsers.difference_update(gone)


async def handle_pi(ws):
    """Receive frames from Pi, compute metrics, relay to browsers."""
    global browsers, last_pi_seq, pi_connected
    pi_connected = True
    print("  ✓ Pi connected")
    evt = emit_signal_event("pi_connected")
    await broadcast_signal_event(evt)
    try:
        async for message in ws:
            data = json.loads(message)
            if data.get("type") != "frame":
                continue

            # Detect sequence gaps (dropped frames)
            seq = data.get("seq", 0)
            if last_pi_seq >= 0 and seq > last_pi_seq + 1:
                gap = seq - last_pi_seq - 1
                gap_evt = emit_signal_event(
                    "seq_gap", gap=gap,
                    from_seq=last_pi_seq, to_seq=seq,
                )
                await broadcast_signal_event(gap_evt)
            last_pi_seq = seq

            # Compute network latency (approximate — depends on clock sync)
            now = time.time()
            network_ms = max(0, (now - data["ts"]) * 1000)
            data["network_ms"] = round(network_ms, 1)
            data["total_ms"] = round(
                data["capture_ms"] + data["encode_ms"] + network_ms, 1
            )
            metrics.append(data)

            # Detect latency spike
            if data["total_ms"] > 300:
                spike_evt = emit_signal_event(
                    "latency_spike", total_ms=data["total_ms"],
                    network_ms=data["network_ms"], seq=seq,
                )
                await broadcast_signal_event(spike_evt)

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
        pi_connected = False
        print("  ✗ Pi disconnected")
        evt = emit_signal_event("pi_disconnected")
        await broadcast_signal_event(evt)


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
    """Serve dashboard static files and signal health API."""

    def __init__(self, *args, **kwargs):
        d = str(Path(__file__).parent / "static")
        super().__init__(*args, directory=d, **kwargs)

    def do_GET(self):
        if self.path == "/":
            self.path = "/dashboard.html"
        elif self.path == "/api/signal-events":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            payload = json.dumps({
                "session_start": session_start,
                "pi_connected": pi_connected,
                "events": list(signal_events),
                "metrics_snapshot": list(metrics)[-60:],
            })
            self.wfile.write(payload.encode())
            return
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
