import win32cred
import pywintypes
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton
import sys

def prompt_auth(hwnd):
    cpi = {
        'MessageText': 'Please authenticate to safely bypass LensBlock monitoring.',
        'CaptionText': 'LensBlock Manual Override',
        'hwndParent': hwnd
    }
    
    # CREDUI_FLAGS_GENERIC_CREDENTIALS = 0x2
    # CREDUI_FLAGS_ALWAYS_SHOW_UI = 0x1
    # CREDUI_FLAGS_DO_NOT_PERSIST = 0x10
    flags = 0x2 | 0x1 | 0x10
    
    try:
        # CredUIPromptForCredentials(targetName, authError, userName, password, save, flags, credUIInfo)
        res = win32cred.CredUIPromptForCredentials(
            cpi,
            "",
            None,
            0,
            "",
            "",
            False,
            flags
        )
        print("Success:", res)
    except pywintypes.error as e:
        print("Auth failed or cancelled:", e)

class TopW(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(200, 200)
        btn = QPushButton("Auth", self)
        btn.clicked.connect(self.cl)
        
    def cl(self):
        prompt_auth(int(self.winId()))

app = QApplication(sys.argv)
w = TopW()
w.show()
QTimer = __import__('PyQt6.QtCore').QtCore.QTimer
QTimer.singleShot(500, w.cl)
QTimer.singleShot(3000, app.quit)
app.exec()
