import sys
import ctypes
import ctypes.wintypes
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt

def prompt():
    app = QApplication(sys.argv)
    w = QWidget()
    w.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
    w.setWindowOpacity(0.01)
    w.setGeometry(0, 0, 10, 10)
    w.show()
    # Force process events to render it
    QApplication.processEvents()

    credui = ctypes.windll.credui
    class CREDUI_INFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.wintypes.DWORD),
            ("hwndParent", ctypes.wintypes.HWND),
            ("pszMessageText", ctypes.c_wchar_p),
            ("pszCaptionText", ctypes.c_wchar_p),
            ("hbmBanner", ctypes.wintypes.HBITMAP),
        ]
    
    info = CREDUI_INFO()
    info.cbSize = ctypes.sizeof(CREDUI_INFO)
    info.hwndParent = int(w.winId())
    info.pszMessageText = "Please authenticate to safely bypass LensBlock monitoring."
    info.pszCaptionText = "LensBlock Manual Override"
    info.hbmBanner = None
    
    auth_pkg = ctypes.wintypes.ULONG(0)
    out_cred = ctypes.c_void_p()
    out_size = ctypes.wintypes.ULONG(0)
    save = ctypes.wintypes.BOOL(False)
    
    # 0x1 is CREDUIWIN_GENERIC
    res = credui.CredUIPromptForWindowsCredentialsW(
        ctypes.byref(info), 0, ctypes.byref(auth_pkg), None, 0,
        ctypes.byref(out_cred), ctypes.byref(out_size), ctypes.byref(save), 0x1
    )
    
    if out_cred:
        ctypes.windll.advapi32.CredFree(out_cred)
        
    sys.exit(res)

if __name__ == '__main__':
    prompt()
