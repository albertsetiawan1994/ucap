"""Find the online-meeting window and grab a small screenshot of it (who is talking, names on video tiles)."""
from __future__ import annotations

# These apps are also chat apps that stay open all day, so the window title must say it is a call:
# screenshots of a normal chat window must never be sent.
MEETING_APPS = {"zoom.exe", "ms-teams.exe", "teams.exe", "webex.exe", "ciscocollabhost.exe", "atmgr.exe",
                "slack.exe", "discord.exe", "skype.exe", "lark.exe", "whatsapp.exe", "whatsapp.root.exe"}
APP_CALL_WORDS = ("meeting", "call", "rapat", "panggilan", "huddle", "webinar", "rapat zoom")
BROWSERS = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe"}
BROWSER_CALL_TITLES = ("meet -", "google meet", "zoom meeting", "jitsi", "whereby", "webex meeting")
MAX_WIDTH = 1280


def pick_meeting_window(windows: list[tuple[int, str, str]]) -> int:
    """hwnd of the most likely call window from (hwnd, exe, title); a meeting app beats a browser tab; 0 = none."""
    browser = 0
    for hwnd, exe, title in windows:
        exe, low = (exe or "").lower(), (title or "").lower()
        if exe in MEETING_APPS and any(k in low for k in APP_CALL_WORDS):
            return hwnd
        if not browser and exe in BROWSERS and any(k in low for k in BROWSER_CALL_TITLES):
            browser = hwnd
    return browser


def list_windows() -> list[tuple[int, str, str]]:
    """Visible, not minimized top-level windows with a title, front to back."""
    out: list[tuple[int, str, str]] = []
    try:
        import psutil
        import win32gui
        import win32process

        def visit(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    try:
                        exe = psutil.Process(win32process.GetWindowThreadProcessId(hwnd)[1]).name()
                    except Exception:  # noqa: BLE001
                        exe = ""
                    out.append((hwnd, exe, title))
            return True

        win32gui.EnumWindows(visit, None)
    except Exception:  # noqa: BLE001
        pass
    return out


def capture(hwnd: int) -> bytes | None:
    """JPEG of the window's area on screen (GUI thread). Whatever covers the window is captured too."""
    try:
        import ctypes
        from ctypes import wintypes

        from PySide6.QtCore import QBuffer, QIODevice, QPoint, Qt
        from PySide6.QtGui import QGuiApplication
        r = wintypes.RECT()
        if not hwnd or not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return None
        ratio = QGuiApplication.primaryScreen().devicePixelRatio() or 1
        x, y, w, h = r.left / ratio, r.top / ratio, (r.right - r.left) / ratio, (r.bottom - r.top) / ratio
        screen = QGuiApplication.screenAt(QPoint(int(x + w / 2), int(y + h / 2)))
        if screen is None or w < 50 or h < 50:
            return None
        geo = screen.geometry()
        pix = screen.grabWindow(0, int(x - geo.x()), int(y - geo.y()), int(w), int(h))
        if pix.width() > MAX_WIDTH:
            pix = pix.scaledToWidth(MAX_WIDTH, Qt.SmoothTransformation)
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        pix.save(buf, "JPG", 60)
        return bytes(buf.data())
    except Exception:  # noqa: BLE001 - a missing screenshot only means fewer hints
        return None
