"""Ultrasonic sensor test — verify HC-SR04 wiring and voltage divider.

Tests the HC-SR04 on GPIO24 (TRIG) and GPIO25 (ECHO) as wired in diagram.json.
The ECHO pin must go through a 1kΩ/2kΩ voltage divider to bring 5V down to 3.3V.

Usage:
    python3 pi/sonar_test.py              # single reading
    python3 pi/sonar_test.py --stream     # continuous readings
    python3 pi/sonar_test.py --benchmark  # timing benchmark
"""

import argparse
import time

TRIG_PIN = 24  # GPIO24 (diagram.json)
ECHO_PIN = 25  # GPIO25 (diagram.json, via voltage divider)
READINGS = 30


def test_sonar():
    """Take a single distance reading."""
    from gpiozero import DistanceSensor

    print("Initializing HC-SR04...")
    print(f"  TRIG: GPIO{TRIG_PIN}")
    print(f"  ECHO: GPIO{ECHO_PIN} (via 1kΩ/2kΩ voltage divider)")
    sensor = DistanceSensor(echo=ECHO_PIN, trigger=TRIG_PIN, max_distance=4.0)
    time.sleep(0.5)

    distance = sensor.distance * 100  # m → cm
    print(f"\n✓ Sonar working! Distance: {distance:.1f} cm")

    if distance < 2:
        print("  ⚠ Reading < 2cm — sensor may be blocked or wiring issue")
    elif distance > 390:
        print("  ⚠ Reading > 390cm — nothing in range or ECHO not connected")
    else:
        print("  Reading looks normal")

    sensor.close()
    return distance


def stream_sonar():
    """Continuous distance readings (Ctrl+C to stop)."""
    from gpiozero import DistanceSensor

    print("Initializing HC-SR04 (Ctrl+C to stop)...")
    sensor = DistanceSensor(echo=ECHO_PIN, trigger=TRIG_PIN, max_distance=4.0)
    time.sleep(0.5)
    print()

    try:
        while True:
            d = sensor.distance * 100
            bar = "█" * int(min(d, 100) / 2)
            print(f"\r  {d:6.1f} cm  {bar:<50}", end="", flush=True)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\nStopped.")
    finally:
        sensor.close()


def benchmark_sonar():
    """Measure read timing over multiple samples."""
    from gpiozero import DistanceSensor

    print(f"Sonar Benchmark ({READINGS} readings)\n")
    sensor = DistanceSensor(echo=ECHO_PIN, trigger=TRIG_PIN, max_distance=4.0)
    time.sleep(0.5)

    times = []
    distances = []
    for i in range(READINGS):
        t0 = time.monotonic()
        d = sensor.distance * 100
        t1 = time.monotonic()
        ms = (t1 - t0) * 1000
        times.append(ms)
        distances.append(d)

    sensor.close()

    avg_ms = sum(times) / len(times)
    min_ms = min(times)
    max_ms = max(times)
    avg_dist = sum(distances) / len(distances)
    std_dist = (sum((d - avg_dist) ** 2 for d in distances) / len(distances)) ** 0.5

    print(f"  Read time:  avg={avg_ms:.1f} ms, min={min_ms:.1f} ms, max={max_ms:.1f} ms")
    print(f"  Distance:   avg={avg_dist:.1f} cm, std={std_dist:.1f} cm")
    print(f"  Max rate:   {1000 / avg_ms:.0f} Hz")
    print()
    print(f"  ✓ Sensor stable" if std_dist < 5 else f"  ⚠ High variance ({std_dist:.1f} cm) — check mounting")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HC-SR04 ultrasonic test")
    parser.add_argument("--stream", action="store_true", help="Continuous readings")
    parser.add_argument("--benchmark", action="store_true", help="Timing benchmark")
    args = parser.parse_args()

    if args.stream:
        stream_sonar()
    elif args.benchmark:
        benchmark_sonar()
    else:
        test_sonar()
