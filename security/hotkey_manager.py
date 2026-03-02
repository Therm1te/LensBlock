"""
Global Hotkey Manager for LensBlock.
Uses pynput to listen for system-wide key combinations
even when the application is not focused or the shield overlay is active.
"""
from pynput import keyboard
from PyQt6.QtCore import QObject, pyqtSignal


class HotkeyManager(QObject):
    """
    Listens for global hotkeys in a background thread via pynput.
    Emits Qt signals to safely bridge into the UI thread.
    """
    unlock_requested = pyqtSignal()       # Fired when Ctrl+Alt+L is pressed
    mode_toggle_requested = pyqtSignal()  # Fired when F2 is pressed

    def __init__(self):
        super().__init__()
        self._listener = None

    def start(self):
        """Starts the non-blocking global hotkey listener."""
        hotkeys = keyboard.GlobalHotKeys({
            '<ctrl>+<alt>+l': self._on_unlock_hotkey,
        })
        self._listener = hotkeys
        self._listener.daemon = True  # Ensure it won't block app exit
        self._listener.start()

        # F2 requires a separate key listener since GlobalHotKeys
        # doesn't support single non-modifier keys like F2 natively
        self._key_listener = keyboard.Listener(on_press=self._on_key_press, daemon=True)
        self._key_listener.start()
        
        print("HotkeyManager: Global listener started (Ctrl+Alt+L, F2)")

    def _on_unlock_hotkey(self):
        """Called from pynput's background thread when the hotkey fires."""
        print("HotkeyManager: Unlock hotkey detected!")
        self.unlock_requested.emit()

    def _on_key_press(self, key):
        """Captures F2 key presses for mode toggle."""
        if key == keyboard.Key.f2:
            print("HotkeyManager: Mode toggle (F2) detected!")
            self.mode_toggle_requested.emit()

    def stop(self):
        """Stops the listener cleanly."""
        if self._listener:
            self._listener.stop()
            self._listener = None
        if hasattr(self, '_key_listener') and self._key_listener:
            self._key_listener.stop()
            self._key_listener = None
        print("HotkeyManager: Listener stopped.")
