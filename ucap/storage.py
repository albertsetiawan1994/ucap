"""Settings, history and the API key (key lives only in Windows Credential Manager)."""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import date, timedelta
from pathlib import Path

from . import APP_NAME
from .gemini_client import DEFAULT_MODEL, RETIRED_MODELS
from .styles import DEFAULT_APP_STYLES

KEYRING_SERVICE = "Ucap"
KEYRING_USER = "gemini_api_key"  # single key of earlier versions; per-key entries add "_<id>"
HISTORY_LIMIT = 100

DEFAULT_SETTINGS = {
    "hotkey": "ctrl+windows",
    "command_hotkey": "alt+windows",  # hold, say an instruction, selected text is rewritten (not Ctrl+Alt: AltGr)
    "paste_hotkey": "alt+shift+z",  # paste the last dictation again
    "meeting_hotkey": "alt+shift+m",  # start / stop a meeting recording
    "check_updates": True,  # ask GitHub Releases once per start (see updater.UPDATE_REPO)
    "romanize": True,  # non-Latin text gets its romanization in parentheses (pinyin, POJ, romaji, ...)
    "use_window_title": True,  # send the target window title as a spelling hint
    "voice_send": False,  # off by default: a trailing "tekan enter" / "press enter" presses Enter after pasting
    "mic_device": None,  # None = Windows default input
    "language": "auto",  # auto | id | en
    "model": DEFAULT_MODEL,
    "model_list": [],  # cached from models.list(); empty = use FALLBACK_MODELS
    "keys": [],  # [{"id", "label", "enabled", "invalid"}] in try order; secrets only in keyring
    "keys_migrated": False,
    "dictionary": [],
    "snippets": [],  # [{"trigger": str, "expansion": str}]
    "app_styles": dict(DEFAULT_APP_STYLES),
    "default_style": "casual",
    "start_with_windows": False,
    "sound_cues": True,
    "keep_audio": False,
    "meeting_screen_speakers": True,  # screenshots of the meeting window name the speakers
    "meeting_system_audio": True,  # meetings also record what the speakers play (online meeting participants)
    "ui_lang": "id",  # id | en
}


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)  # atomic, so a crash never leaves half a file


class Settings(dict):
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "settings.json"
        loaded = _read_json(self.path, {})
        merged = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
                  for k, v in DEFAULT_SETTINGS.items()}
        if isinstance(loaded, dict):
            merged.update({k: v for k, v in loaded.items() if k in DEFAULT_SETTINGS})
        merged.pop("api_key", None)  # never kept in a plain file
        if merged["model"] in RETIRED_MODELS or not merged["model"]:
            merged["model"] = DEFAULT_MODEL
        super().__init__(merged)

    def save(self) -> None:
        _write_json(self.path, dict(self))


class History:
    def __init__(self, path: Path | None = None, limit: int = HISTORY_LIMIT):
        self.path = path or data_dir() / "history.json"
        self.limit = limit
        self._lock = threading.Lock()
        items = _read_json(self.path, [])
        self.items: list[dict] = items if isinstance(items, list) else []

    def add(self, text: str, app: str, model: str = "", key_label: str = "") -> dict:
        entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "app": app or "", "model": model,
                 "key": key_label, "text": text}
        with self._lock:
            self.items.insert(0, entry)
            del self.items[self.limit:]
            _write_json(self.path, self.items)
        return entry

    def remove(self, index: int) -> None:
        with self._lock:
            if 0 <= index < len(self.items):
                del self.items[index]
                _write_json(self.path, self.items)

    def clear(self) -> None:
        with self._lock:
            self.items = []
            _write_json(self.path, self.items)


class Stats:
    """Words and speaking time per day, kept apart from the 100-item history."""

    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "stats.json"
        self._lock = threading.Lock()
        days = _read_json(self.path, {})
        self.days: dict[str, dict] = days if isinstance(days, dict) else {}

    def add(self, words: int, secs: float, day: str | None = None) -> None:
        with self._lock:
            d = self.days.setdefault(day or time.strftime("%Y-%m-%d"), {"words": 0, "secs": 0.0, "count": 0})
            d["words"] += int(words)
            d["secs"] += float(secs)
            d["count"] += 1
            _write_json(self.path, self.days)

    def last_days(self, n: int = 7, today: date | None = None) -> list[tuple[date, int]]:
        """(day, words) for the last n days, oldest first; days without dictation count 0."""
        today = today or date.today()
        with self._lock:
            days = dict(self.days)
        out = []
        for i in range(n - 1, -1, -1):
            d = today - timedelta(days=i)
            out.append((d, int(days.get(d.isoformat(), {}).get("words", 0))))
        return out

    def summary(self, today: date | None = None) -> dict:
        today = today or date.today()
        parsed = {}
        with self._lock:
            days = dict(self.days)
        for k, v in days.items():
            try:
                parsed[date.fromisoformat(k)] = v
            except ValueError:
                pass
        words = sum(v["words"] for v in parsed.values())
        secs = sum(v["secs"] for v in parsed.values())
        streak, day = 0, today if today in parsed else today - timedelta(days=1)
        while day in parsed:
            streak += 1
            day -= timedelta(days=1)
        return {"words_today": parsed.get(today, {}).get("words", 0),
                "words_week": sum(v["words"] for k, v in parsed.items() if 0 <= (today - k).days < 7),
                "words_total": words, "count_total": sum(v["count"] for v in parsed.values()),
                "wpm": words / (secs / 60) if secs > 0 else 0, "streak": streak}


