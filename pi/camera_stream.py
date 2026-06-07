"""Stream camera frames over HTTP for viewing from Mac."""
from picamera2 import Picamera2
from http.server import HTTPServer, BaseHTTPRequestHandler
import io
import time
import threading

cam = None

class StreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'''<html><body>
                <h1>Pi Camera Stream</h1>
                <img src="/stream" width="640" height="480" />
            </body></html>''')
        elif self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            while True:
                try:
                    frame = cam.capture_array()
                    from PIL import Image
                    img = Image.fromarray(frame[..., ::-1])
                    buf = io.BytesIO()
                    img.save(buf, format='JPEG')
                    jpg = buf.getvalue()
                    self.wfile.write(b'--frame\r\n')
                    self.wfile.write(b'Content-Type: image/jpeg\r\n\r\n')
                    self.wfile.write(jpg)
                    self.wfile.write(b'\r\n')
                    time.sleep(0.1)  # ~10 FPS
                except (BrokenPipeError, ConnectionResetError):
                    break
    
    def log_message(self, format, *args):
        pass  # suppress logs

def main():
    global cam
    print("Starting camera...")
    cam = Picamera2()
    config = cam.create_still_configuration(
        main={"size": (640, 480), "format": "RGB888"}
    )
    cam.configure(config)
    cam.start()
    time.sleep(2)
    
    server = HTTPServer(('0.0.0.0', 8080), StreamHandler)
    print("✓ Camera stream running at http://pi-brain.local:8080")
    print("  Open this URL on your Mac to see the live feed")
    print("  Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        cam.stop()
        server.server_close()

if __name__ == "__main__":
    main()
