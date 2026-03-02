import time
import cv2
from PyQt6.QtCore import QObject, pyqtSignal as Signal, QThread
from config import ConfigHandler
from security.logger import ThreatLogger
from core.engine import YoloV8Engine
from core.camera import CameraStream

try:
    import pyvirtualcam
    VIRTUAL_CAM_AVAILABLE = True
except ImportError:
    VIRTUAL_CAM_AVAILABLE = False
    print("Warning: pyvirtualcam not installed. Virtual camera disabled.")

class SecurityController(QThread):
    """
    Background worker thread that manages the camera stream, 
    inference loop, and threat persistence logic.
    Emits signals safely to the main GUI thread.
    """
    # Emits (is_threat_active, remaining_lockout_seconds)
    threat_detected = Signal(bool, int)
    frame_ready = Signal(object)     # For updating the dashboard preview
    debug_frame_ready = Signal(object)  # For the debug view annotated frame

    def __init__(self, config: ConfigHandler, logger: ThreatLogger):
        super().__init__()
        self.config = config
        self.logger = logger
        
        self.camera = CameraStream()
        self.engine = YoloV8Engine()
        
        self.is_running = False
        self.monitoring_active = True
        self.debug_mode = False
        self.pending_camera_restart = False
        self.pending_model_restart = False
        
        # FPS tracking
        self._frame_count = 0
        self._fps_start = time.time()
        self._current_fps = 0.0
        
        # State variables
        self.consecutive_threat_frames = 0
        self.is_threat_active = False
        self.incident_start_time = None
        self.max_threat_confidence = 0.0
        self.lockout_end_time = 0.0

    def get_settings(self):
        """Fetches dynamic settings that the user might have updated."""
        threshold = self.config.get('detection', 'confidence_threshold', 0.60)
        persistence = self.config.get('detection', 'persistence_frames', 3)
        log_enabled = self.config.get('logging', 'enable_forensic_logging', True)
        lockout = self.config.get('detection', 'lockout_duration_seconds', 10)
        return threshold, persistence, log_enabled, lockout

    def run(self):
        """Main QThread execution loop."""
        if not self.camera.start():
            print("Failed to start camera stream. Controller aborting.")
            return

        self.is_running = True
        
        # Initialize virtual camera for broadcasting to Zoom/Teams
        vcam = None
        if VIRTUAL_CAM_AVAILABLE:
            try:
                vcam = pyvirtualcam.Camera(width=640, height=480, fps=30, fmt=pyvirtualcam.PixelFormat.RGB)
                print(f"Virtual Camera started: {vcam.device}")
            except Exception as e:
                print(f"Warning: Could not start virtual camera ({e}). Broadcasting disabled.")
                vcam = None
        
        while self.is_running:
            if self.pending_camera_restart:
                camera_idx = self.config.get('system', 'camera_index', 0)
                print(f"Restarting camera with index: {camera_idx}")
                self.camera.stop()
                self.camera = CameraStream(camera_index=camera_idx)
                self.camera.start()
                self.pending_camera_restart = False
            
            if self.pending_model_restart:
                model_path = self.config.get('detection', 'model_path', 'models/yolov8n.onnx')
                print(f"Restarting engine with model: {model_path}")
                self.engine = YoloV8Engine(model_path=model_path)
                self.pending_model_restart = False

            # We need the RAW frame for the virtual camera when paused,
            # since self.camera.read() returns None when self.camera.is_paused
            with self.camera.lock:
                raw_frame = self.camera.current_frame.copy() if self.camera.current_frame is not None else None

            if self.monitoring_active or self.debug_mode:
                frame = self.camera.read()
                if frame is not None:
                    # Emit raw frame for dashboard preview
                    self.frame_ready.emit(frame)

                    # FPS calculation
                    self._frame_count += 1
                    elapsed = time.time() - self._fps_start
                    if elapsed >= 1.0:
                        self._current_fps = self._frame_count / elapsed
                        self._frame_count = 0
                        self._fps_start = time.time()

                    if self.debug_mode:
                        # Use the full debug pipeline with bounding boxes
                        detected, confidence, annotated, det_count = self.engine.detect_debug(frame)
                        
                        # Overlay FPS, Status, Detection Count
                        status_text = "Shield Active" if self.is_threat_active else "Monitoring"
                        overlay_lines = [
                            f"FPS: {self._current_fps:.1f}",
                            f"Status: {status_text}",
                            f"Detections: {det_count}",
                        ]
                        y_offset = annotated.shape[0] - 20
                        for line in reversed(overlay_lines):
                            cv2.putText(annotated, line, (8, y_offset),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 136), 1,
                                        cv2.LINE_AA)
                            y_offset -= 20
                        
                        self.debug_frame_ready.emit(annotated)
                    else:
                        detected, confidence = self.engine.detect(frame)
                    
                    # Only evaluate threat state when NOT in debug mode
                    if not self.debug_mode:
                        self._evaluate_state(detected, confidence)
                    
                    # If detected, frame now has bounding boxes drawn by the engine
                    raw_frame = frame
            else:
                # Still emit raw frame for dashboard when paused, but mark it
                if raw_frame is not None:
                    # Add a small "PAUSED" text to the preview so the user knows
                    preview_frame = raw_frame.copy()
                    cv2.putText(preview_frame, "AI PAUSED", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                    self.frame_ready.emit(preview_frame)
            
            # Broadcast frame to virtual camera (BGR → RGB)
            if vcam is not None and raw_frame is not None:
                try:
                    rgb_frame = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2RGB)
                    # Resize to match virtual camera dimensions if needed
                    h, w = rgb_frame.shape[:2]
                    if w != vcam.width or h != vcam.height:
                        rgb_frame = cv2.resize(rgb_frame, (vcam.width, vcam.height))
                    vcam.send(rgb_frame)
                    vcam.sleep_until_next_frame()
                except Exception as e:
                    pass  # Silently skip frame on transient errors
            else:
                # Prevent 100% CPU lock in tight loops
                time.sleep(0.01)
        
        # Clean up virtual camera
        if vcam is not None:
            vcam.close()
            print("Virtual Camera closed.")

    def _evaluate_state(self, detected, confidence):
        """Applies heuristic validation (confidence thresholds & persistence)."""
        threshold, required_persistence, log_enabled, lockout_duration = self.get_settings()
        
        current_time = time.time()
        
        # 1. Is it a potential threat?
        is_high_confidence = detected and confidence >= threshold
        
        if is_high_confidence:
            self.consecutive_threat_frames += 1
            if confidence > self.max_threat_confidence:
                self.max_threat_confidence = confidence
                
            # If a threat is seen while the lockout timer is active, reset the timer
            if self.is_threat_active:
                self.lockout_end_time = current_time + lockout_duration
                
        else:
            # Quick decay: if phone disappears, drop threat frames rapidly.
            self.consecutive_threat_frames = 0
            
        # 2. State Machine Transitions
        if self.consecutive_threat_frames >= required_persistence:
            # Enter Threat State
            if not self.is_threat_active:
                self.is_threat_active = True
                self.incident_start_time = current_time
                self.lockout_end_time = current_time + lockout_duration
                self.threat_detected.emit(True, int(self.lockout_end_time - current_time))
                print(f"THREAT ENTERED: Score {self.max_threat_confidence:.2f}")
                
        elif self.consecutive_threat_frames == 0 and self.is_threat_active:
            # We are in active threat state, but no current visual threat.
            # Check the lockout timer.
            if current_time > self.lockout_end_time:
                # Exit Threat State
                duration = current_time - self.incident_start_time if self.incident_start_time else 0.0
                
                if log_enabled:
                    self.logger.log_threat("Cell phone visual intrusion", self.max_threat_confidence, duration)
                    print(f"THREAT EXITED: Duration {duration:.2f}s logged.")
                else:
                    print("THREAT EXITED: Logging disabled by user.")
                    
                self.is_threat_active = False
                self.incident_start_time = None
                self.max_threat_confidence = 0.0
                self.lockout_end_time = 0.0
                self.threat_detected.emit(False, 0)
        
        # Continuous signal emission to update the UI countdown timer while locked out
        if self.is_threat_active:
            remaining = int(self.lockout_end_time - current_time)
            # Prevent negative numbers from short timing glitches
            remaining = max(0, remaining)
            self.threat_detected.emit(True, remaining)

    def pause_monitoring(self):
        """Temporarily disables YOLO inference and threat evaluation, but keeps camera alive."""
        self.monitoring_active = False
        self.camera.pause()
        
        # Instantly resolve any active threats cleanly
        if self.is_threat_active:
            self.is_threat_active = False
            self.consecutive_threat_frames = 0
            self.incident_start_time = None
            self.max_threat_confidence = 0.0
            self.lockout_end_time = 0.0
            self.threat_detected.emit(False, 0)
            
    def resume_monitoring(self):
        """Re-enables YOLO inference."""
        self.monitoring_active = True
        self.camera.resume()

    def set_debug_mode(self, enabled: bool):
        """Toggles debug mode on/off. Debug mode pauses threat evaluation."""
        self.debug_mode = enabled
        if enabled:
            # Ensure camera stream is running for debug
            self.camera.resume()
            self.monitoring_active = False
            # Clear any active threats
            if self.is_threat_active:
                self.is_threat_active = False
                self.consecutive_threat_frames = 0
                self.incident_start_time = None
                self.max_threat_confidence = 0.0
                self.lockout_end_time = 0.0
                self.threat_detected.emit(False, 0)
        else:
            # Restore normal monitoring
            self.monitoring_active = True

    def request_camera_restart(self):
        self.pending_camera_restart = True
        
    def request_engine_restart(self):
        self.pending_model_restart = True

    def stop(self):
        """Safely shuts down the loop and releases hardware."""
        self.is_running = False
        self.camera.stop()
        self.quit()
        self.wait()