# Settings that move between PCs; API keys and the cached model list never leave Credential Manager / this PC.
EXPORT_KEYS = ("hotkey", "command_hotkey", "paste_hotkey", "meeting_hotkey", "voice_send", "use_window_title", "romanize", "language", "model", "dictionary",
               "snippets", "app_styles", "default_style", "sound_cues", "ui_lang")


def export_settings(settings: dict) -> dict:
    return {k: settings[k] for k in EXPORT_KEYS if k in settings}


def _valid(key: str, value) -> bool:
    if type(value) is not type(DEFAULT_SETTINGS[key]):
        return False
    if key == "model":
        return bool(value.strip()) and value not in RETIRED_MODELS
    if key == "dictionary":
        return all(isinstance(x, str) for x in value)
    if key == "snippets":
        return all(isinstance(x, dict) and isinstance(x.get("trigger"), str) and isinstance(x.get("expansion"), str)
                   for x in value)
    if key == "app_styles":
        return all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())
    return True


def import_settings(settings: dict, data) -> list[str]:
    """Copy the valid exported settings into `settings`; returns the keys that were applied."""
    applied = []
    for k in EXPORT_KEYS:
        if isinstance(data, dict) and k in data and _valid(k, data[k]):
            settings[k] = data[k]
            applied.append(k)
    return applied


AUDIO_KEEP = 100  # newest kept recordings


def audio_dir() -> Path:
    d = data_dir() / "audio"
    d.mkdir(exist_ok=True)
    return d


def prune_audio(folder: Path | None = None, limit: int = AUDIO_KEEP) -> None:
    """Delete the oldest .wav files beyond `limit` so kept recordings do not grow forever."""
    files = sorted((folder or audio_dir()).glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files[limit:]:
        try:
            f.unlink()
        except OSError:
            pass


# --- API key: Windows Credential Manager via keyring -------------------------

def _keyring(kr=None):
    if kr is not None:
        return kr
    import keyring
    return keyring


def get_key_secret(key_id: str, kr=None) -> str:
    try:
        return _keyring(kr).get_password(KEYRING_SERVICE, f"{KEYRING_USER}_{key_id}") or ""
    except Exception:
        return ""


def set_key_secret(key_id: str, secret: str, kr=None) -> None:
    _keyring(kr).set_password(KEYRING_SERVICE, f"{KEYRING_USER}_{key_id}", secret.strip())


def delete_key_secret(key_id: str, kr=None) -> None:
    try:
        _keyring(kr).delete_password(KEYRING_SERVICE, f"{KEYRING_USER}_{key_id}")
    except Exception:
        pass


def new_key_id(keys: list[dict]) -> str:
    used = {k["id"] for k in keys}
    return next(str(i) for i in range(1, 1000) if str(i) not in used)


def migrate_single_key(settings: dict, kr=None) -> bool:
    """The one key of earlier versions becomes key #1 'Utama'. Runs once; True if a key was moved."""
    if settings.get("keys_migrated"):
        return False
    kr = _keyring(kr)
    try:
        old = kr.get_password(KEYRING_SERVICE, KEYRING_USER) or ""
    except Exception:
        return False  # keyring unavailable: try again next start
    moved = False
    if old:
        kid = new_key_id(settings["keys"])
        set_key_secret(kid, old, kr)
        settings["keys"].insert(0, {"id": kid, "label": "Utama", "enabled": True, "invalid": False})
        try:
            kr.delete_password(KEYRING_SERVICE, KEYRING_USER)  # only after the copy succeeded
        except Exception:
            pass
        moved = True
    settings["keys_migrated"] = True
    return moved


# --- Start with Windows -------------------------------------------------------

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command() -> str:
    import sys
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    main = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{pyw if pyw.exists() else exe}" "{main}"'


def set_autostart(enabled: bool) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass
