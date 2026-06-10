"""Edge capture loop — pushes frames to the dashboard server.

Runs on the Raspberry Pi. Captures camera frames with timing metadata
and pushes them to the Mac dashboard via WebSocket (best-effort).

Usage:
    python3 pi/edge_stream.py --dashboard ws://192.168.0.XX:9091
"""

import argparse
import asyncio
import base64
import io
import json
import time

from picamera2 import Picamera2
from PIL import Image


async def stream(dashboard_uri, width, height, quality):
    print("Initializing camera...")
    cam = Picamera2()
    config = cam.create_video_configuration(
        main={"size": (width, height), "format": "RGB888"}
    )
    cam.configure(config)
    cam.start()
    time.sleep(2)
    print(f"Camera ready: {width}x{height}, JPEG quality={quality}")

    import websockets

    seq = 0
    while True:
        try:
            async with websockets.connect(dashboard_uri) as ws:
                await ws.send(json.dumps({"role": "pi"}))
                print(f"Connected to dashboard at {dashboard_uri}")

                while True:
                    t0 = time.monotonic()
                    frame = cam.capture_array()
                    t_capture = time.monotonic()

                    img = Image.fromarray(frame[..., ::-1])  # BGR → RGB
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=quality)
                    t_encode = time.monotonic()

                    jpeg_bytes = buf.getvalue()

                    msg = json.dumps({
                        "type": "frame",
                        "seq": seq,
                        "ts": time.time(),
                        "capture_ms": round((t_capture - t0) * 1000, 1),
                        "encode_ms": round((t_encode - t_capture) * 1000, 1),
                        "jpeg_kb": round(len(jpeg_bytes) / 1024, 1),
                        "frame": base64.b64encode(jpeg_bytes).decode(),
                    })

                    await ws.send(msg)
                    seq += 1

        except (ConnectionRefusedError, OSError) as e:
            print(f"Dashboard unavailable ({e}), retrying in 2s...")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"Connection lost ({type(e).__name__}: {e}), reconnecting...")
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="Cloud Rover — edge stream")
    parser.add_argument(
        "--dashboard", default="ws://localhost:9091",
        help="Dashboard WebSocket URI (default: ws://localhost:9091)",
    )
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--quality", type=int, default=50,
                        help="JPEG quality 1-95 (default: 50)")
    args = parser.parse_args()

    asyncio.run(stream(args.dashboard, args.width, args.height, args.quality))


if __name__ == "__main__":
    main()
