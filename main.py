import sys
import argparse
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMessageBox, QStyle
)
from PyQt6.QtGui import QIcon, QAction, QPixmap
from PyQt6.QtCore import Qt

# Internal Imports
from config import ConfigHandler
from security.logger import ThreatLogger
from core.engine import YoloV8Engine # Ensure ONNX Runtime initializes early
from security.controller import SecurityController
from ui.dashboard import SettingsDashboard
from ui.shield import PrivacyShield

class LensBlockApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False) # Essential for tray applications
        
        # Set Taskbar Icon globally for all windows
        app_icon = QIcon('media/LensBlockBGRem.png')
        self.app.setWindowIcon(app_icon)
        
        self.config = ConfigHandler()
        self.logger = ThreatLogger()
        
        # 1. Initialize UI Components
        self.dashboard = SettingsDashboard(self.config, self.logger)
        self.shield = PrivacyShield()
        
        # 2. Setup System Tray
        self._init_tray()
        
        # 3. Initialize Background Controller Thread
        self.controller = SecurityController(self.config, self.logger)
        self._connect_signals()

        # Start background thread
        self.controller.start()

    def _init_tray(self):
        """Initializes the Windows System Tray Icon."""
        self.tray_icon = QSystemTrayIcon(self.app)
        
        # Set Tray Icon
        # Provide an explicit scaled Pixmap to force maximum available tray area rendering
        pixmap = QPixmap('media/LensBlockBGRem.png').scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.tray_icon.setIcon(QIcon(pixmap))
        self.tray_icon.setToolTip("LensBlock - System Armed")

        tray_menu = QMenu()
        
        # Actions
        open_action = QAction("Open Dashboard", self.app)
        open_action.triggered.connect(self.dashboard.show)
        tray_menu.addAction(open_action)

        self.pause_action = QAction("Pause Monitoring", self.app)
        self.pause_action.triggered.connect(self._pause_monitoring)
        tray_menu.addAction(self.pause_action)
        
        tray_menu.addSeparator()

        exit_action = QAction("Exit LensBlock", self.app)
        exit_action.triggered.connect(self._exit_app)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
        # Double-click tray to open dashboard
        self.tray_icon.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.dashboard.show()
            self.dashboard.raise_()
            self.dashboard.activateWindow()

    def _connect_signals(self):
        """Bind QThread signals from controller to UI Thread components."""
        self.controller.threat_detected.connect(self._on_threat_detected)
        self.controller.frame_ready.connect(self._on_frame_ready)
        
        # Disconnect previous controller bindings if they exist
        try:
            self.dashboard.restart_camera_requested.disconnect()
            self.dashboard.restart_engine_requested.disconnect()
            self.shield.override_triggered.disconnect()
        except TypeError:
            pass # No connections yet
            
        self.dashboard.restart_camera_requested.connect(self.controller.request_camera_restart)
        self.dashboard.restart_engine_requested.connect(self.controller.request_engine_restart)
        self.shield.override_triggered.connect(self.controller.clear_threat_state)

    def _on_threat_detected(self, is_active, remaining_seconds):
        """Fired in UI scale when controller toggles."""
        if is_active:
            # Trigger full-screen blackout lock
            self.shield.trigger_shield(True, remaining_seconds)
            self.dashboard.status_label.setText("System Status: LOCKDOWN")
            self.dashboard.status_label.setStyleSheet("color: #FF3333; font-weight: bold; font-size: 16px;")
        else:
            # Dissolve lock
            self.shield.trigger_shield(False, 0)
            self.dashboard.status_label.setText("System Status: ARMED")
            self.dashboard.status_label.setStyleSheet("color: #4caf50; font-weight: bold; font-size: 16px;")

    def _on_frame_ready(self, cv_frame):
        """If dashboard is open, stream frame to UI."""
        if self.dashboard.isVisible():
            self.dashboard.update_frame(cv_frame)

    def _pause_monitoring(self):
        """Temporarily pauses the camera processing."""
        if self.controller.is_running:
            self.controller.stop()
            self.pause_action.setText("Resume Monitoring")
            self.tray_icon.setToolTip("LensBlock - Paused")
            self.dashboard.status_label.setText("System Status: PAUSED")
            self.dashboard.status_label.setStyleSheet("color: #aaaaaa; font-weight: bold; font-size: 16px;")
            QMessageBox.information(None, "Paused", "Monitoring paused until restarted.")
        else:
            # Restart
            self.controller = SecurityController(self.config, self.logger)
            self._connect_signals()
            self.controller.start()
            self.pause_action.setText("Pause Monitoring")
            self.tray_icon.setToolTip("LensBlock - System Armed")
            self.dashboard.status_label.setText("System Status: ARMED")
            self.dashboard.status_label.setStyleSheet("color: #4caf50; font-weight: bold; font-size: 16px;")
            QMessageBox.information(None, "Resumed", "Monitoring resumed.")

    def _exit_app(self):
        """Clean shutdown mechanism."""
        self.controller.stop()
        self.tray_icon.hide()
        self.app.quit()

    def run(self):
        """Executes the PyQt Application Event Loop."""
        return self.app.exec()

if __name__ == "__main__":
    app = LensBlockApp()
    sys.exit(app.run())
