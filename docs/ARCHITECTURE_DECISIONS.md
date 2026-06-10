# Architecture Decisions

Technical decisions, benchmarks, and known limitations for the Cloud Rover project.

## ADR-001: Camera Capture Limited to ~8 FPS (IMX708 + picamera2)

**Date:** 2026-06-09
**Status:** Accepted

### Context

Benchmarked the ArduCam IMX708 camera module on a Raspberry Pi 3 Model B using `picamera2`'s still capture pipeline (`create_still_configuration`). Tested across multiple resolutions and JPEG quality levels.

### Benchmark Results

| Config | Capture (ms) | Encode (ms) | Total (ms) | Max FPS | JPEG Size (KB) |
|--------|-------------|-------------|------------|---------|----------------|
| 640x480 q=85 | 63.5 | 62.9 | 126.5 | 7.9 | 13.7 |
| 640x480 q=50 | 62.7 | 75.7 | 138.4 | 7.2 | 5.9 |
| 640x480 q=30 | 59.0 | 62.4 | 121.5 | 8.2 | 5.6 |
| 320x240 q=50 | 105.0 | 16.1 | 121.0 | 8.3 | 2.2 |
| 320x240 q=30 | 96.8 | 24.7 | 121.5 | 8.2 | 1.9 |
| 480x360 q=50 | 55.2 | 67.9 | 123.1 | 8.1 | 3.8 |

### Key Findings

- **The sensor readout is the bottleneck**, not JPEG encoding. Capture takes 55-105 ms regardless of resolution.
- **Lowering resolution does not help.** The Pi reads the full sensor and downscales. 320x240 is actually slower to capture than 640x480.
- **JPEG quality has minimal FPS impact.** q=30 vs q=85 saves bandwidth but not time.
- **~8 FPS is the hard ceiling** with this hardware and the still capture pipeline.

### Decision

Use **640x480 at JPEG quality 50** as the default. This gives:
- Full resolution for the vision model (more detail for object detection and path planning)
- Small frame size (~6 KB) for efficient network transfer
- Same FPS as any other config

### Future Options

- Switch to `create_video_configuration` (uses the hardware video pipeline, can reach 30+ FPS)
- Upgrade to Raspberry Pi 5 (faster ISP, faster I/O)
- Use hardware MJPEG encoding instead of PIL software encoding

### Hardware

- Board: Raspberry Pi 3 Model B v1.2 (1 GB RAM, aarch64)
- Camera: ArduCam IMX708 (12 MP)
- Sensor driver: libcamera v0.7.1+rpt20260429
- Software: picamera2 0.3.34, Pillow 11.1.0
