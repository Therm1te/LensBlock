import sys
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from PyQt6.QtCore import Qt, QTimer, QObject
from PyQt6.QtGui import QColor, QPalette, QFont, QGuiApplication

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
        
        # Transparent background for the widget
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Set dark translucent overlay color
        self.setStyleSheet("background-color: rgba(20, 20, 20, 240);") # ~95% opacity black
        
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Threat Message text
        self.warning_label = QLabel("Visual Threat Detected.\nCamera in Field of View.")
        self.warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        font = QFont("Segoe UI", 36, QFont.Weight.Bold)
        self.warning_label.setFont(font)
        # Deep red color for high visibility on dark background
        self.warning_label.setStyleSheet("color: #FF3333; background-color: transparent;")
        
        layout.addWidget(self.warning_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
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

    def trigger_shield(self, is_active: bool):
        """Called by the main thread when a threat is detected or resolved."""
        if is_active:
            # Stop any fading out that might be occurring
            if self.fade_timer.isActive():
                self.fade_timer.stop()
                
            self.opacity = 1.0
            
            # Shield ON: Show on all screens robustly
            for shield in self.shields:
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
