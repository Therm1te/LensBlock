import time
import cv2
import numpy as np
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
    SHIELD = "shield"          # v1: Full-screen blackout
    CENSORSHIP = "censorship"  # v2: Real-time object blurring

class SecurityController(QThread):
    """
    Background worker thread that manages the camera stream, 
    inference loop, and threat persistence logic.
    Emits signals safely to the main GUI thread.
    """
    # Emits (is_threat_active, remaining_lockout_seconds)
    threat_detected = Signal(bool, int)
    frame_ready = Signal(object)           # For updating the dashboard preview
    censored_frame_ready = Signal(object)  # Censored frame for vcam preview

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
        
        # Censorship mode state
        self._active_threats = {}   # id -> {"box": (x1,y1,x2,y2), "cooldown": int}
        self._next_threat_id = 0
        self._last_censored_frame = None  # Frame-drop fallback
        self._censor_cooldown_frames = 10
        self._roi_padding = 0.20    # 20% expansion

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
        
        # Initialize virtual camera matching real camera resolution
        vcam = None
        cam_w = getattr(self.camera, 'actual_width', 640)
        cam_h = getattr(self.camera, 'actual_height', 480)
        if VIRTUAL_CAM_AVAILABLE:
            try:
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

                    if self.protection_mode == ProtectionMode.CENSORSHIP:
                        # --- CENSORSHIP MODE with temporal buffer ---
                        threshold = self.get_settings()[0]
                        
                        # Time the inference for frame-drop prevention
                        t_start = time.time()
                        detected, confidence, boxes = self.engine.detect_with_boxes(frame, conf_threshold=threshold)
                        inference_ms = (time.time() - t_start) * 1000
                        
                        # If inference took too long, use the last safe frame
                        if inference_ms > 50 and self._last_censored_frame is not None:
                            self.censored_frame_ready.emit(self._last_censored_frame)
                            raw_frame = self._last_censored_frame
                        else:
                            # --- 1. Update threat memory with IoU matching ---
                            matched_ids = set()
                            for box in boxes:
                                best_iou = 0.0
                                best_id = None
                                for tid, tdata in self._active_threats.items():
                                    iou = self._compute_iou(box, tdata["box"])
                                    if iou > best_iou:
                                        best_iou = iou
                                        best_id = tid
                                
                                if best_iou > 0.3 and best_id is not None:
                                    # Update existing threat
                                    self._active_threats[best_id]["box"] = box
                                    self._active_threats[best_id]["cooldown"] = 0
                                    matched_ids.add(best_id)
                                else:
                                    # New threat
                                    self._active_threats[self._next_threat_id] = {"box": box, "cooldown": 0}
                                    matched_ids.add(self._next_threat_id)
                                    self._next_threat_id += 1
                            
                            # Age unmatched threats
                            expired = []
                            for tid, tdata in self._active_threats.items():
                                if tid not in matched_ids:
                                    tdata["cooldown"] += 1
                                    if tdata["cooldown"] > self._censor_cooldown_frames:
                                        expired.append(tid)
                            for tid in expired:
                                del self._active_threats[tid]
                            
                            # --- 2. Build censored frame from all active threats ---
                            sanitized = raw_frame.copy() if raw_frame is not None else frame.copy()
                            fh, fw = sanitized.shape[:2]
                            
                            for tdata in self._active_threats.values():
                                x1, y1, x2, y2 = tdata["box"]
                                
                                # ROI padding (20% expansion)
                                bw = x2 - x1
                                bh = y2 - y1
                                pad_x = int(bw * self._roi_padding)
                                pad_y = int(bh * self._roi_padding)
                                x1 = max(0, x1 - pad_x)
                                y1 = max(0, y1 - pad_y)
                                x2 = min(fw, x2 + pad_x)
                                y2 = min(fh, y2 + pad_y)
                                
                                # Heavy triple-stacked blur (irreversible by AI sharpening)
                                roi = sanitized[y1:y2, x1:x2]
                                if roi.size > 0:
                                    blurred = cv2.GaussianBlur(roi, (99, 99), 0)
                                    blurred = cv2.GaussianBlur(blurred, (99, 99), 0)
                                    blurred = cv2.GaussianBlur(blurred, (99, 99), 0)
                                    sanitized[y1:y2, x1:x2] = blurred
                            
                            self._last_censored_frame = sanitized
                            self.censored_frame_ready.emit(sanitized)
                            raw_frame = sanitized
                        
                        # Log if detected (but DON'T trigger the shield)
                        if detected:
                            _, _, log_enabled, _ = self.get_settings()
                            if not self.is_threat_active:
                                self.is_threat_active = True
                                self.incident_start_time = time.time()
                                self.max_threat_confidence = confidence
                            elif confidence > self.max_threat_confidence:
                                self.max_threat_confidence = confidence
                        else:
                            # Only log exit if all threats have fully cooled down
                            if self.is_threat_active and len(self._active_threats) == 0:
                                duration = time.time() - self.incident_start_time if self.incident_start_time else 0.0
                                _, _, log_enabled, _ = self.get_settings()
                                if log_enabled:
                                    self.logger.log_threat("Cell phone visual intrusion (censored)", self.max_threat_confidence, duration)
                                self.is_threat_active = False
                                self.incident_start_time = None
                                self.max_threat_confidence = 0.0
                    else:
                        # --- SHIELD MODE: v1 full-screen blackout ---
                        detected, confidence = self.engine.detect(frame)
                        self._evaluate_state(detected, confidence)
                        raw_frame = frame
                        
                        # During shield lockdown, send a black "PRIVACY BLOCKED" frame to vcam
                        if self.is_threat_active:
                            blocked = np.zeros((cam_h, cam_w, 3), dtype=np.uint8)
                            tx = cam_w // 2 - 150
                            ty = cam_h // 2
                            cv2.putText(blocked, "PRIVACY BLOCKED", (tx, ty),
                                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (50, 50, 200), 3, cv2.LINE_AA)
                            raw_frame = blocked
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
        """Switch between Shield and Censorship modes."""
        self.protection_mode = mode
        # Reset threat state cleanly when switching modes
        if self.is_threat_active:
            self.is_threat_active = False
            self.consecutive_threat_frames = 0
            self.incident_start_time = None
            self.max_threat_confidence = 0.0
            self.lockout_end_time = 0.0
            self.threat_detected.emit(False, 0)
        # Reset censorship memory
        self._active_threats.clear()
        self._last_censored_frame = None
        print(f"Protection mode changed to: {mode.value}")

    @staticmethod
    def _compute_iou(box_a, box_b):
        """Compute Intersection over Union between two (x1,y1,x2,y2) boxes."""
        xa = max(box_a[0], box_b[0])
        ya = max(box_a[1], box_b[1])
        xb = min(box_a[2], box_b[2])
        yb = min(box_a[3], box_b[3])
        inter = max(0, xb - xa) * max(0, yb - ya)
        area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
        area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

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
