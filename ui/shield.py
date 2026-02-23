import sys
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation
from PyQt6.QtGui import QColor, QPalette, QFont

class PrivacyShield(QWidget):
    """
    A full-screen, always-on-top overlay that visually blocks the screen when a threat is detected.
    It uses a heavy translucent dark effect.
    """
    def __init__(self):
        super().__init__()
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
        
        # Initialize animation variables
        self.opacity = 0.0
        self.setWindowOpacity(self.opacity)

    def trigger_shield(self, is_active: bool):
        """Called by the main thread when a threat is detected or resolved."""
        if is_active:
            # Show on all screens
            # To cover multiple monitors, we typically grab the geometry of the entire desktop
            screen_geometry = QApplication.primaryScreen().virtualGeometry()
            self.setGeometry(screen_geometry)
            self.show()
            self.setWindowOpacity(1.0) # Instant snap ON
        else:
            # Fade out
            self.fade_out()

    def fade_out(self):
        """Gradually fades out the shield to prevent jarring transitions."""
        # We manually animate since QPropertyAnimation on WindowOpacity can be tricky on some OSs.
        self.opacity = 1.0
        self.fade_timer = QTimer(self)
        self.fade_timer.timeout.connect(self._do_fade)
        self.fade_timer.start(10) # 10ms intervals

    def _do_fade(self):
        self.opacity -= 0.05
        if self.opacity <= 0.0:
            self.opacity = 0.0
            self.setWindowOpacity(self.opacity)
            self.fade_timer.stop()
            self.hide() # Completely hide it so clicks pass through normally
        else:
            self.setWindowOpacity(self.opacity)
            
    def mousePressEvent(self, event):
        """Intercept clicks so user cannot interact with masked content."""
        event.accept()
        
    def keyPressEvent(self, event):
        """Intercept key presses."""
        event.accept()

