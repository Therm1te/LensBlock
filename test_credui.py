import ctypes
import ctypes.wintypes

credui = ctypes.windll.credui

class CREDUI_INFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("hwndParent", ctypes.wintypes.HWND),
        ("pszMessageText", ctypes.c_wchar_p),
        ("pszCaptionText", ctypes.c_wchar_p),
        ("hbmBanner", ctypes.wintypes.HBITMAP),
    ]

def prompt_windows_auth():
    info = CREDUI_INFO()
    info.cbSize = ctypes.sizeof(CREDUI_INFO)
    info.hwndParent = None
    info.pszMessageText = "Please authenticate to bypass LensBlock overlay."
    info.pszCaptionText = "LensBlock Manual Override"
    info.hbmBanner = None
    
    auth_pkg = ctypes.wintypes.ULONG(0)
    out_cred = ctypes.c_void_p()
    out_size = ctypes.wintypes.ULONG(0)
    save = ctypes.wintypes.BOOL(False)
    
    # CREDUIWIN_ENUMERATE_CURRENT_USER = 0x20000
    # ERROR_SUCCESS = 0
    flags = 0x20000
    
    res = credui.CredUIPromptForWindowsCredentialsW(
        ctypes.byref(info),
        0, 
        ctypes.byref(auth_pkg),
        None,
        0,
        ctypes.byref(out_cred),
        ctypes.byref(out_size),
        ctypes.byref(save),
        flags
    )
    
    if out_cred:
        ctypes.windll.credui.CredFree(out_cred)
        
    print("CredUI Result is:", res)

if __name__ == "__main__":
    prompt_windows_auth()
