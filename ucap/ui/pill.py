"""Floating always-on-top pill at the bottom-center of the active monitor. Never takes focus."""
from __future__ import annotations

import ctypes
import math
import time
from collections import deque

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme as th

BARS = 26
W_SMALL, W_WIDE, H = 236, 440, 46


class Pill(QWidget):
    def __init__(self, level_source=lambda: 0.0):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.level_source = level_source
        self.mode = "hidden"  # rec | proc | msg | hidden
        self.handsfree = False
        self.label = ""
        self.tag = ""  # short badge on the recording pill, e.g. "Edit" for Command Mode
        self.error = True
        self.levels: deque[float] = deque([0.0] * BARS, maxlen=BARS)
        self.t0 = 0.0
        self._hide_timer = QTimer(self, singleShot=True, timeout=self.hide_pill)
        self._tick = QTimer(self, interval=40, timeout=self._on_tick)
        self.resize(W_SMALL, H)

    def _no_activate(self) -> None:
        try:
            u = ctypes.windll.user32
            hwnd = int(self.winId())
            style = u.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
            u.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x80 | 0x8)  # NOACTIVATE | TOOLWINDOW | TOPMOST
        except Exception:
            pass

    # ---- public API ----
    def show_recording(self, target_hwnd: int, handsfree: bool, tag: str = "") -> None:
        self._hide_timer.stop()
        self.mode, self.handsfree, self.tag = "rec", handsfree, tag
        self.levels = deque([0.0] * BARS, maxlen=BARS)
        self.t0 = time.monotonic()
        self._place(target_hwnd, W_SMALL)

    def show_processing(self, label: str) -> None:
        self._hide_timer.stop()
        self.mode, self.label, self.t0 = "proc", label, time.monotonic()
        self.update()

    def show_message(self, text: str, error: bool = True, target_hwnd: int | None = None, ms: int = 4000,
                     on_click=None) -> None:
        self.mode, self.label, self.error, self._on_click = "msg", text, error, on_click
        self.setCursor(Qt.PointingHandCursor if on_click else Qt.ArrowCursor)
        self._place(self._last_hwnd if target_hwnd is None else target_hwnd, W_WIDE if len(text) > 30 else W_SMALL)
        self._hide_timer.start(ms)

    def mousePressEvent(self, _):
        if self.mode != "msg":
            return  # clicks during recording/processing do nothing
        cb, self._on_click = self._on_click, None
        self.hide_pill()
        if cb:
            cb()

    def hide_pill(self) -> None:
        self._on_click = None
        self._hide_timer.stop()
        self._tick.stop()
        self.mode = "hidden"
        self.hide()

    # ---- internals ----
    _last_hwnd = 0
    _on_click = None

    def _place(self, hwnd: int, width: int) -> None:
        self._last_hwnd = hwnd
        screen = self._screen_for(hwnd)
        area = screen.availableGeometry()
        self.resize(width, H)
        self.move(QPoint(area.x() + (area.width() - width) // 2, area.y() + area.height() - H - 28))
        if not self.isVisible():
            self.show()
            self._no_activate()
        self.raise_()
        self._tick.start()
        self.update()

    def _screen_for(self, hwnd: int):
        # screen containing the target window's center (falls back to the mouse position)
        try:
            from ctypes import wintypes
            r = wintypes.RECT()
            if hwnd and ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r)):
                ratio = QGuiApplication.primaryScreen().devicePixelRatio() or 1
                pt = QPoint(int((r.left + r.right) / 2 / ratio), int((r.top + r.bottom) / 2 / ratio))
                s = QGuiApplication.screenAt(pt)
                if s:
                    return s
        except Exception:
            pass
        from PySide6.QtGui import QCursor
        return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

    def _on_tick(self) -> None:
        if self.mode == "rec":
            self.levels.append(self.level_source())
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = h / 2
        border = QColor(th.ACCENT) if (self.mode == "rec" and self.handsfree) else QColor(th.INK_2)
        p.setPen(QPen(border, 1.5))
        p.setBrush(QColor(th.INK))
        p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), r - 1, r - 1)
        now = time.monotonic()
        if self.mode == "rec":
            pulse = 0.5 + 0.5 * math.sin(now * 6)
            d = 5 + 2 * pulse
            cx, cy = r + 2, h / 2
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(th.ACCENT))
            p.drawEllipse(QRectF(cx - d, cy - d, 2 * d, 2 * d))
            x0, x1 = cx + 16, w - 52
            if self.tag:
                p.setPen(QColor(th.ACCENT))
                p.setFont(QFont(th.FONT, 9, QFont.Bold))
                p.drawText(QRectF(x0 - 4, 0, 60, h), Qt.AlignVCenter | Qt.AlignLeft, self.tag)
                x0 += 52
            step = (x1 - x0) / (BARS - 1)
            for i, lv in enumerate(self.levels):
                bh = 2 + min(1.0, lv * 1.6) * 15
                pen = QPen(QColor(th.ACCENT if lv > 0.08 else "#C9CCD6"), 3, Qt.SolidLine, Qt.RoundCap)
                p.setPen(pen)
                x = x0 + i * step
                p.drawLine(int(x), int(cy - bh), int(x), int(cy + bh))
            secs = int(now - self.t0)
            p.setPen(QColor("#FFFFFF"))
            p.setFont(QFont(th.FONT, 10, QFont.Bold))
            p.drawText(QRectF(w - 60, 0, 60 - r + 8, h), Qt.AlignVCenter | Qt.AlignRight, f"{secs // 60}:{secs % 60:02d}")
        elif self.mode == "proc":
            p.setPen(Qt.NoPen)
            for i in range(3):
                a = max(0.0, math.sin(((now * 3 - i * 0.35) % 2.0) * math.pi / 2))
                d = 3 + 2.5 * a
                cx = r + 4 + i * 14
                p.setBrush(QColor(th.ACCENT if a > 0.5 else "#8A90A2"))
                p.drawEllipse(QRectF(cx - d, h / 2 - d, 2 * d, 2 * d))
            p.setPen(QColor("#FFFFFF"))
            p.setFont(QFont(th.FONT, 10, QFont.Bold))
            p.drawText(QRectF(r + 40, 0, w - r - 48, h), Qt.AlignVCenter | Qt.AlignLeft, self.label + "…")
        elif self.mode == "msg":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(th.ERR if self.error else th.OK))
            p.drawEllipse(QRectF(r - 5, h / 2 - 5, 10, 10))
            p.setPen(QColor("#FFFFFF"))
            p.setFont(QFont(th.FONT, 9))
            p.drawText(QRectF(r + 12, 2, w - r - 26, h - 4), Qt.AlignVCenter | Qt.AlignLeft | Qt.TextWordWrap, self.label)
        p.end()
