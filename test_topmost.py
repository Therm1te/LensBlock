import sys
import ctypes
import ctypes.wintypes
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, QThread

class CREDUI_INFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("hwndParent", ctypes.wintypes.HWND),
        ("pszMessageText", ctypes.c_wchar_p),
        ("pszCaptionText", ctypes.c_wchar_p),
        ("hbmBanner", ctypes.wintypes.HBITMAP),
    ]

class AuthThread(QThread):
    def run(self):
        credui = ctypes.windll.credui
        info = CREDUI_INFO()
        info.cbSize = ctypes.sizeof(CREDUI_INFO)
        info.hwndParent = None
        info.pszMessageText = "Please authenticate"
        info.pszCaptionText = "LensBlock Manual Override"
        auth_pkg, out_cred, out_size, save = ctypes.wintypes.ULONG(0), ctypes.c_void_p(), ctypes.wintypes.ULONG(0), ctypes.wintypes.BOOL(False)
        print("Starting CredUI")
        credui.CredUIPromptForWindowsCredentialsW(ctypes.byref(info), 0, ctypes.byref(auth_pkg), None, 0, ctypes.byref(out_cred), ctypes.byref(out_size), ctypes.byref(save), 0x1)
        print("Done auth")

class TopW(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(500, 500)
        btn = QPushButton("Click", self)
        btn.clicked.connect(self.cl)
        
        self.t = QTimer()
        self.t.timeout.connect(self.lift)
        
    def cl(self):
        self.th = AuthThread()
        self.th.start()
        self.t.start(100)

    def lift(self):
        # find the window and lift it
        hwnd = ctypes.windll.user32.FindWindowW(None, "Windows Security")
        if hwnd:
            # HWND_TOPMOST = -1
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0002 | 0x0001)
            self.t.stop()
            print("LIFTED SECURITY!")
            
app = QApplication(sys.argv)
w = TopW()
w.show()
QTimer.singleShot(500, w.cl)
QTimer.singleShot(4000, app.quit)
app.exec()
