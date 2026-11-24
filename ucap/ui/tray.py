"""System tray icon with menu and notifications."""
from __future__ import annotations

from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .. import __version__
from . import theme as th


class Tray:
    def __init__(self, app):
        self.app = app
        self.icon_idle = th.logo_icon()
        self.icon_rec = th.logo_icon(recording=True)
        self.tray = QSystemTrayIcon(self.icon_idle)
        self.tray.setToolTip(f"Ucap {__version__}")
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self._fill)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._activated)
        self._fill()

    def _fill(self):
        t = self.app.t
        self.menu.clear()
        self.menu.addAction(t("tray_settings"), lambda: self.app.win.show_tab("general"))
        self.menu.addAction(t("tray_history"), lambda: self.app.win.show_tab("history"))
        retry = self.menu.addAction(t("tray_retry"), self.app.retry_last)
        retry.setEnabled(self.app.last_job is not None)
        self.menu.addAction(t("tray_paste_last"), self.app.paste_last).setEnabled(bool(self.app.history.items))
        rec = self.app.meet is not None and self.app.meet.state == "recording"
        idle = self.app.meet is None or self.app.meet.state in ("recording", "done")
        self.menu.addAction(t("tray_meeting_stop" if rec else "tray_meeting_start"),
                            self.app.meeting_toggle).setEnabled(idle)
        if self.app.update_info:
            self.menu.addAction(t("tray_update", version=self.app.update_info["version"]), self.app.open_update)
        self.menu.addSeparator()
        self.menu.addAction(t("tray_quit"), self.app.quit)

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.app.win.show_tab()

    def start(self):
        self.tray.show()

    def stop(self):
        self.tray.hide()

    def set_recording(self, on: bool):
        self.tray.setIcon(self.icon_rec if on else self.icon_idle)

    def set_meeting(self, on: bool):
        self.tray.setToolTip(f"Ucap {__version__}" + (" - rapat" if on else ""))
        self.tray.setIcon(self.icon_rec if on else self.icon_idle)

    def notify(self, text: str):
        self.tray.showMessage("Ucap", text, self.icon_idle, 4000)
