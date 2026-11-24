"""Controller: wires hotkey -> recorder -> Gemini -> snippets -> paste, plus tray, pill and settings."""
from __future__ import annotations

import ctypes
import queue
import sys
import threading
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from . import __version__, audio, gemini_client, i18n, inserter, meetings, storage, updater
from .commands import split_send
from .errors import UcapError
from .hotkey import HotkeyListener, HotkeyMachine, combos_conflict
from .keypool import MAX_KEYS, KeyPool
from .meeting_session import MeetingSession
from .snippets import clean_output, expand_snippets
from .styles import foreground_app, is_code_editor, style_for_app, window_title
from .ui import theme


def _beep(freq: int, ms: int) -> None:
    import winsound
    threading.Thread(target=winsound.Beep, args=(freq, ms), daemon=True).start()


class UcapApp:
    def __init__(self, screenshot: str | None = None):
        self.screenshot = screenshot
        self.qt = QApplication.instance() or QApplication(sys.argv)
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setStyle("Fusion")
        self.qt.setStyleSheet(theme.stylesheet())
        self.qt.setWindowIcon(theme.logo_icon())
        self.settings = storage.Settings()
        self.history = storage.History()
        self.stats = storage.Stats()
        self.meetings = meetings.MeetingStore()
        self.meet: MeetingSession | None = None
        self.q: queue.Queue = queue.Queue()
        self.recorder = audio.Recorder()
        self.busy = False
        self.target = (0, "")
        self.target_title = ""
        self._secrets: dict[str, str] = {}
        self._hotkey_paused = False
        self.last_job = None  # audio of the last failed dictation, kept in memory for one retry
        self.update_info = None  # {"version", "url"} when a newer release exists
        if not screenshot and not self.settings["keys_migrated"]:
            storage.migrate_single_key(self.settings)
            self.settings.save()
        self.pool = KeyPool(self.settings["keys"], self.secret,
                            None if screenshot else storage.data_dir() / "quota.json")

        from .ui.pill import Pill
        from .ui.settings_window import SettingsWindow
        self.pill = Pill(level_source=lambda: self.recorder.level)
        self.win = SettingsWindow(self)
        self.machine = HotkeyMachine(self.settings["hotkey"], lambda m: self._hk_start(m, "dictate"),
                                     self._hk_stop, self._hk_cancel)
        self.cmd_machine = HotkeyMachine(self.settings["command_hotkey"], lambda m: self._hk_start(m, "command"),
                                         self._hk_stop, self._hk_cancel)
        self.machines = {"dictate": self.machine, "command": self.cmd_machine}
        self.kind = "dictate"
        self.listener = HotkeyListener(list(self.machines.values()))
        self.tray = None
        self._pump_timer = QTimer(interval=30, timeout=self._pump)

    # ---- thread-safe entry point (hook / worker threads) ----
    def post(self, ev) -> None:
        self.q.put(ev)

    def _hk_start(self, mode, kind="dictate"):
        if not self._hotkey_paused:
            self.post(("start", mode, kind))

    def _hk_stop(self):
        self.post(("stop",))

    def _hk_cancel(self, reason):
        self.post(("cancel", reason))

    # ---- run ----
    def run(self) -> int:
        if self.screenshot:
            return self._run_screenshot()
        from .ui.tray import Tray
        self.tray = Tray(self)
        self.tray.start()
        try:
            self.listener.start()
            self._bind_paste_hotkey()
        except Exception:
            QTimer.singleShot(800, lambda: self._error(UcapError("hotkey")))
        if not self.has_key():
            self.win.show_tab("gemini")
        if self.settings["check_updates"]:
            threading.Thread(target=lambda: self.post(("update", updater.check(__version__))), daemon=True).start()
        if self.hotkey_conflicts():
            QTimer.singleShot(1500, lambda: self.tray.notify(self.t("hotkey_conflict_saved")))
        self._pump_timer.start()
        return self.qt.exec()

    HOTKEYS = (("hotkey", "hotkey"), ("command_hotkey", "cmd_hotkey"), ("paste_hotkey", "paste_hotkey"),
               ("meeting_hotkey", "meet_hotkey"))

    def hotkey_conflict(self, key: str, value: str) -> str | None:
        """i18n label of another hotkey that `value` would clash with, or None."""
        for k, label in self.HOTKEYS:
            if k != key and combos_conflict(value, self.settings[k]):
                return label
        return None

    def hotkey_conflicts(self) -> bool:
        return any(self.hotkey_conflict(k, self.settings[k]) for k, _ in self.HOTKEYS)

    def _bind_paste_hotkey(self) -> None:
        self.listener.set_extra("paste", self.settings["paste_hotkey"], lambda: self.post(("paste_last",)))
        self.listener.set_extra("meeting", self.settings["meeting_hotkey"], lambda: self.post(("meeting_hotkey",)))

    def _run_screenshot(self) -> int:
        w = self.win
        w.setAttribute(Qt.WA_ShowWithoutActivating)
        w.setWindowFlag(Qt.WindowStaysOnBottomHint, True)  # behind other windows; still drawn on Windows
        w.show()
        frames = [0]

        def frame():
            frames[0] += 1
            w.update()
            if frames[0] >= 120:
                timer.stop()
                w.grab().save(self.screenshot, "PNG")
                self.qt.quit()

        timer = QTimer(interval=16, timeout=frame)
        timer.start()
        return self.qt.exec()

    def _pump(self) -> None:
        if self.meet:
            self.meet.tick()
        try:
            while True:
                ev = self.q.get_nowait()
                getattr(self, "_on_" + ev[0])(*ev[1:])
        except queue.Empty:
            pass

    def _confirm(self, key: str) -> bool:
        from PySide6.QtWidgets import QMessageBox
        return QMessageBox.question(self.win, "Ucap", self.t(key)) == QMessageBox.Yes

    def quit(self) -> None:
        if self.meet and self.meet.state in ("recording", "processing") and not self._confirm("confirm_quit_meeting"):
            return  # the meeting audio only exists in memory
        try:
            self.listener.stop()
        except Exception:
            pass
        self.recorder.stop()
        if self.meet and self.meet.state == "recording":
            self.meet.abort()
        if self.tray:
            self.tray.stop()
        self.qt.quit()

    # ---- events (GUI thread) ----
    def _on_call(self, fn):
        fn()

    def _on_update(self, info):
        if info:
            self.update_info = info
            self.tray.notify(self.t("update_available", version=info["version"]))

    def open_update(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if self.update_info:
            QDesktopServices.openUrl(QUrl(self.update_info["url"]))

    def _on_start(self, mode, kind="dictate"):
        if self.busy or self.recorder.active:
            self.machines[kind].reset()
            return
        self.target = foreground_app()
        s = self.settings
        if style_for_app(self.target[1], s["app_styles"], s["default_style"]) == "off":
            self.machines[kind].reset()  # Ucap is switched off for this app
            return
        self.kind = kind
        self.target_title = window_title(self.target[0]) if s["use_window_title"] else ""
        try:
            self.recorder.start(self.settings["mic_device"])
        except UcapError as err:
            self.machine.reset()
            self._error(err)
            return
        self.listener.set_esc_capture(True)
        self.pill.show_recording(self.target[0], mode == "handsfree", self.t("cmd_pill") if kind == "command" else "")
        if self.tray:
            self.tray.set_recording(True)
        if self.settings["sound_cues"]:
            _beep(880, 70)

    def _end_recording(self):
        samples = self.recorder.stop()
        self.listener.set_esc_capture(False)
        if self.tray:
            self.tray.set_recording(False)
        return samples

    def _on_cancel(self, reason):
        if not self.recorder.active:
            return
        self._end_recording()
        self.pill.hide_pill()
        if reason == "esc" and self.settings["sound_cues"]:
            _beep(330, 90)

    def _on_stop(self):
        if not self.recorder.active:
            return
        samples = self._end_recording()
        if not audio.is_usable(samples):  # too short or silent: ignore quietly
            self.pill.hide_pill()
            return
        if self.settings["sound_cues"]:
            _beep(660, 60)
        if not self.has_key():
            self._error(UcapError("no_key"))
            return
        s = self.settings
        style = style_for_app(self.target[1], s["app_styles"], s["default_style"])
        command = self.kind == "command"
        if command:
            prompt = gemini_client.build_command_prompt(style, s["dictionary"])
        else:
            prompt = gemini_client.build_system_prompt(s["language"], style, s["dictionary"],
                                                       [x["trigger"] for x in s["snippets"]],
                                                       self.target_title, is_code_editor(self.target[1]))
        wav = audio.to_wav(samples)
        if s["keep_audio"]:
            (storage.audio_dir() / time.strftime("%Y%m%d-%H%M%S.wav")).write_bytes(wav)
            storage.prune_audio()
        self._start_job({"wav": wav, "prompt": prompt, "snippets": [] if command else list(s["snippets"]),
                         "target": self.target, "command": command, "voice_send": bool(s["voice_send"]),
                         "secs": samples.size / audio.SAMPLE_RATE}, label="cmd_label" if command else "processing")

    def _start_job(self, job, refocus=False, label="processing"):
        self.busy = True
        self.pill.show_processing(self.t(label))
        args = (job, self.settings["model"], list(self.settings["model_list"]), refocus)
        threading.Thread(target=self._process, args=args, daemon=True).start()

    def retry_last(self) -> None:
        """One retry of the last failed dictation (pill click or tray menu)."""
        job, self.last_job = self.last_job, None
        if job and not self.busy:
            self.target = job["target"]
            self._start_job(job, refocus=True)

    def _process(self, job, model, available, refocus):
        try:
            instruction = gemini_client.USER_INSTRUCTION
            if job.get("command"):
                inserter.wait_keys_released()
                selected = inserter.copy_selection(inserter.WinClipboard(), inserter.send_ctrl_c)
                if not selected:
                    raise UcapError("no_selection")
                instruction = gemini_client.command_instruction(selected)
            r = gemini_client.transcribe(job["wav"], self.pool, model, job["prompt"], available,
                                         instruction=instruction)
            text = expand_snippets(clean_output(r["text"]), job["snippets"])
            send = False
            if job.get("voice_send") and not job.get("command"):
                text, send = split_send(text)
            if not text and not send:
                self.post(("done", None, None, None))
                return
            if text:
                self.history.add(text, job["target"][1], r["model"], r["label"])
                self.stats.add(len(text.split()), job.get("secs", 0))
            if refocus and job["target"][0]:
                ctypes.windll.user32.SetForegroundWindow(job["target"][0])  # tray menu took focus
                time.sleep(0.15)
            can_paste = inserter.can_paste_into_foreground()
            result = "pasted"
            if text:
                result = inserter.insert_text(text, inserter.WinClipboard(), inserter.send_ctrl_v, can_paste=can_paste)
            if send and result == "pasted" and can_paste:
                time.sleep(0.12)
                inserter.send_enter()
            self.post(("done", text, result, r))
        except Exception as exc:  # noqa: BLE001
            err = gemini_client.classify_error(exc)
            self.post(("fail", err, None if err.code == "no_selection" else job))

    def _on_done(self, text, result, r=None):
        self.busy = False
        self.settings.save()  # keys may have been marked invalid
        self.win.refresh_keys()
        self.win.refresh_stats()
        if text is None:
            self.pill.show_message(self.t("err_empty"), error=True, ms=1800)
            return
        self.win.refresh_history()
        if not text:  # only a spoken "press enter"
            self.pill.hide_pill()
            return
        if result == "clipboard":
            self.pill.show_message(self.t("pasted_clipboard"), error=False)
            if self.tray:
                self.tray.notify(self.t("pasted_clipboard"))
        elif r and r.get("switched"):
            short = r["model"].removeprefix("gemini-")
            self.pill.show_message(self.t("via", label=r["label"], model=short), error=False, ms=2200)
        else:
            self.pill.hide_pill()

    def _on_fail(self, err, job=None):
        self.busy = False
        self.settings.save()
        self.win.refresh_keys()
        if job and err.code not in ("no_key",):
            self.last_job = job
        msg = i18n.error_text(self.settings["ui_lang"], err)
        if err.code == "quota":
            until = self.pool.earliest_reset()
            if until:
                msg = self.t("err_quota_all", time=time.strftime("%H:%M", time.localtime(until)))
        if self.last_job:
            msg += " " + self.t("retry_hint")
        self.pill.show_message(msg, error=True, target_hwnd=self.target[0], ms=9000,
                               on_click=self.retry_last if self.last_job else None)
        if self.tray:
            self.tray.notify(msg)

    def _error(self, err: UcapError):
        msg = i18n.error_text(self.settings["ui_lang"], err)
        self.pill.show_message(msg, error=True, target_hwnd=self.target[0])
        if self.tray:
            self.tray.notify(msg)

    # ---- API used by the settings window ----
    def t(self, key, **kw):
        return i18n.t(self.settings["ui_lang"], key, **kw)

    def secret(self, key_id: str) -> str:
        if self.screenshot:
            return ""
        if key_id not in self._secrets:
            self._secrets[key_id] = storage.get_key_secret(key_id)
        return self._secrets[key_id]

    def has_key(self) -> bool:
        return bool(self.pool.usable())

    def first_valid_secret(self) -> str:
        keys = self.pool.usable()
        return self.secret(keys[0]["id"]) if keys else ""

    def add_key(self, label: str, secret: str) -> None:
        keys = self.settings["keys"]
        if len(keys) >= MAX_KEYS or not secret.strip():
            return
        kid = storage.new_key_id(keys)
        storage.set_key_secret(kid, secret)
        self._secrets[kid] = secret.strip()
        keys.append({"id": kid, "label": label.strip() or f"Project {len(keys) + 1}", "enabled": True,
                     "invalid": False})
        self.settings.save()

    def remove_key(self, key_id: str) -> None:
        self.settings["keys"][:] = [k for k in self.settings["keys"] if k["id"] != key_id]
        storage.delete_key_secret(key_id)
        self._secrets.pop(key_id, None)
        self.pool.forget(key_id)
        self.settings.save()

    def move_key(self, key_id: str, delta: int) -> None:
        keys = self.settings["keys"]
        i = next(i for i, k in enumerate(keys) if k["id"] == key_id)
        j = i + delta
        if 0 <= j < len(keys):
            keys[i], keys[j] = keys[j], keys[i]
            self.settings.save()

    def test_key(self, key_id, model, callback):
        """callback(result_dict_or_None, key_error_or_None) on the GUI thread; also refreshes the model list."""
        secret = self.secret(key_id)

        def work():
            try:
                result, err = gemini_client.test_key(secret, model), None
            except UcapError as e:
                result, err = None, e

            def finish():
                if err is None or err.code != "offline":
                    self.pool.mark_invalid(key_id, err is not None and err.code == "invalid_key")
                    self.settings.save()
                self._got_models(result and result["models"])
                callback(result, err)
            self.post(("call", finish))
        threading.Thread(target=work, daemon=True).start()

    def refresh_models(self, callback):
        """callback(error_or_None) on the GUI thread after the cached model list is reloaded."""
        key = self.first_valid_secret()

        def work():
            try:
                models, err = gemini_client.list_models(key), None
            except UcapError as e:
                models, err = None, e
            self.post(("call", lambda: self._got_models(models) or callback(err)))
        threading.Thread(target=work, daemon=True).start()

    def _got_models(self, models):
        if models:
            self.settings["model_list"] = models
            self.settings.save()
            self.win.fill_models()

    def apply_settings(self) -> None:
        self.settings.save()
        self.machine.set_combo(self.settings["hotkey"])
        self.cmd_machine.set_combo(self.settings["command_hotkey"])
        if self.tray:
            self._bind_paste_hotkey()
        try:
            storage.set_autostart(bool(self.settings["start_with_windows"]))
        except OSError:
            pass
        self.win.refresh_status()

    def set_ui_lang(self, lang: str) -> None:
        self.settings["ui_lang"] = lang
        self.settings.save()
        self.win.build()

    def pause_hotkey(self, on: bool) -> None:
        self._hotkey_paused = on

    def copy_text(self, text: str) -> None:
        inserter.WinClipboard().set_text(text)

    def _on_paste_last(self) -> None:
        if self._hotkey_paused:  # the user is recording a new hotkey
            return
        if not self.history.items:
            self.pill.show_message(self.t("err_no_history"), error=True, ms=1800)
            return
        self.reinsert(self.history.items[0]["text"], minimize=False)

    def paste_last(self) -> None:
        self.post(("paste_last",))

    # ---- meetings ----
    def meeting_toggle(self) -> None:
        if self.meet and self.meet.state == "recording":
            self.meet.stop()
        elif not self.meet or self.meet.state == "done":
            if self.meet and self.meet.needs_retry and not self._confirm("confirm_new_meeting"):
                return  # starting a new one would drop the parts that still can be retried
            session = MeetingSession(self)
            try:
                session.start(self.settings["mic_device"])
            except UcapError as err:
                self._error(err)
                return
            self.meet = session
            self.pill.show_message(self.t("meet_started"), error=False, ms=1800)
        self._meeting_changed()

    def _on_meeting_hotkey(self) -> None:
        if self._hotkey_paused:  # the user is recording a new hotkey
            return
        was_recording = self.meet is not None and self.meet.state == "recording"
        self.meeting_toggle()
        if was_recording:
            self.pill.show_message(self.t("meet_stopping"), error=False, ms=2000)

    def meeting_retry(self) -> None:
        if self.meet:
            self.meet.retry()
            self._meeting_changed()

    def _meeting_changed(self) -> None:
        self.win.refresh_meeting()
        if self.tray:
            self.tray.set_meeting(bool(self.meet and self.meet.state == "recording"))

    def _on_meeting_progress(self) -> None:
        self.win.refresh_meeting()

    def _on_meeting_done(self, meeting, _err) -> None:
        if meeting is None:
            self.meet = None
            self.pill.show_message(self.t("meet_empty"), error=True, ms=3000)
        else:
            if not self.meet.needs_retry:
                self.meet = None
            self.pill.show_message(self.t("meet_saved", title=meeting["title"]), error=False, ms=4000)
        self.settings.save()
        self.win.refresh_keys()
        self._meeting_changed()
        self.win.refresh_meetings_list(select=meeting["id"] if meeting else None)

    def ask_notes(self, question: str, callback) -> None:
        """callback(answer_or_None, error_or_None) on the GUI thread."""
        notes = list(self.meetings.items)
        model, available = self.settings["model"], list(self.settings["model_list"])

        def work():
            try:
                context = meetings.build_context(notes, question)
                r = gemini_client.generate(self.pool, model, meetings.qa_prompt(),
                                           [f"{context}\n\n# Question\n{question}"], available,
                                           timeout_ms=meetings.CHUNK_TIMEOUT_MS, budget_s=120.0)
                out, err = r["text"], None
            except Exception as exc:  # noqa: BLE001
                out, err = None, gemini_client.classify_error(exc)
            self.post(("call", lambda: callback(out, err)))
        threading.Thread(target=work, daemon=True).start()

    def export_settings(self, path: str) -> None:
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(storage.export_settings(self.settings), f, ensure_ascii=False, indent=2)

    def import_settings(self, path: str) -> int:
        import json
        with open(path, encoding="utf-8") as f:
            applied = storage.import_settings(self.settings, json.load(f))
        self.apply_settings()
        self.win.build()
        return len(applied)

    def reinsert(self, text: str, minimize: bool = True) -> None:
        # minimise our window so the previous app gets focus back, then paste there
        if minimize:
            self.win.showMinimized()

        def work():
            if minimize:
                time.sleep(0.45)
            else:
                inserter.wait_keys_released()
            result = inserter.insert_text(text, inserter.WinClipboard(), inserter.send_ctrl_v,
                                          can_paste=inserter.can_paste_into_foreground())
            if result == "clipboard":
                self.post(("done", text, result))
        threading.Thread(target=work, daemon=True).start()


def single_instance() -> bool:
    k32 = ctypes.windll.kernel32
    single_instance.handle = k32.CreateMutexW(None, False, "Local\\UcapDictationSingleton")
    return k32.GetLastError() != 183  # ERROR_ALREADY_EXISTS
