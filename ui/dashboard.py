from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QCheckBox, QPushButton, QFrame, 
    QApplication, QStyle, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QIcon
from PyQt6.QtMultimedia import QMediaDevices
import cv2
import os

class SettingsDashboard(QWidget):
    """
    Main user-facing settings window.
    Allows configuring sensitivity, persistence, and viewing a camera preview.
    """
    restart_camera_requested = pyqtSignal()
    restart_engine_requested = pyqtSignal()
    mode_changed = pyqtSignal(str)  # Emits 'shield' or 'censorship'

    def __init__(self, config_handler, logger_instance):
        super().__init__()
        self.config = config_handler
        self.logger = logger_instance
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("LensBlock - Security Dashboard")
        self.setFixedSize(500, 450)
        
        # Dark theme styling
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                font-size: 14px;
            }
            QSlider::handle:horizontal {
                background: #4caf50;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #999999;
                height: 6px;
                background: #555555;
                margin: 0px 0;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:checked {
                background-color: #4caf50;
                border: 1px solid #4caf50;
            }
        """)

        layout = QVBoxLayout()
        self.setLayout(layout)

        # 1. Header Area
        header_layout = QHBoxLayout()
        
        self.status_label = QLabel("System Status: ARMED")
        self.status_label.setStyleSheet("color: #4caf50; font-weight: bold; font-size: 16px;")
        
        self.shield_icon = QIcon('media/LensBlockBGRem.png')
        self.icon_label = QLabel()
        self.icon_label.setPixmap(self.shield_icon.pixmap(80, 80))

        header_layout.addWidget(self.icon_label)
        header_layout.addWidget(self.status_label)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)

        # Separator line
        self._add_separator(layout)

        # 2. Hardware and Model Selectors
        hardware_layout = QHBoxLayout()
        
        # Camera Dropdown
        self.camera_combo = QComboBox()
        self.camera_combo.currentIndexChanged.connect(self._camera_changed)
        
        self.refresh_cam_btn = QPushButton("Refresh")
        self.refresh_cam_btn.setStyleSheet("background-color: #333333; padding: 4px; border-radius: 4px;")
        self.refresh_cam_btn.clicked.connect(self._populate_cameras)
        
        self._populate_cameras() # Initial population
        
        hardware_layout.addWidget(QLabel("Camera Source:"))
        hardware_layout.addWidget(self.camera_combo)
        hardware_layout.addWidget(self.refresh_cam_btn)
        
        # Model Dropdown
        self.model_combo = QComboBox()
        model_dir = "models"
        if os.path.exists(model_dir):
            onnx_models = [f for f in os.listdir(model_dir) if f.endswith(".onnx")]
            for model_file in onnx_models:
                # Add human readable text and proper relative path as data
                self.model_combo.addItem(model_file, f"{model_dir}/{model_file}")
                
        curr_model = self.config.get('detection', 'model_path', 'models/yolov8n.onnx')
        idx_found = self.model_combo.findData(curr_model)
        if idx_found >= 0:
            self.model_combo.setCurrentIndex(idx_found)
        self.model_combo.currentIndexChanged.connect(self._model_changed)
        
        hardware_layout.addWidget(QLabel("   ONNX Model:"))
        hardware_layout.addWidget(self.model_combo)
        
        layout.addLayout(hardware_layout)
        
        self._add_separator(layout)

        # 3. Controls Area
        # Sensitivity Slider
        sens_layout = QHBoxLayout()
        self.sens_label = QLabel(f"Detection Sensitivity:")
        
        self.sens_slider = QSlider(Qt.Orientation.Horizontal)
        self.sens_slider.setRange(50, 90)
        # Load setting (0.60 -> 60)
        curr_sens = int(self.config.get('detection', 'confidence_threshold', 0.60) * 100)
        self.sens_slider.setValue(curr_sens)
        
        self.sens_value_label = QLabel(f"{curr_sens}%")
        self.sens_slider.valueChanged.connect(self._sens_changed)

        sens_layout.addWidget(self.sens_label)
        sens_layout.addWidget(self.sens_slider)
        sens_layout.addWidget(self.sens_value_label)
        layout.addLayout(sens_layout)

        # Persistence Slider
        pers_layout = QHBoxLayout()
        self.pers_label = QLabel(f"Persistence Threshold:")
        
        self.pers_slider = QSlider(Qt.Orientation.Horizontal)
        self.pers_slider.setRange(1, 5)
        # Load setting
        curr_pers = self.config.get('detection', 'persistence_frames', 3)
        self.pers_slider.setValue(curr_pers)
        
        self.pers_value_label = QLabel(f"{curr_pers} frames")
        self.pers_slider.valueChanged.connect(self._pers_changed)

        pers_layout.addWidget(self.pers_label)
        pers_layout.addWidget(self.pers_slider)
        pers_layout.addWidget(self.pers_value_label)
        layout.addLayout(pers_layout)

        # Separator Line
        self._add_separator(layout)
        
        # 3. Switches and Logs
        self.log_checkbox = QCheckBox("Enable Forensic SQLite Logging")
        self.log_checkbox.setChecked(self.config.get('logging', 'enable_forensic_logging', True))
        self.log_checkbox.stateChanged.connect(self._log_toggled)
        layout.addWidget(self.log_checkbox)

        self.boot_checkbox = QCheckBox("Start on Boot (Windows)")
        self.boot_checkbox.setChecked(self.config.get('system', 'start_on_boot', False))
        self.boot_checkbox.stateChanged.connect(self._boot_toggled)
        layout.addWidget(self.boot_checkbox)

        self.debug_btn = QPushButton("Enable Debug View")
        self.debug_btn.setStyleSheet("background-color: #333333; padding: 8px; border-radius: 4px;")
        self._debug_active = False
        self.debug_btn.clicked.connect(self._debug_toggled)
        layout.addWidget(self.debug_btn)

        # View Logs Button
        self.logs_btn = QPushButton("View Recent Logs")
        self.logs_btn.setStyleSheet("background-color: #333333; padding: 8px; border-radius: 4px;")
        self.logs_btn.clicked.connect(self._show_logs)
        layout.addWidget(self.logs_btn)
        
        # Separator
        self._add_separator(layout)
        
        # 4. Preview Window
        # Note: UIUX recommends blurred by default, but for simplicty we'll just show a "Video Source Active" label
        # The QImage preview will be connected to the controller's frame_ready signal.
        preview_label_title = QLabel("Live Threat Monitor (Blurred for Privacy)")
        preview_label_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_label_title.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        layout.addWidget(preview_label_title)
        
        self.preview_window = QLabel()
        self.preview_window.setFixedSize(320, 180) # 16:9 ratio preview
        self.preview_window.setStyleSheet("background-color: #000000; border: 1px solid #555;")
        self.preview_window.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_window.setText("Waiting for Camera...")
        
        # Center the preview
        preview_layout = QHBoxLayout()
        preview_layout.addStretch()
        preview_layout.addWidget(self.preview_window)
        preview_layout.addStretch()
        
        layout.addLayout(preview_layout)

    def _populate_cameras(self):
        """Discovers and populates the camera dropdown."""
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        
        # 1. Try QtMultimedia first (good for real names of physical devices)
        cameras = QMediaDevices.videoInputs()
        qt_found = len(cameras)
        
        if cameras:
            for i, cam in enumerate(cameras):
                desc = cam.description()
                name = desc if desc else f"Camera {i}"
                self.camera_combo.addItem(name, i)
                
        # 2. Fallback / Augment with OpenCV DirectShow (catches OBS Virtual Camera better on Windows)
        # We'll check up to index 4. If Qt found it, we might double-list, but it ensures virtual cams appear.
        for i in range(qt_found, 5): 
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                self.camera_combo.addItem(f"DShow Camera {i}", i)
                cap.release()
                
        # 3. Absolute Fallback if nothing at all
        if self.camera_combo.count() == 0:
            for i in range(5):
                self.camera_combo.addItem(f"Unknown Camera {i}", i)
                
        curr_cam = self.config.get('system', 'camera_index', 0)
        idx_found = self.camera_combo.findData(curr_cam)
        if idx_found >= 0:
            self.camera_combo.setCurrentIndex(idx_found)
            
        self.camera_combo.blockSignals(False)

    def _camera_changed(self, index):
        cam_idx = self.camera_combo.itemData(index)
        self.config.set('system', 'camera_index', cam_idx)
        self.restart_camera_requested.emit()
        
    def _model_changed(self, index):
        model_path = self.model_combo.itemData(index)
        self.config.set('detection', 'model_path', model_path)
        self.restart_engine_requested.emit()

    def _debug_toggled(self):
        self._debug_active = not self._debug_active
        if self._debug_active:
            self.debug_btn.setText("Disable Debug View")
            self.debug_btn.setStyleSheet("background-color: #1a4d2e; padding: 8px; border-radius: 4px;")
        else:
            self.debug_btn.setText("Enable Debug View")
            self.debug_btn.setStyleSheet("background-color: #333333; padding: 8px; border-radius: 4px;")
        self.debug_mode_toggled.emit(self._debug_active)

    def _add_separator(self, layout):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #333333;")
        layout.addWidget(line)

    def _sens_changed(self, value):
        self.sens_value_label.setText(f"{value}%")
        # Save dynamically 
        self.config.set('detection', 'confidence_threshold', value / 100.0)

    def _pers_changed(self, value):
        self.pers_value_label.setText(f"{value} frames")
        self.config.set('detection', 'persistence_frames', value)
        
    def _log_toggled(self, state):
        val = bool(state)
        self.config.set('logging', 'enable_forensic_logging', val)

    def _boot_toggled(self, state):
        val = bool(state)
        self.config.set('system', 'start_on_boot', val)
        
    def _show_logs(self):
        logs = self.logger.get_recent_logs(limit=5)
        
        if not logs:
            QMessageBox.information(self, "Recent Logs", "No threats recorded in the database.")
            return
            
        msg = "Recent Security Violations:\n\n"
        for log in logs:
            # ID | Time | Type | Conf | Duration
            # e.g., [1745] Cell phone (87%): 2.5s
            ts = log[1].split('T')[1][:8] # Extract just time from ISO format
            conf = int(log[3] * 100)
            msg += f"[{ts}] {log[2]} ({conf}% confidence) - Duration: {log[4]:.1f}s\n"
            
        QMessageBox.information(self, "Recent Logs", msg)

    def update_frame(self, cv_frame):
        """Called by the main thread via signal from the controller."""
        # Optional: apply blur based on UX spec
        blurred = cv2.GaussianBlur(cv_frame, (51, 51), 0)
        
        # Convert OpenCV BGR format to Qt Format
        rgb_image = cv2.cvtColor(blurred, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        
        # Create QImage from buffer
        # Keep reference to the Python wrapper alive
        self.__last_frame = rgb_image 
        q_img = QImage(self.__last_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        
        # Scale down for preview
        pixmap = QPixmap.fromImage(q_img).scaled(
            self.preview_window.size(), 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        self.preview_window.setPixmap(pixmap)
        
    def closeEvent(self, event):
        """Hide instead of close, we want the system tray to handle exiting."""
        event.ignore()
        self.hide()
