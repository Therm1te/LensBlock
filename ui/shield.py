import sys
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from PyQt6.QtCore import Qt, QTimer, QObject
from PyQt6.QtGui import QColor, QPalette, QFont, QGuiApplication, QPixmap

class ShieldWindow(QWidget):
    """
    A full-screen, always-on-top overlay that visually blocks the screen when a threat is detected.
    It uses a heavy translucent dark effect.
    """
    def __init__(self, screen_obj):
        super().__init__()
        self.screen_obj = screen_obj
        self._init_ui()

    def _init_ui(self):
        # Remove window borders and frame
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool | # Tool prevents it from showing in taskbar
            Qt.WindowType.X11BypassWindowManagerHint
        )
        
        # Set solid slate overlay color
        self.setStyleSheet("background-color: #0f172a;")
        
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setLayout(layout)
        
        # Icon
        self.icon_label = QLabel()
        pixmap = QPixmap('media/LensBlockBGRem.png').scaled(
            128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.icon_label.setPixmap(pixmap)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)
        
        # Header
        self.header_label = QLabel("VISUAL THREAT DETECTED")
        self.header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_label.setStyleSheet("color: #ef4444; font-size: 32px; font-weight: bold; font-family: 'Segoe UI'; background-color: transparent;")
        layout.addWidget(self.header_label)
        
        # Subtext
        self.subtext_label = QLabel("A recording device has entered the secure monitoring zone. Please remove the device to resume work.")
        self.subtext_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtext_label.setStyleSheet("color: #94a3b8; font-size: 16px; font-family: 'Segoe UI'; background-color: transparent;")
        layout.addWidget(self.subtext_label)
        
        # Lockout Timer text
        self.lockout_label = QLabel("System locked for 0 seconds.")
        self.lockout_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lockout_label.setStyleSheet("color: #ffffff; font-size: 24px; font-weight: bold; font-family: 'Consolas'; margin-top: 20px; background-color: transparent;")
        layout.addWidget(self.lockout_label)
        
        # Initialize opacity
        self.opacity = 0.0
        self.setWindowOpacity(self.opacity)
        
        # Snap to specific monitor
        self.setGeometry(self.screen_obj.geometry())

    def mousePressEvent(self, event):
        """Intercept clicks so user cannot interact with masked content."""
        event.accept()
        
    def keyPressEvent(self, event):
        """Intercept key presses."""
        event.accept()

class PrivacyShield(QObject):
    """
    Manager class that handles rendering ShieldWindows across all active monitors simultaneously.
    """
    def __init__(self):
        super().__init__()
        self.shields = []
        
        # Initialize one overlay per screen
        for screen in QGuiApplication.screens():
            shield = ShieldWindow(screen)
            self.shields.append(shield)
            
        self.opacity = 0.0
        
        # Create a single persistent timer for fading to prevent memory leaks/orphaned timers
        self.fade_timer = QTimer(self)
        self.fade_timer.timeout.connect(self._do_fade)

    def trigger_shield(self, is_active: bool, remaining_seconds: int = 0):
        """Called by the main thread when a threat is detected or resolved."""
        if is_active:
            # Stop any fading out that might be occurring
            if self.fade_timer.isActive():
                self.fade_timer.stop()
                
            self.opacity = 1.0
            
            # Shield ON: Show on all screens robustly
            for shield in self.shields:
                shield.lockout_label.setText(f"System locked for {remaining_seconds} seconds.")
                # Re-assert geometry just in case screen resolution changed
                shield.setGeometry(shield.screen_obj.geometry())
                shield.setWindowOpacity(1.0)
                shield.opacity = 1.0
                shield.show()
                shield.raise_()
                shield.activateWindow()
        else:
            # Fade out
            self.fade_out()

    def fade_out(self):
        """Gradually fades out all shields to prevent jarring transitions."""
        if not self.fade_timer.isActive():
            self.opacity = 1.0
            self.fade_timer.start(10) # 10ms intervals

    def _do_fade(self):
        self.opacity -= 0.05
        if self.opacity <= 0.0:
            self.opacity = 0.0
            self.fade_timer.stop()
            for shield in self.shields:
                shield.setWindowOpacity(self.opacity)
                shield.hide() # Completely hide it so clicks pass through normally
        else:
            for shield in self.shields:
                shield.setWindowOpacity(self.opacity)
