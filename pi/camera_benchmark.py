"""Benchmark camera capture and encode pipeline to find bottlenecks."""
from picamera2 import Picamera2
from PIL import Image
import io
import time
import sys

FRAMES = 30

def benchmark_config(cam, size, jpeg_quality):
    """Benchmark a specific resolution + quality combo."""
    config = cam.create_still_configuration(
        main={"size": size, "format": "RGB888"}
    )
    cam.configure(config)
    cam.start()
    time.sleep(1)  # let auto-exposure settle

    capture_times = []
    encode_times = []
    sizes = []

    for _ in range(FRAMES):
        t0 = time.monotonic()
        frame = cam.capture_array()
        t1 = time.monotonic()

        img = Image.fromarray(frame[..., ::-1])
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=jpeg_quality)
        t2 = time.monotonic()

        capture_times.append(t1 - t0)
        encode_times.append(t2 - t1)
        sizes.append(buf.tell())

    cam.stop()

    avg_capture = sum(capture_times) / len(capture_times) * 1000
    avg_encode = sum(encode_times) / len(encode_times) * 1000
    avg_total = avg_capture + avg_encode
    avg_size = sum(sizes) / len(sizes) / 1024
    max_fps = 1000 / avg_total

    print(f"  {size[0]}x{size[1]} q={jpeg_quality}:")
    print(f"    Capture:  {avg_capture:6.1f} ms")
    print(f"    Encode:   {avg_encode:6.1f} ms")
    print(f"    Total:    {avg_total:6.1f} ms  ({max_fps:.1f} FPS max)")
    print(f"    JPEG size: {avg_size:.1f} KB")
    print()

    return {
        "size": size,
        "quality": jpeg_quality,
        "capture_ms": avg_capture,
        "encode_ms": avg_encode,
        "total_ms": avg_total,
        "fps": max_fps,
        "kb": avg_size,
    }

def main():
    print(f"Camera Benchmark ({FRAMES} frames per config)\n")
    cam = Picamera2()

    configs = [
        # (resolution, jpeg_quality)
        ((640, 480), 85),   # current setting
        ((640, 480), 50),   # lower quality
        ((640, 480), 30),   # aggressive compression
        ((320, 240), 50),   # smaller resolution
        ((320, 240), 30),   # smallest
        ((480, 360), 50),   # middle ground
    ]

    results = []
    for size, quality in configs:
        try:
            r = benchmark_config(cam, size, quality)
            results.append(r)
        except Exception as e:
            print(f"  {size[0]}x{size[1]} q={quality}: FAILED - {e}\n")

    # Summary
    print("=" * 60)
    print(f"{'Config':<20} {'Total ms':>10} {'FPS':>8} {'JPEG KB':>10}")
    print("-" * 60)
    for r in results:
        label = f"{r['size'][0]}x{r['size'][1]} q={r['quality']}"
        print(f"{label:<20} {r['total_ms']:>10.1f} {r['fps']:>8.1f} {r['kb']:>10.1f}")

if __name__ == "__main__":
    main()
