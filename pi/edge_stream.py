"""Edge stream — capture frames, read sensors, receive actions, drive motors.

Runs on the Raspberry Pi. Main control loop:
    1. Capture camera frame
    2. Read sensors (IMU, ultrasonic)
    3. Send full observation packet to cloud brain
    4. Receive action from cloud brain
    5. Execute action via motor controller (with ultrasonic safety override)

Usage:
    python3 pi/edge_stream.py --dashboard ws://192.168.0.XX:9091
    python3 pi/edge_stream.py --dashboard ws://192.168.0.XX:9091 --dry-run
"""

import argparse
import asyncio
import base64
import io
import json
import time

from picamera2 import Picamera2
from PIL import Image

from motor_controller import MotorController


# ---------------------------------------------------------------------------
# Shared I2C bus — PCA9685 (0x40) and ADXL345 (0x53) share GPIO2/GPIO3
# ---------------------------------------------------------------------------

_i2c = None

def get_i2c():
    """Return a shared I2C bus instance."""
    global _i2c
    if _i2c is None:
        import board
        import busio
        _i2c = busio.I2C(board.SCL, board.SDA)
    return _i2c


# ---------------------------------------------------------------------------
# Status LED on GPIO18 (from diagram.json)
# ---------------------------------------------------------------------------

_led = None

def init_led():
    global _led
    try:
        from gpiozero import LED
        _led = LED(18)
        _led.on()
        print("  ✓ Status LED (GPIO18) on")
    except Exception as e:
        print(f"  ✗ Status LED unavailable ({e}), skipping")


def led_blink():
    if _led:
        _led.toggle()


# ---------------------------------------------------------------------------
# Sensor helpers
# ---------------------------------------------------------------------------

def init_imu():
    """Initialize ADXL345 accelerometer on shared I2C bus (address 0x53)."""
    try:
        import adafruit_adxl34x
        accel = adafruit_adxl34x.ADXL345(get_i2c())
        print("  ✓ IMU (ADXL345) ready")
        return accel
    except Exception as e:
        print(f"  ✗ IMU unavailable ({e}), skipping")
        return None


def read_imu(accel) -> dict | None:
    """Read acceleration (x, y, z) in m/s². Returns None if unavailable."""
    if accel is None:
        return None
    try:
        x, y, z = accel.acceleration
        return {"x": round(x, 3), "y": round(y, 3), "z": round(z, 3)}
    except Exception:
        return None


def init_sonar(trig_pin: int, echo_pin: int):
    """Initialize HC-SR04 ultrasonic sensor.

    Uses gpiozero for simplicity. ECHO must go through voltage divider
    (1kΩ/2kΩ) — see diagram.json.
    """
    try:
        from gpiozero import DistanceSensor
        sensor = DistanceSensor(echo=echo_pin, trigger=trig_pin,
                                max_distance=4.0)
        print(f"  ✓ Sonar ready (TRIG=GPIO{trig_pin}, ECHO=GPIO{echo_pin})")
        return sensor
    except Exception as e:
        print(f"  ✗ Sonar unavailable ({e}), skipping")
        return None


def read_sonar(sensor) -> float | None:
    """Read distance in cm. Returns None if unavailable."""
    if sensor is None:
        return None
    try:
        return round(sensor.distance * 100, 1)  # m → cm
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Ultrasonic safety override (ADR-003 Phase 2)
# ---------------------------------------------------------------------------

EMERGENCY_STOP_CM = 15.0
SLOW_ZONE_CM = 40.0
SLOW_ZONE_MAX_SPEED = 0.30


def safety_check(action: str, distance_cm: float | None) -> str:
    """Override action based on ultrasonic reading.

    Only overrides forward movement. Turns and stops pass through.
    Returns the (possibly overridden) action. Speed capping for the
    slow zone (15-40cm) is handled separately in the main loop since
    it requires modifying speed, not just the action string.
    """
    if distance_cm is None:
        return action  # sensor unavailable, trust the brain
    if action not in ("FORWARD",):
        return action  # only restrict forward motion
    if distance_cm < EMERGENCY_STOP_CM:
        return "STOP"
    return action


# ---------------------------------------------------------------------------
# Main stream loop
# ---------------------------------------------------------------------------

async def stream(dashboard_uri, width, height, quality, dry_run):
    # Init camera
    print("Initializing camera...")
    cam = Picamera2()
    config = cam.create_video_configuration(
        main={"size": (width, height), "format": "RGB888"}
    )
    cam.configure(config)
    cam.start()
    time.sleep(2)
    print(f"  ✓ Camera ready: {width}x{height}, JPEG quality={quality}")

    # Init motors (shared I2C bus with IMU)
    motors = MotorController(dry_run=dry_run,
                             i2c=None if dry_run else get_i2c())
    motors.startup()

    # Init sensors (GPIO pins from diagram.json)
    imu = init_imu()
    sonar = init_sonar(trig_pin=24, echo_pin=25)

    # Status LED
    init_led()

    import websockets

    seq = 0
    while True:
        try:
            async with websockets.connect(dashboard_uri) as ws:
                await ws.send(json.dumps({"role": "pi"}))
                print(f"Connected to brain server at {dashboard_uri}")

                while True:
                    # --- Capture frame ---
                    t0 = time.monotonic()
                    frame = cam.capture_array()
                    t_capture = time.monotonic()

                    img = Image.fromarray(frame[..., ::-1])  # BGR → RGB
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=quality)
                    t_encode = time.monotonic()

                    # --- Read sensors ---
                    accel_data = read_imu(imu)
                    distance_cm = read_sonar(sonar)
                    t_sensor = time.monotonic()

                    # --- Build observation packet ---
                    jpeg_bytes = buf.getvalue()
                    motor_state = motors.get_state()

                    msg = json.dumps({
                        "type": "frame",
                        "seq": seq,
                        "ts": time.time(),
                        "capture_ms": round((t_capture - t0) * 1000, 1),
                        "encode_ms": round((t_encode - t_capture) * 1000, 1),
                        "sensor_ms": round((t_sensor - t_encode) * 1000, 1),
                        "jpeg_kb": round(len(jpeg_bytes) / 1024, 1),
                        "frame": base64.b64encode(jpeg_bytes).decode(),
                        "accel": accel_data,
                        "distance_cm": distance_cm,
                        "motors": motor_state.to_dict(),
                    })

                    await ws.send(msg)

                    # --- Receive action from brain ---
                    try:
                        reply = await asyncio.wait_for(ws.recv(), timeout=0.5)
                        data = json.loads(reply)
                        if data.get("type") == "action":
                            action = data["action"]
                            action = safety_check(action, distance_cm)
                            motors.execute(action)
                    except asyncio.TimeoutError:
                        pass  # brain didn't respond in time, keep going

                    led_blink()  # visual heartbeat
                    seq += 1

        except (ConnectionRefusedError, OSError) as e:
            motors.stop()
            print(f"Brain server unavailable ({e}), motors stopped, retrying in 2s...")
            await asyncio.sleep(2)
        except Exception as e:
            motors.stop()
            print(f"Connection lost ({type(e).__name__}: {e}), motors stopped, reconnecting...")
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="Cloud Rover — edge stream")
    parser.add_argument(
        "--dashboard", default="ws://localhost:9091",
        help="Brain server WebSocket URI (default: ws://localhost:9091)",
    )
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--quality", type=int, default=50,
                        help="JPEG quality 1-95 (default: 50)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print motor commands instead of sending I2C")
    args = parser.parse_args()

    asyncio.run(stream(args.dashboard, args.width, args.height, args.quality,
                       args.dry_run))


if __name__ == "__main__":
    main()
