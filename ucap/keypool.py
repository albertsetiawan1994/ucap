"""Several Gemini API keys (one per Google Cloud project) plus quota memory per (key, model).

Secrets are never stored here: `secret_of(key_id)` reads them from Windows Credential Manager.
The state file only holds key ids, model names, reset times and request counts.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")  # Gemini daily quotas reset at midnight Pacific time
MINUTE_COOLDOWN = 60.0
MAX_KEYS = 10

_DAILY = re.compile(r"quotaId['\"]?\s*:\s*['\"][^'\"]*PerDay", re.IGNORECASE)
_RETRY = re.compile(r"retryDelay['\"]?\s*:\s*['\"](\d+(?:\.\d+)?)s")


def next_pacific_midnight(now: float) -> float:
    local = datetime.fromtimestamp(now, PACIFIC)
    nxt = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), tzinfo=PACIFIC)
    return nxt.timestamp()


def pacific_date(now: float) -> str:
    return datetime.fromtimestamp(now, PACIFIC).strftime("%Y-%m-%d")


def parse_quota(text: str) -> tuple[bool, float | None]:
    """(is_daily, retry_delay_seconds) from a 429 error's text (the SDK puts the JSON details in str(exc))."""
    daily = bool(_DAILY.search(text or ""))
    m = _RETRY.search(text or "")
    return daily, (float(m.group(1)) if m else None)


def mask(secret: str) -> str:
    return f"{secret[:4]}…{secret[-4:]}" if len(secret) > 10 else "…"


class KeyPool:
    def __init__(self, keys: list[dict], secret_of: Callable[[str], str], state_path: Path | None = None,
                 clock: Callable[[], float] = time.time):
        self.keys = keys  # the settings["keys"] list itself, so enable/invalid changes are saved with settings
        self.secret_of = secret_of
        self.path = state_path
        self.clock = clock
        self._lock = threading.Lock()
        self.blocks: dict[str, dict] = {}  # "key_id|model" -> {"until": ts, "daily": bool}
        self.counts: dict = {"date": "", "data": {}}  # Pacific date -> {key_id: {model: n}}
        self._load()

    # ---- persistence ----
    def _load(self) -> None:
        if not self.path:
            return
        try:
            data = json.loads(Path(self.path).read_text(encoding="utf-8"))
            self.blocks = dict(data.get("blocks", {}))
            self.counts = data.get("counts") or self.counts
        except (OSError, ValueError, AttributeError):
            pass
        self._prune()

    def _save(self) -> None:
        if not self.path:
            return
        tmp = Path(self.path).with_suffix(".tmp")
        tmp.write_text(json.dumps({"blocks": self.blocks, "counts": self.counts}, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def _prune(self) -> None:
        now = self.clock()
        self.blocks = {k: v for k, v in self.blocks.items() if v.get("until", 0) > now}
        if self.counts.get("date") != pacific_date(now):
            self.counts = {"date": pacific_date(now), "data": {}}

    # ---- queries ----
    def usable(self) -> list[dict]:
        """Enabled, not marked invalid, and with a secret — in the user's order."""
        return [k for k in self.keys if k.get("enabled", True) and not k.get("invalid") and self.secret_of(k["id"])]

    def blocked_until(self, key_id: str, model: str) -> float | None:
        b = self.blocks.get(f"{key_id}|{model}")
        return b["until"] if b and b["until"] > self.clock() else None

    def blocks_for(self, key_id: str) -> list[tuple[str, float, bool]]:
        """Active (model, until, daily) blocks of one key."""
        with self._lock:
            self._prune()
            return [(k.split("|", 1)[1], v["until"], v["daily"]) for k, v in self.blocks.items()
                    if k.split("|", 1)[0] == key_id]

    def earliest_reset(self) -> float | None:
        with self._lock:
            self._prune()
            return min((v["until"] for v in self.blocks.values()), default=None)

    def today_counts(self, key_id: str) -> dict[str, int]:
        with self._lock:
            self._prune()
            return dict(self.counts["data"].get(key_id, {}))

    # ---- updates ----
    def count(self, key_id: str, model: str) -> None:
        with self._lock:
            self._prune()
            per_key = self.counts["data"].setdefault(key_id, {})
            per_key[model] = per_key.get(model, 0) + 1
            self._save()

    def mark_quota(self, key_id: str, model: str, error_text: str) -> float:
        daily, delay = parse_quota(error_text)
        now = self.clock()
        until = next_pacific_midnight(now) if daily else now + (delay or MINUTE_COOLDOWN)
        with self._lock:
            self.blocks[f"{key_id}|{model}"] = {"until": until, "daily": daily}
            self._save()
        return until

    def mark_invalid(self, key_id: str, invalid: bool = True) -> None:
        for k in self.keys:
            if k["id"] == key_id:
                k["invalid"] = invalid

    def forget(self, key_id: str) -> None:
        """Drop everything about a removed key."""
        with self._lock:
            self.blocks = {k: v for k, v in self.blocks.items() if k.split("|", 1)[0] != key_id}
            self.counts["data"].pop(key_id, None)
            self._save()
