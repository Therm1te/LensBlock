import sys
import ctypes
import ctypes.wintypes
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton
from PyQt6.QtCore import Qt, QTimer

class CREDUI_INFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("hwndParent", ctypes.wintypes.HWND),
        ("pszMessageText", ctypes.c_wchar_p),
        ("pszCaptionText", ctypes.c_wchar_p),
        ("hbmBanner", ctypes.wintypes.HBITMAP),
    ]

class TopW(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(500, 500)
        self.setStyleSheet("background-color: black;")
        btn = QPushButton("Click", self)
        btn.clicked.connect(self.cl)
        
    def cl(self):
        credui = ctypes.windll.credui
        info = CREDUI_INFO()
        info.cbSize = ctypes.sizeof(CREDUI_INFO)
        info.hwndParent = int(self.winId())
        info.pszMessageText = "Please authenticate"
        info.pszCaptionText = "LensBlock Manual Override"
        
        auth_pkg = ctypes.wintypes.ULONG(0)
        out_cred = ctypes.c_void_p()
        out_size = ctypes.wintypes.ULONG(0)
        save = ctypes.wintypes.BOOL(False)
        
        print("Starting CredUI on Main Thread")
        res = credui.CredUIPromptForWindowsCredentialsW(
            ctypes.byref(info), 0, ctypes.byref(auth_pkg), None, 0,
            ctypes.byref(out_cred), ctypes.byref(out_size), ctypes.byref(save), 0x1
        )
        print("CredUI returned:", res)
        if out_cred:
            ctypes.windll.credui.CredFree(out_cred)

app = QApplication(sys.argv)
w = TopW()
w.show()
QTimer.singleShot(500, w.cl)
QTimer.singleShot(4000, app.quit)
app.exec()
