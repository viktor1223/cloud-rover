# Architecture Decisions

Technical decisions, benchmarks, and known limitations for the Cloud Rover project.

## ADR-001: Camera Capture Pipeline Selection (IMX708 + picamera2)

**Date:** 2026-06-09
**Updated:** 2026-06-09
**Status:** Superseded by ADR-001b

### Context

Benchmarked the ArduCam IMX708 camera module on a Raspberry Pi 3 Model B using `picamera2`'s still capture pipeline (`create_still_configuration`). Tested across multiple resolutions and JPEG quality levels.

### Benchmark Results (Still Pipeline)

| Config | Capture (ms) | Encode (ms) | Total (ms) | Max FPS | JPEG Size (KB) |
|--------|-------------|-------------|------------|---------|----------------|
| 640x480 q=85 | 63.5 | 62.9 | 126.5 | 7.9 | 13.7 |
| 640x480 q=50 | 62.7 | 75.7 | 138.4 | 7.2 | 5.9 |
| 640x480 q=30 | 59.0 | 62.4 | 121.5 | 8.2 | 5.6 |
| 320x240 q=50 | 105.0 | 16.1 | 121.0 | 8.3 | 2.2 |
| 320x240 q=30 | 96.8 | 24.7 | 121.5 | 8.2 | 1.9 |
| 480x360 q=50 | 55.2 | 67.9 | 123.1 | 8.1 | 3.8 |

### Original Findings

- The sensor readout was the bottleneck at 55-105 ms per frame.
- ~8 FPS was the hard ceiling with the still pipeline.

---

## ADR-001b: Switch to Video Pipeline (2x FPS Improvement)

**Date:** 2026-06-09
**Status:** Accepted

### Context

The still pipeline (`create_still_configuration`) applies heavy per-frame ISP
processing designed for photography. The video pipeline
(`create_video_configuration`) uses a lighter processing path designed for
continuous streaming. We benchmarked both on the same hardware.

### Benchmark Results (Still vs Video)

| Config | Capture (ms) | Encode (ms) | Total (ms) | Max FPS | JPEG Size (KB) |
|--------|-------------|-------------|------------|---------|----------------|
| 640x480 q=50 [still] | 64.0 | 59.6 | 123.5 | 8.1 | 6.2 |
| 640x480 q=50 [video] | 4.2 | 59.0 | 63.2 | 15.8 | 6.7 |
| 640x480 q=85 [video] | 4.1 | 61.1 | 65.2 | 15.3 | 25.4 |
| 640x480 q=30 [video] | 4.0 | 58.6 | 62.6 | 16.0 | 5.7 |
| 320x240 q=50 [video] | 16.5 | 15.1 | 31.7 | 31.6 | 2.3 |
| 480x360 q=50 [video] | 3.0 | 33.8 | 36.8 | 27.2 | 4.1 |

### Key Findings

- **Video pipeline reduces capture time from 64 ms to 4 ms** (16x improvement).
- **FPS doubled at 640x480**: 8 FPS (still) to 16 FPS (video).
- **The new bottleneck is JPEG encoding** (~59 ms via Pillow software encode), no longer the camera.
- **Lower resolutions now actually help**: 480x360 reaches 27 FPS, 320x240 reaches 32 FPS.
- **Image quality difference is negligible** for ML inference (slightly different color space metadata, same visual output).

### Decision

Use `create_video_configuration` with **640x480 at JPEG quality 50** as the
default. This delivers 16 FPS at 6.7 KB per frame with no quality loss that
matters for the brain.

### Future Optimization

The remaining bottleneck is PIL's software JPEG encoding (59 ms). Options to
push FPS higher:

- Use `turbojpeg` (libjpeg-turbo Python bindings) for ~3-5x faster JPEG encode
- Drop resolution to 480x360 for 27 FPS with acceptable quality
- Send raw frames over the network and encode on the desktop GPU

### Hardware

- Board: Raspberry Pi 3 Model B v1.2 (1 GB RAM, aarch64)
- Camera: ArduCam IMX708 (12 MP)
- Sensor driver: libcamera v0.7.1+rpt20260429
- Software: picamera2 0.3.34, Pillow 11.1.0
