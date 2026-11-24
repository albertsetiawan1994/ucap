"""Insert text at the cursor of any app: clipboard backup -> paste -> restore."""
from __future__ import annotations

import ctypes
import time
from typing import Callable, Protocol

RESTORE_DELAY = 0.6  # seconds; target apps read the clipboard asynchronously after Ctrl+V


class Clipboard(Protocol):
    def snapshot(self) -> object: ...
    def set_text(self, text: str) -> None: ...
    def get_text(self) -> str | None: ...
    def restore(self, snap: object) -> None: ...


def insert_text(text: str, clipboard: Clipboard, send_paste: Callable[[], bool],
                can_paste: bool = True, sleep: Callable[[float], None] = time.sleep,
                restore_delay: float = RESTORE_DELAY) -> str:
    """Returns 'pasted', or 'clipboard' when the text was left on the clipboard for a manual paste."""
    snap = clipboard.snapshot()
    clipboard.set_text(text)
    if not can_paste:
        return "clipboard"
    try:
        ok = send_paste()
    except Exception:
        ok = False
    if not ok:
        return "clipboard"
    sleep(restore_delay)
    # only restore if nobody copied something new meanwhile
    if clipboard.get_text() == text:
        clipboard.restore(snap)
    return "pasted"


# --- Windows implementation ---------------------------------------------------

# Handle-based formats can't be copied as bytes; the text/DIB versions cover them.
# shortcut: copied files (CF_HDROP) aren't restored, upgrade if people dictate right after copying files.
_SKIP_FORMATS = {1, 2, 3, 7, 9, 14, 15, 16, 17, 0x80, 0x82, 0x83, 0x8E}


class WinClipboard:
    def _open(self) -> None:
        import win32clipboard
        for _ in range(20):
            try:
                win32clipboard.OpenClipboard()
                return
            except Exception:
                time.sleep(0.03)
        win32clipboard.OpenClipboard()

    def snapshot(self) -> dict:
        import win32clipboard
        snap = {}
        self._open()
        try:
            fmt = win32clipboard.EnumClipboardFormats(0)
            while fmt:
                if fmt not in _SKIP_FORMATS:
                    try:
                        snap[fmt] = win32clipboard.GetClipboardData(fmt)
                    except Exception:
                        pass
                fmt = win32clipboard.EnumClipboardFormats(fmt)
        finally:
            win32clipboard.CloseClipboard()
        return snap

    def set_text(self, text: str) -> None:
        import win32clipboard
        self._open()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
        finally:
            win32clipboard.CloseClipboard()

    def get_text(self) -> str | None:
        import win32clipboard
        self._open()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            return None
        finally:
            win32clipboard.CloseClipboard()

    def restore(self, snap: dict) -> None:
        import win32clipboard
        self._open()
        try:
            win32clipboard.EmptyClipboard()
            for fmt, data in snap.items():
                try:
                    win32clipboard.SetClipboardData(fmt, data)
                except Exception:
                    pass
        finally:
            win32clipboard.CloseClipboard()


def send_ctrl_v() -> bool:
    import keyboard
    keyboard.send("ctrl+v")
    return True


def _process_elevated(pid: int) -> bool:
    k32, adv = ctypes.windll.kernel32, ctypes.windll.advapi32
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return True  # can't even look at it: treat as protected
    try:
        tok = ctypes.c_void_p()
        if not adv.OpenProcessToken(h, 0x0008, ctypes.byref(tok)):
            return True
        try:
            elev = ctypes.c_uint32()
            size = ctypes.c_uint32()
            adv.GetTokenInformation(tok, 20, ctypes.byref(elev), 4, ctypes.byref(size))
            return bool(elev.value)
        finally:
            k32.CloseHandle(tok)
    finally:
        k32.CloseHandle(h)


def can_paste_into_foreground() -> bool:
    """False when there is no target window or it runs as admin while we don't (Windows blocks that)."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    if ctypes.windll.shell32.IsUserAnAdmin():
        return True
    pid = ctypes.c_uint32()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return not _process_elevated(pid.value)


def copy_selection(clipboard: Clipboard, send_copy: Callable[[], bool], sleep: Callable[[float], None] = time.sleep,
                   wait: float = 0.2) -> str:
    """Text currently selected in the foreground app ('' if none); the clipboard is put back as it was."""
    snap = clipboard.snapshot()
    sentinel = f"\x00ucap-{time.time_ns()}"
    clipboard.set_text(sentinel)
    try:
        send_copy()
        sleep(wait)
        got = clipboard.get_text()
    finally:
        clipboard.restore(snap)
    return "" if got in (None, sentinel) else got


def send_ctrl_c() -> bool:
    import keyboard
    keyboard.send("ctrl+c")
    return True


def send_enter() -> bool:
    import keyboard
    keyboard.send("enter")
    return True


def wait_keys_released(timeout: float = 1.5, keys=("ctrl", "alt", "shift", "windows")) -> None:
    """A hotkey is usually still held when we start; wait so our own Ctrl+C / Ctrl+V isn't mangled by it."""
    import keyboard
    end = time.monotonic() + timeout
    while time.monotonic() < end and any(keyboard.is_pressed(k) for k in keys):
        time.sleep(0.02)
