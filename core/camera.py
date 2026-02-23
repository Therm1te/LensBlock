import cv2
import threading
import time

class CameraStream:
    def __init__(self, camera_index=0, width=640, height=480, fps=30):
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.fps = fps
        self.cap = None
        self.is_running = False
        self.current_frame = None
        self.lock = threading.Lock()
        self.thread = None

    def start(self):
        """Starts the video capture thread."""
        if self.is_running:
            return

        self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_MSMF) # Use Media Foundation on Windows for faster startup
        if not self.cap.isOpened():
            print(f"Warning: Could not open camera {self.camera_index} with Media Foundation. Falling back to default backend.")
            self.cap = cv2.VideoCapture(self.camera_index)
            if not self.cap.isOpened():
                print(f"Error: Could not open camera {self.camera_index}")
                return False

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)

        self.is_running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        return True

    def _update(self):
        """Continuously reads frames from the camera in a background thread."""
        while self.is_running:
            start_time = time.time()
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    with self.lock:
                        self.current_frame = frame
                else:
                    print("Warning: Failed to read frame from camera.")
            
            # Simple soft-cap on FPS if the camera runs too fast
            elapsed_time = time.time() - start_time
            sleep_time = max(0, (1.0 / self.fps) - elapsed_time)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def read(self):
        """Returns the most recent frame."""
        with self.lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
            return None

    def stop(self):
        """Stops the video capture thread and releases the camera."""
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        
        if self.cap and self.cap.isOpened():
            self.cap.release()
            
        with self.lock:
            self.current_frame = None
