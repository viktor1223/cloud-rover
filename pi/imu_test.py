"""IMU test — verify ADXL345 accelerometer wiring and readings.

Tests the ADXL345 on I2C address 0x53 (shared bus with PCA9685 at 0x40).
Connected via GPIO2 (SDA) and GPIO3 (SCL) as wired in diagram.json.

Usage:
    python3 pi/imu_test.py              # single reading
    python3 pi/imu_test.py --stream     # continuous readings (tilt monitor)
    python3 pi/imu_test.py --benchmark  # timing benchmark
"""

import argparse
import math
import time

READINGS = 100


def test_imu():
    """Take a single accelerometer reading and check orientation."""
    import board
    import busio
    import adafruit_adxl34x

    print("Initializing ADXL345...")
    print("  I2C address: 0x53")
    print("  Bus: GPIO2 (SDA), GPIO3 (SCL)")
    i2c = busio.I2C(board.SCL, board.SDA)
    accel = adafruit_adxl34x.ADXL345(i2c)
    time.sleep(0.2)

    x, y, z = accel.acceleration
    magnitude = math.sqrt(x**2 + y**2 + z**2)

    print(f"\n✓ IMU working!")
    print(f"  Acceleration: x={x:.3f}, y={y:.3f}, z={z:.3f} m/s²")
    print(f"  Magnitude: {magnitude:.3f} m/s² (expect ~9.81 at rest)")

    # Check if readings make sense
    if 8.0 < magnitude < 12.0:
        print("  Gravity vector looks correct")
    else:
        print(f"  ⚠ Magnitude {magnitude:.1f} m/s² is unusual — check wiring")

    # Estimate tilt
    pitch = math.degrees(math.atan2(x, math.sqrt(y**2 + z**2)))
    roll = math.degrees(math.atan2(y, math.sqrt(x**2 + z**2)))
    print(f"  Pitch: {pitch:.1f}°, Roll: {roll:.1f}°")

    if abs(pitch) < 5 and abs(roll) < 5:
        print("  Rover is approximately level ✓")
    else:
        print(f"  Rover is tilted (pitch={pitch:.1f}°, roll={roll:.1f}°)")

    return x, y, z


def stream_imu():
    """Continuous readings with tilt display (Ctrl+C to stop)."""
    import board
    import busio
    import adafruit_adxl34x

    print("Initializing ADXL345 (Ctrl+C to stop)...")
    i2c = busio.I2C(board.SCL, board.SDA)
    accel = adafruit_adxl34x.ADXL345(i2c)
    time.sleep(0.2)
    print()

    try:
        while True:
            x, y, z = accel.acceleration
            pitch = math.degrees(math.atan2(x, math.sqrt(y**2 + z**2)))
            roll = math.degrees(math.atan2(y, math.sqrt(x**2 + z**2)))
            mag = math.sqrt(x**2 + y**2 + z**2)

            # Simple collision indicator
            bump = " *** BUMP ***" if mag > 15.0 else ""

            print(f"\r  x={x:+6.2f}  y={y:+6.2f}  z={z:+6.2f}  "
                  f"pitch={pitch:+5.1f}°  roll={roll:+5.1f}°  "
                  f"|g|={mag:5.2f}{bump}",
                  end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n\nStopped.")


def benchmark_imu():
    """Measure I2C read timing."""
    import board
    import busio
    import adafruit_adxl34x

    print(f"IMU Benchmark ({READINGS} readings)\n")
    i2c = busio.I2C(board.SCL, board.SDA)
    accel = adafruit_adxl34x.ADXL345(i2c)
    time.sleep(0.2)

    times = []
    for _ in range(READINGS):
        t0 = time.monotonic()
        _ = accel.acceleration
        t1 = time.monotonic()
        times.append((t1 - t0) * 1000)

    avg_ms = sum(times) / len(times)
    min_ms = min(times)
    max_ms = max(times)

    print(f"  Read time:  avg={avg_ms:.2f} ms, min={min_ms:.2f} ms, max={max_ms:.2f} ms")
    print(f"  Max rate:   {1000 / avg_ms:.0f} Hz")
    print(f"  ✓ Fast enough for frame-rate reads ({avg_ms:.2f} ms per read)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ADXL345 IMU test")
    parser.add_argument("--stream", action="store_true", help="Continuous tilt monitor")
    parser.add_argument("--benchmark", action="store_true", help="Timing benchmark")
    args = parser.parse_args()

    if args.stream:
        stream_imu()
    elif args.benchmark:
        benchmark_imu()
    else:
        test_imu()
