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
    threat_detected = Signal(bool, float) # (is_threat_active, max_confidence)
    frame_ready = Signal(object) # For updating the dashboard preview

    def __init__(self, config: ConfigHandler, logger: ThreatLogger):
        super().__init__()
        self.config = config
        self.logger = logger
        
        self.camera = CameraStream()
        self.engine = YoloV8Engine()
        
        self.is_running = False
        
        # State variables
        self.consecutive_threat_frames = 0
        self.is_threat_active = False
        self.incident_start_time = None
        self.max_threat_confidence = 0.0

    def get_settings(self):
        """Fetches dynamic settings that the user might have updated."""
        threshold = self.config.get('detection', 'confidence_threshold', 0.60)
        persistence = self.config.get('detection', 'persistence_frames', 3)
        log_enabled = self.config.get('logging', 'enable_forensic_logging', True)
        return threshold, persistence, log_enabled

    def run(self):
        """Main QThread execution loop."""
        if not self.camera.start():
            print("Failed to start camera stream. Controller aborting.")
            return

        self.is_running = True
        
        while self.is_running:
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
        threshold, required_persistence, log_enabled = self.get_settings()
        
        # 1. Is it a potential threat?
        is_high_confidence = detected and confidence >= threshold
        
        if is_high_confidence:
            self.consecutive_threat_frames += 1
            if confidence > self.max_threat_confidence:
                self.max_threat_confidence = confidence
        else:
            # Quick decay: if phone disappears, drop threat frames rapidly.
            # E.g., drops completely to 0 immediately or decays by 1. For safety, we drop immediately.
            self.consecutive_threat_frames = 0
            
        # 2. State Machine Transitions
        if self.consecutive_threat_frames >= required_persistence:
            # Enter Threat State
            if not self.is_threat_active:
                self.is_threat_active = True
                self.incident_start_time = time.time()
                self.threat_detected.emit(True, self.max_threat_confidence)
                print(f"THREAT ENTERED: Score {self.max_threat_confidence:.2f}")
                
        elif self.consecutive_threat_frames == 0 and self.is_threat_active:
            # Exit Threat State
            duration = time.time() - self.incident_start_time if self.incident_start_time else 0.0
            
            if log_enabled:
                self.logger.log_threat("Cell phone visual intrusion", self.max_threat_confidence, duration)
                print(f"THREAT EXITED: Duration {duration:.2f}s logged.")
            else:
                print("THREAT EXITED: Logging disabled by user.")
                
            self.is_threat_active = False
            self.incident_start_time = None
            self.max_threat_confidence = 0.0
            self.threat_detected.emit(False, 0.0)

    def stop(self):
        """Safely shuts down the loop and releases hardware."""
        self.is_running = False
        self.camera.stop()
        self.quit()
        self.wait()
