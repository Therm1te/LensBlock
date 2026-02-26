import time
from PyQt6.QtCore import QObject, pyqtSignal as Signal, QThread
from config import ConfigHandler
from security.logger import ThreatLogger
from core.engine import YoloV8Engine
from core.camera import CameraStream

class SecurityController(QThread):
    """
    Background worker thread that manages the camera stream, 
    inference loop, and threat persistence logic.
    Emits signals safely to the main GUI thread.
    """
    # Emits (is_threat_active, remaining_lockout_seconds)
    threat_detected = Signal(bool, int)
    frame_ready = Signal(object) # For updating the dashboard preview

    def __init__(self, config: ConfigHandler, logger: ThreatLogger):
        super().__init__()
        self.config = config
        self.logger = logger
        
        self.camera = CameraStream()
        self.engine = YoloV8Engine()
        
        self.is_running = False
        self.pending_camera_restart = False
        self.pending_model_restart = False
        
        # State variables
        self.consecutive_threat_frames = 0
        self.is_threat_active = False
        self.incident_start_time = None
        self.max_threat_confidence = 0.0
        self.lockout_end_time = 0.0
        self.override_until = 0.0

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

            frame = self.camera.read()
            if frame is None:
                time.sleep(0.01)
                continue
                
            # Emit raw frame for dashboard preview
            self.frame_ready.emit(frame)

            detected, confidence = self.engine.detect(frame)
            self._evaluate_state(detected, confidence)
            
            # Prevent 100% CPU lock in tight loops
            time.sleep(0.01)

    def _evaluate_state(self, detected, confidence):
        """Applies heuristic validation (confidence thresholds & persistence)."""
        current_time = time.time()
        
        # Immediate bypass if under Windows Hello Grace Period
        if current_time < self.override_until:
            return
            
        threshold, required_persistence, log_enabled, lockout_duration = self.get_settings()
        
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

    def request_camera_restart(self):
        self.pending_camera_restart = True
        
    def request_engine_restart(self):
        self.pending_model_restart = True

    def clear_threat_state(self, grace_period_seconds=300):
        """Called by UI when manual override succeeds. Ignores threats for a grace period."""
        self.override_until = time.time() + grace_period_seconds
        
        if self.is_threat_active:
            duration = time.time() - self.incident_start_time if self.incident_start_time else 0.0
            log_enabled = self.config.get('logging', 'enable_forensic_logging', True)
            if log_enabled:
                self.logger.log_threat("Cell phone visual intrusion - OVERRIDDEN", self.max_threat_confidence, duration)
            print("THREAT OVERRIDDEN by User via Windows Hello.")
            
        self.consecutive_threat_frames = 0
        self.is_threat_active = False
        self.incident_start_time = None
        self.max_threat_confidence = 0.0
        self.lockout_end_time = 0.0
        self.threat_detected.emit(False, 0)

    def stop(self):
        """Safely shuts down the loop and releases hardware."""
        self.is_running = False
        self.camera.stop()
        self.quit()
        self.wait()
