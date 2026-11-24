"""Writing style per app (by foreground process exe name)."""
from __future__ import annotations

STYLES = ("formal", "casual", "very_casual")
APP_STYLES = STYLES + ("off",)  # "off" = Ucap is disabled in that app (per-app only)

_MESSAGING = ["WhatsApp.exe", "WhatsApp.Root.exe", "Telegram.exe", "Signal.exe", "Discord.exe", "LINE.exe", "Messenger.exe"]
_WORK_CHAT = ["slack.exe", "ms-teams.exe", "Teams.exe", "Zoom.exe"]
_EMAIL_DOCS = ["OUTLOOK.EXE", "olk.exe", "thunderbird.exe", "WINWORD.EXE", "POWERPNT.EXE", "EXCEL.EXE", "ONENOTE.EXE", "soffice.bin"]
_BROWSERS = ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"]

# messaging = casual, work chat = casual, email/docs = formal, browsers = casual (mixed use)
DEFAULT_APP_STYLES: dict[str, str] = {
    **{e: "casual" for e in _MESSAGING},
    **{e: "casual" for e in _WORK_CHAT},
    **{e: "formal" for e in _EMAIL_DOCS},
    **{e: "casual" for e in _BROWSERS},
}

STYLE_RULES = {
    "formal": (
        "Formal: polished, professional writing. Complete sentences, correct grammar, full punctuation "
        "and capitalization, no slang or chat abbreviations. In Indonesian use standard (baku) spelling. "
        "Keep the speaker's wording and meaning; do not add content."
    ),
    "casual": (
        "Casual: natural, friendly conversational writing. Normal capitalization and punctuation, "
        "keep informal words exactly as spoken (e.g. 'nggak', 'gonna'). Keep the speaker's wording."
    ),
    "very_casual": (
        "Very casual: relaxed chat-message style. Lowercase is fine, minimal punctuation, no period at the "
        "very end, keep slang exactly as spoken. Keep the speaker's wording."
    ),
}


def style_for_app(exe: str | None, app_styles: dict[str, str], default_style: str = "casual") -> str:
    """Case-insensitive exe lookup; unknown apps get default_style."""
    fallback = default_style if default_style in STYLES else "casual"
    if not exe:
        return fallback
    lowered = {k.lower(): v for k, v in app_styles.items()}
    style = lowered.get(exe.lower(), fallback)
    return style if style in APP_STYLES else fallback


CODE_EDITORS = {"code.exe", "cursor.exe", "windsurf.exe", "devenv.exe", "idea64.exe", "pycharm64.exe",
                "webstorm64.exe", "rider64.exe", "clion64.exe", "goland64.exe", "phpstorm64.exe",
                "studio64.exe", "sublime_text.exe", "notepad++.exe", "zed.exe"}


def is_code_editor(exe: str | None) -> bool:
    return (exe or "").lower() in CODE_EDITORS


def window_title(hwnd: int) -> str:
    try:
        import win32gui
        return win32gui.GetWindowText(hwnd) if hwnd else ""
    except Exception:
        return ""


def foreground_app() -> tuple[int, str]:
    """(hwnd, exe name) of the foreground window; (0, '') when unknown."""
    try:
        import psutil
        import win32gui
        import win32process
        hwnd = win32gui.GetForegroundWindow()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return hwnd, psutil.Process(pid).name()
    except Exception:
        return 0, ""
