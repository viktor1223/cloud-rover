"""
Mock Cloud Brain — receives frames from Pi and returns actions.

Run this on your Mac to simulate the cloud AI endpoint.
The Pi streams camera frames here, and this returns mock decisions.

Usage:
    python3 cloud/mock_brain.py
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import time
import cgi
import os

frame_count = 0
start_time = None

class BrainHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        global frame_count, start_time
        
        if self.path == '/frame':
            if start_time is None:
                start_time = time.time()
            
            # Parse the multipart form data
            content_type = self.headers['Content-Type']
            ctype, pdict = cgi.parse_header(content_type)
            
            if ctype == 'multipart/form-data':
                pdict['boundary'] = pdict['boundary'].encode()
                fields = cgi.parse_multipart(self.rfile, pdict)
            
            frame_count += 1
            elapsed = time.time() - start_time
            fps = frame_count / elapsed if elapsed > 0 else 0
            
            # Simulate AI inference (mock action)
            actions = ["forward", "forward", "forward", "turn_left", "turn_right", "stop"]
            action = actions[frame_count % len(actions)]
            
            # Save latest frame for viewing
            if ctype == 'multipart/form-data' and 'image' in fields:
                os.makedirs("data/frames", exist_ok=True)
                with open("data/frames/latest.jpg", "wb") as f:
                    f.write(fields['image'][0])
            
            print(f"  Frame {frame_count:04d} received | "
                  f"FPS: {fps:.1f} | "
                  f"Action: {action}")
            
            # Return action to Pi
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {
                "action": action,
                "confidence": 0.87,
                "frame_num": frame_count,
                "inference_ms": 45  # simulated
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_GET(self):
        if self.path == '/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            elapsed = time.time() - start_time if start_time else 0
            self.wfile.write(json.dumps({
                "frames_received": frame_count,
                "uptime_s": round(elapsed, 1),
                "fps": round(frame_count / elapsed, 1) if elapsed > 0 else 0
            }).encode())
        elif self.path == '/latest':
            # Serve the latest frame as an image
            try:
                with open("data/frames/latest.jpg", "rb") as f:
                    img = f.read()
                self.send_response(200)
                self.send_header('Content-type', 'image/jpeg')
                self.end_headers()
                self.wfile.write(img)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # suppress default logs

def main():
    port = 9090
    print("=" * 60)
    print("  CLOUD ROVER — Mock Brain Server")
    print("=" * 60)
    print(f"  Listening on: http://0.0.0.0:{port}")
    print(f"  Endpoints:")
    print(f"    POST /frame   — receive camera frame from Pi")
    print(f"    GET  /status  — pipeline stats")
    print(f"    GET  /latest  — view latest frame in browser")
    print("=" * 60)
    print("\n  Waiting for frames from Pi...\n")
    
    server = HTTPServer(('0.0.0.0', port), BrainHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n\nShutdown. Received {frame_count} total frames.")
        server.server_close()

if __name__ == "__main__":
    main()
