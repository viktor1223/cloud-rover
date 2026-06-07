"""Camera test — verify Pi camera connection and stream a frame."""
from picamera2 import Picamera2
import time
import os

def test_camera():
    print("Initializing camera...")
    cam = Picamera2()
    
    config = cam.create_still_configuration(
        main={"size": (640, 480), "format": "RGB888"}
    )
    cam.configure(config)
    cam.start()
    time.sleep(2)  # warm-up
    
    # Capture a test frame
    frame = cam.capture_array()
    print(f"✓ Camera working! Frame shape: {frame.shape}")
    print(f"  Resolution: {frame.shape[1]}x{frame.shape[0]}")
    print(f"  Channels: {frame.shape[2]}")
    
    # Save test image
    os.makedirs("data", exist_ok=True)
    from PIL import Image
    img = Image.fromarray(frame)
    img.save("data/test_capture.jpg")
    print(f"✓ Saved test image to data/test_capture.jpg")
    
    cam.stop()
    return frame

if __name__ == "__main__":
    test_camera()
