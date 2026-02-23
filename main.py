import sys
import argparse
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMessageBox, QStyle
)
from PyQt6.QtGui import QIcon, QAction

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
        
        # You'll usually replace this with a proper shield.ico file
        # Using a default message box icon as placeholder
        self.tray_icon.setIcon(self.app.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
        self.tray_icon.setToolTip("LensBlock - System Armed")

        tray_menu = QMenu()
        
        # Actions
        open_action = QAction("Open Dashboard", self.app)
        open_action.triggered.connect(self.dashboard.show)
        tray_menu.addAction(open_action)

        pause_action = QAction("Pause Monitoring", self.app)
        pause_action.triggered.connect(self._pause_monitoring)
        tray_menu.addAction(pause_action)
        
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

    def _on_threat_detected(self, is_active, confidence):
        """Fired in UI scale when controller toggles."""
        if is_active:
            # Trigger full-screen blackout lock
            self.shield.trigger_shield(True)
            self.dashboard.status_label.setText("System Status: LOCKDOWN")
            self.dashboard.status_label.setStyleSheet("color: #FF3333; font-weight: bold; font-size: 16px;")
        else:
            # Dissolve lock
            self.shield.trigger_shield(False)
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
            self.tray_icon.setToolTip("LensBlock - Paused")
            self.dashboard.status_label.setText("System Status: PAUSED")
            self.dashboard.status_label.setStyleSheet("color: #aaaaaa; font-weight: bold; font-size: 16px;")
            QMessageBox.information(None, "Paused", "Monitoring paused until restarted.")
        else:
            # Restart
            self.controller = SecurityController(self.config, self.logger)
            self._connect_signals()
            self.controller.start()
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
