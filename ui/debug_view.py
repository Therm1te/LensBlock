"""
Debug View Window for LensBlock.
A small always-on-top window showing live YOLO-annotated frames
with FPS, status, and detection count overlays.
"""
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap, QGuiApplication
import cv2


class DebugView(QWidget):
    """
    A compact, always-on-top debug window positioned in the bottom-right
    corner of the primary screen showing annotated YOLO detection frames.
    """
    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("LensBlock - Debug View")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
        )

        self.resize(720, 480)
        self.setMinimumSize(400, 260)
        self.setStyleSheet("background-color: #0a0a0a;")

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        self.setLayout(layout)

        # Title bar
        self.title_label = QLabel("DEBUG MODE")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet(
            "color: #00ff88; font-size: 11px; font-weight: bold; "
            "font-family: 'Consolas'; background: transparent;"
        )
        layout.addWidget(self.title_label)

        # Video frame display
        self.frame_label = QLabel()
        self.frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.frame_label.setStyleSheet(
            "background-color: #111111; border: 1px solid #00ff88; "
            "color: #555555; font-family: 'Consolas';"
        )
        self.frame_label.setText("Waiting for frames...")
        layout.addWidget(self.frame_label)

        # Position in bottom-right corner of primary screen
        self._snap_to_corner()

    def _snap_to_corner(self):
        """Places the window in the bottom-right corner of the primary screen."""
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + geo.width() - self.width() - 10
            y = geo.y() + geo.height() - self.height() - 10
            self.move(x, y)

    def update_frame(self, cv_frame):
        """
        Receives a BGR OpenCV frame (already annotated with bounding boxes
        and info overlay by the controller) and renders it.
        """
        rgb = cv2.cvtColor(cv_frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bpl = ch * w

        # Must keep a reference so the buffer stays alive
        self._last_frame = rgb
        q_img = QImage(self._last_frame.data, w, h, bpl, QImage.Format.Format_RGB888)

        pixmap = QPixmap.fromImage(q_img).scaled(
            self.frame_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.frame_label.setPixmap(pixmap)
