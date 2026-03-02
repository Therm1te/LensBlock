import time
import cv2
from enum import Enum
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


class ProtectionMode(Enum):
    SHIELD = "shield"        # v1: Full-screen blackout overlay
    CENSORSHIP = "censorship"  # v2: Real-time object blurring on stream


class SecurityController(QThread):
    """
    Background worker thread that manages the camera stream, 
    inference loop, and threat persistence logic.
    Emits signals safely to the main GUI thread.
    """
    # Emits (is_threat_active, remaining_lockout_seconds)
    threat_detected = Signal(bool, int)
    frame_ready = Signal(object)          # For updating the dashboard preview
    censored_frame_ready = Signal(object)  # Emits annotated censored frame for dashboard
    mode_changed = Signal(str)             # Emits new mode name for UI feedback

    def __init__(self, config: ConfigHandler, logger: ThreatLogger):
        super().__init__()
        self.config = config
        self.logger = logger
        
        self.camera = CameraStream()
        self.engine = YoloV8Engine()
        
        self.is_running = False
        self.monitoring_active = True
        self.protection_mode = ProtectionMode.SHIELD
        self.pending_camera_restart = False
        self.pending_model_restart = False
        
        # State variables
        self.consecutive_threat_frames = 0
        self.is_threat_active = False
        self.incident_start_time = None
        self.max_threat_confidence = 0.0
        self.lockout_end_time = 0.0

        # Block-first: keep the last safe (censored) frame for vcam fallback
        self._last_safe_frame = None

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
        
        # Initialize virtual camera at the camera's native resolution
        vcam = None
        if VIRTUAL_CAM_AVAILABLE:
            try:
                cam_w = int(self.camera.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if self.camera.cap else 640
                cam_h = int(self.camera.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if self.camera.cap else 480
                vcam = pyvirtualcam.Camera(width=cam_w, height=cam_h, fps=30, fmt=pyvirtualcam.PixelFormat.RGB)
                print(f"Virtual Camera started: {vcam.device} ({cam_w}x{cam_h})")
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

            if self.monitoring_active:
                frame = self.camera.read()
                if frame is not None:
                    # Emit raw frame for dashboard preview
                    self.frame_ready.emit(frame)

                    if self.protection_mode == ProtectionMode.SHIELD:
                        # v1: Standard detection → trigger full-screen shield
                        detected, confidence = self.engine.detect(frame)
                        self._evaluate_state(detected, confidence)
                        raw_frame = frame
                        
                        # In SHIELD mode during lockdown, send a "PRIVACY BLOCKED" frame to vcam
                        if self.is_threat_active and vcam is not None:
                            blocked_frame = frame.copy()
                            blocked_frame[:] = (15, 23, 42)  # Dark slate color matching shield
                            cv2.putText(blocked_frame, "PRIVACY BLOCKED", 
                                       (blocked_frame.shape[1]//2 - 180, blocked_frame.shape[0]//2),
                                       cv2.FONT_HERSHEY_SIMPLEX, 1.2, (239, 68, 68), 2, cv2.LINE_AA)
                            raw_frame = blocked_frame

                    elif self.protection_mode == ProtectionMode.CENSORSHIP:
                        # v2: Detect + blur threat regions with temporal memory
                        t_start = time.perf_counter()
                        detected, confidence, clean_frame, annotated_preview, det_count = self.engine.detect_and_censor(frame)
                        inference_ms = (time.perf_counter() - t_start) * 1000
                        
                        # Block-first logic: if inference took > 50ms, use the
                        # last known-safe frame to prevent raw frame leakage
                        if inference_ms > 50 and self._last_safe_frame is not None:
                            raw_frame = self._last_safe_frame
                        else:
                            raw_frame = clean_frame
                            self._last_safe_frame = clean_frame.copy()
                        
                        # Log threats the same way, but do NOT trigger the shield
                        threshold, _, log_enabled, _ = self.get_settings()
                        if detected and confidence >= threshold:
                            if not self.is_threat_active:
                                self.is_threat_active = True
                                self.incident_start_time = time.time()
                                self.max_threat_confidence = confidence
                        elif not detected and self.is_threat_active:
                            duration = time.time() - self.incident_start_time if self.incident_start_time else 0.0
                            if log_enabled:
                                self.logger.log_threat("Cell phone visual intrusion (censored)", self.max_threat_confidence, duration)
                            self.is_threat_active = False
                            self.incident_start_time = None
                            self.max_threat_confidence = 0.0
                        
                        # Add mode indicator overlay on the PREVIEW only (not vcam)
                        active_count = len(self.engine.active_threats)
                        status = f"CENSORSHIP | Active Redactions: {active_count}"
                        cv2.putText(annotated_preview, status, (10, 25),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 200), 1, cv2.LINE_AA)
                        
                        # Annotated preview goes to dashboard
                        self.censored_frame_ready.emit(annotated_preview)
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

    def set_protection_mode(self, mode: ProtectionMode):
        """Switch between SHIELD and CENSORSHIP modes."""
        self.protection_mode = mode
        # Clear threat memory when switching modes
        self.engine.clear_threat_memory()
        self._last_safe_frame = None
        # If switching away from SHIELD and threat is active, clear it
        if mode == ProtectionMode.CENSORSHIP and self.is_threat_active:
            self.is_threat_active = False
            self.consecutive_threat_frames = 0
            self.incident_start_time = None
            self.max_threat_confidence = 0.0
            self.lockout_end_time = 0.0
            self.threat_detected.emit(False, 0)
        self.mode_changed.emit(mode.value)
        print(f"Protection mode changed to: {mode.value.upper()}")

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
