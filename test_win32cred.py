import pywintypes
import win32cred

def test_auth():
    try:
        cpi = {
            'MessageText': 'Please authenticate to bypass LensBlock',
            'CaptionText': 'LensBlock Manual Override',
            'hwndParent': 0
        }
        flags = win32cred.CREDUIWIN_ENUMERATE_CURRENT_USER | win32cred.CREDUIWIN_PACK32_WOW
        result = win32cred.CredUIPromptForWindowsCredentials(cpi, 0, "", None, None, False, flags)
        print("Success!", result)
    except pywintypes.error as e:
        print("Failed:", e)

if __name__ == '__main__':
    test_auth()
