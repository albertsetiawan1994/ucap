"""Global hotkey: hold-to-talk, double-tap for hands-free, Esc cancels."""
from __future__ import annotations

import ctypes
import time
from typing import Callable

_ALIASES = {"control": "ctrl", "win": "windows", "cmd": "windows", "command": "windows", "super": "windows",
            "alt gr": "alt", "option": "alt", "escape": "esc"}

TAP_MAX = 0.30      # a press shorter than this is a tap, not a dictation
DOUBLE_GAP = 0.45   # second tap must start within this after the first ended


def normalize_key(name: str) -> str:
    n = (name or "").strip().lower()
    for side in ("left ", "right "):
        if n.startswith(side):
            n = n[len(side):]
    return _ALIASES.get(n, n)


def parse_combo(text: str) -> frozenset[str]:
    keys = frozenset(normalize_key(p) for p in (text or "").split("+") if p.strip())
    return keys or frozenset({"ctrl", "windows"})


def combos_conflict(a: str, b: str) -> bool:
    """True when pressing one combo also presses the other (same keys, or one inside the other)."""
    pa, pb = parse_combo(a), parse_combo(b)
    return pa <= pb or pb <= pa


def format_combo(text: str) -> str:
    order = {"ctrl": 0, "shift": 1, "alt": 2, "windows": 3}
    keys = sorted(parse_combo(text), key=lambda k: (order.get(k, 9), k))
    return "+".join(k.capitalize() if len(k) > 1 else k.upper() for k in keys).replace("Windows", "Win")


class HotkeyMachine:
    """Pure state machine fed with key events; no OS calls, so it can be unit-tested."""

    def __init__(self, combo: str, on_start: Callable[[str], None], on_stop: Callable[[], None],
                 on_cancel: Callable[[str], None], clock: Callable[[], float] = time.monotonic):
        self.combo = parse_combo(combo)
        self.on_start, self.on_stop, self.on_cancel, self.clock = on_start, on_stop, on_cancel, clock
        self.pressed: set[str] = set()
        self.state = "idle"  # idle | hold | handsfree
        self._combo_down = False
        self._press_t = 0.0
        self._last_tap_end = -10.0

    def set_combo(self, combo: str) -> None:
        self.combo = parse_combo(combo)
        self.pressed.clear()
        self._combo_down = False

    def reset(self) -> None:
        """Called when the app aborts a recording by itself (e.g. mic error)."""
        self.state = "idle"

    def key_down(self, name: str) -> None:
        k = normalize_key(name)
        self.pressed.add(k)
        now = self.clock()
        if k == "esc" and self.state != "idle":
            self.state = "idle"
            self.on_cancel("esc")
            return
        if not self._combo_down and self.combo <= self.pressed:
            self._combo_down = True
            if self.state == "handsfree":
                self.state = "idle"
                self.on_stop()
            elif self.state == "idle":
                if now - self._last_tap_end <= DOUBLE_GAP:
                    self.state = "handsfree"
                    self._last_tap_end = -10.0
                    self.on_start("handsfree")
                else:
                    self.state = "hold"
                    self._press_t = now
                    self.on_start("hold")
            return
        if k not in self.combo and self.state == "hold":
            # user pressed e.g. Ctrl+Win+D: a Windows shortcut, not a dictation
            self.state = "idle"
            self.on_cancel("other_key")

    def key_up(self, name: str) -> None:
        k = normalize_key(name)
        self.pressed.discard(k)
        if self._combo_down and k in self.combo:
            self._combo_down = False
            if self.state == "hold":
                self.state = "idle"
                now = self.clock()
                if now - self._press_t < TAP_MAX:
                    self._last_tap_end = now
                    self.on_cancel("tap")
                else:
                    self.on_stop()


VK_MASK = 0xE8  # unassigned virtual key


def _mask_start_menu() -> None:
    # A key event between Win-down and Win-up keeps the Start menu from opening.
    u = ctypes.windll.user32
    u.keybd_event(VK_MASK, 0, 0, 0)
    u.keybd_event(VK_MASK, 0, 2, 0)


class HotkeyListener:
    """Feeds every HotkeyMachine from one global low-level keyboard hook (keyboard library)."""

    def __init__(self, machines):
        self.machines = list(machines) if isinstance(machines, (list, tuple)) else [machines]
        self._hook = None
        self._esc = None
        self._extra: dict[str, object] = {}  # name -> add_hotkey handle

    def start(self) -> None:
        import keyboard
        self._hook = keyboard.hook(self._on_event)

    def stop(self) -> None:
        import keyboard
        if self._hook is not None:
            keyboard.unhook(self._hook)
            self._hook = None
        for name in list(self._extra):
            self.set_extra(name, None, None)
        self.set_esc_capture(False)

    def set_extra(self, name: str, combo: str | None, callback) -> None:
        """One-shot hotkey (fires on press, no hold logic), replaced by name."""
        import keyboard
        old = self._extra.pop(name, None)
        try:
            if old is not None:
                keyboard.remove_hotkey(old)
            if combo:
                self._extra[name] = keyboard.add_hotkey(combo, callback)
        except Exception:
            pass

    def set_esc_capture(self, on: bool) -> None:
        """While recording, swallow Esc so it cancels us instead of reaching the target app."""
        import keyboard
        try:
            if on and self._esc is None:
                self._esc = keyboard.add_hotkey("esc", lambda: None, suppress=True)
            elif not on and self._esc is not None:
                keyboard.remove_hotkey(self._esc)
                self._esc = None
        except Exception:
            self._esc = None

    def _on_event(self, e) -> None:
        # scan code 0 = synthetic event (our own Start-menu mask key); physical keys always have one
        if not e.scan_code or not e.name:
            return
        for m in self.machines:
            if e.event_type == "down":
                was = m._combo_down
                m.key_down(e.name)
                if not was and m._combo_down and "windows" in m.combo:
                    _mask_start_menu()
            else:
                m.key_up(e.name)
