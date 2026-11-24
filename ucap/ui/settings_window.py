"""Settings window (opened from the tray). Closing it only hides it; Ucap keeps running in the tray."""
from __future__ import annotations

import html
import threading
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                               QScrollArea, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget)

from .. import i18n, meetings
from ..audio import list_input_devices
from ..dictionary import suggest_terms
from ..gemini_client import DEFAULT_MODEL, FALLBACK_MODELS, LANGUAGE_NAMES
from ..hotkey import format_combo, normalize_key
from ..keypool import MAX_KEYS, mask
from ..styles import APP_STYLES, STYLES
from . import theme as th

LANGS = ("auto", "id", "en", *LANGUAGE_NAMES)
TABS = ("general", "gemini", "dict", "snippets", "styles", "history", "meetings", "stats")


class _Bars(QWidget):
    """Small bar chart: one bar per (day, value)."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(150)
        self.data: list[tuple] = []

    def set_data(self, data):
        self.data = data
        self.update()

    def paintEvent(self, _):
        if not self.data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        top = max(max(v for _, v in self.data), 1)
        slot = w / len(self.data)
        for i, (day, v) in enumerate(self.data):
            bar_h = (h - 40) * v / top
            x = i * slot + slot * 0.2
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(th.ACCENT if v else th.MUTED).lighter(100 if v else 170))
            p.drawRoundedRect(QRectF(x, h - 22 - bar_h, slot * 0.6, max(bar_h, 3)), 4, 4)
            p.setPen(QColor(th.MUTED))
            p.drawText(QRectF(i * slot, h - 20, slot, 20), Qt.AlignCenter, f"{day.day}/{day.month}")
            if v:
                p.drawText(QRectF(i * slot, h - 22 - bar_h - 18, slot, 16), Qt.AlignCenter, str(v))
        p.end()


class _Logo(QWidget):
    def __init__(self, size):
        super().__init__()
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        paint_size = self.width() - 2
        th.paint_logo(p, QRectF(1, 1, paint_size, paint_size))
        p.end()


def _esc(text):
    return html.escape(text or "")


def _label(text, name=None, wrap=False):
    lb = QLabel(text)
    if wrap:
        lb.setMinimumHeight(38 if name == "Muted" else 0)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


def _button(text, accent=False, slot=None):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    if accent:
        b.setProperty("accent", True)
    if slot:
        b.clicked.connect(slot)
    return b


def _table(headers, stretch_last=True):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().hide()
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setShowGrid(False)
    t.setWordWrap(False)
    t.verticalHeader().setDefaultSectionSize(30)
    t.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    t.horizontalHeader().setHighlightSections(False)
    if stretch_last:
        t.horizontalHeader().setStretchLastSection(True)
    return t


def _fill(table, rows):
    table.setRowCount(0)
    for row in rows:
        r = table.rowCount()
        table.insertRow(r)
        for c, v in enumerate(row):
            table.setItem(r, c, QTableWidgetItem(v))


def _sel(table):
    rows = table.selectionModel().selectedRows()
    return rows[0].row() if rows else None


class SettingsWindow(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("Root")
        self.setWindowTitle("Ucap")
        self.setWindowIcon(th.logo_icon())
        self.resize(820, 700)
        self.setMinimumSize(660, 520)
        self.tab_index = 0
        self._meet_view = "notes"
        self._meet_tick = QTimer(self, interval=1000, timeout=self.refresh_meeting)
        self._meet_tick.start()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 16)
        self._layout.setSpacing(0)
        self.build()

    def t(self, key, **kw):
        return i18n.t(self.app.settings["ui_lang"], key, **kw)

    def show_tab(self, tab=None):
        if tab in TABS:
            self.tabs.setCurrentIndex(TABS.index(tab))
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        e.ignore()
        self.hide()

    # ---- build ----
    def build(self):
        while self._layout.count():
            w = self._layout.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self._layout.addWidget(self._header())
        self._layout.addWidget(self._status())
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        for key, builder in zip(TABS, (self._tab_general, self._tab_gemini, self._tab_dict, self._tab_snippets,
                                       self._tab_styles, self._tab_history, self._tab_meetings,
                                       self._tab_stats)):
            page = QWidget()
            page.setObjectName("Card")
            page.setAttribute(Qt.WA_StyledBackground)
            lay = QVBoxLayout(page)
            lay.setContentsMargins(20, 18, 20, 18)
            builder(lay)
            scroll = QScrollArea()  # a tab taller than the window scrolls instead of squeezing its widgets
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(page)
            self.tabs.addTab(scroll, self.t(f"tab_{key}"))
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(16, 6, 16, 0)
        wl.addWidget(self.tabs)
        self._layout.addWidget(wrap, 1)
        self.tabs.setCurrentIndex(self.tab_index)
        self.tabs.currentChanged.connect(lambda i: setattr(self, "tab_index", i))
        self.refresh_status()

    def _header(self):
        h = QFrame()
        h.setObjectName("Header")
        h.setFixedHeight(78)
        lay = QHBoxLayout(h)
        lay.setContentsMargins(22, 0, 22, 0)
        lay.addWidget(_Logo(42))
        lay.addSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addStretch()
        col.addWidget(_label("Ucap", "Title"))
        col.addWidget(_label(self.t("tagline"), "Tagline"))
        col.addStretch()
        lay.addLayout(col)
        lay.addStretch()
        seg = QFrame()
        seg.setObjectName("Seg")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(2)
        for code in ("id", "en"):
            b = QPushButton(code.upper())
            b.setCheckable(True)
            b.setChecked(self.app.settings["ui_lang"] == code)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=code: self.app.set_ui_lang(c))
            sl.addWidget(b)
        lay.addWidget(seg, 0, Qt.AlignVCenter)
        return h

    def _status(self):
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(16, 12, 16, 4)
        s = QFrame()
        s.setObjectName("Status")
        lay = QHBoxLayout(s)
        lay.setContentsMargins(12, 9, 12, 9)
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(10, 10)
        lay.addWidget(self.status_dot)
        lay.addSpacing(4)
        self.status_lbl = QLabel()
        lay.addWidget(self.status_lbl, 1)
        self.hk_badge = _label("", "HkBadge")
        lay.addWidget(self.hk_badge)
        wl.addWidget(s)
        return wrap

    def refresh_status(self):
        ok = self.app.has_key()
        hk = format_combo(self.app.settings["hotkey"])
        self.status_lbl.setText(self.t("status_ready", hk=hk) if ok else self.t("status_nokey"))
        self.hk_badge.setText(hk)
        s = self.app.settings
        self.hk_badge.setToolTip(" · ".join(f"{self.t(lb)}: {format_combo(s[k])}" for k, lb in self.app.HOTKEYS))
        self.status_dot.setStyleSheet(f"background:{th.OK if ok else th.ACCENT}; border-radius:5px;")

    def _changed(self, key, value):
        self.app.settings[key] = value
        self.app.apply_settings()

    # ---- General ----
    def _tab_general(self, lay):
        s = self.app.settings
        lay.addWidget(_label(self.t("sec_hotkeys"), "Field"))
        g = QGridLayout()
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(10)
        g.setColumnStretch(1, 1)
        self._hk_row(g, 0, "hotkey", "hotkey")
        g.addWidget(_label(self.t("hotkey_help"), "Muted", wrap=True), 1, 1)
        self._hk_row(g, 2, "cmd_hotkey", "command_hotkey")
        g.addWidget(_label(self.t("cmd_help"), "Muted", wrap=True), 3, 1)
        self._hk_row(g, 4, "paste_hotkey", "paste_hotkey")
        self._hk_row(g, 5, "meet_hotkey", "meeting_hotkey")
        self.hk_warn = QLabel(self.t("hotkey_conflict_saved"))
        self.hk_warn.setWordWrap(True)
        self.hk_warn.setStyleSheet(f"color:{th.ERR}; font-weight:700;")
        self.hk_warn.setVisible(self.app.hotkey_conflicts())
        g.addWidget(self.hk_warn, 6, 1)

        g.addWidget(_label(self.t("mic"), "Field"), 7, 0)
        devices = list_input_devices()
        self._dev_ids = [None] + [i for i, _ in devices]
        mic = QComboBox()
        mic.addItems([self.t("mic_default")] + [n for _, n in devices])
        mic.setCurrentIndex(self._dev_ids.index(s["mic_device"]) if s["mic_device"] in self._dev_ids else 0)
        mic.setMinimumWidth(340)
        mic.currentIndexChanged.connect(lambda i: self._changed("mic_device", self._dev_ids[i]))
        g.addWidget(mic, 7, 1, Qt.AlignLeft)

        g.addWidget(_label(self.t("language"), "Field"), 8, 0)
        lang = QComboBox()
        lang.addItems([LANGUAGE_NAMES[c] if c in LANGUAGE_NAMES else self.t(f"lang_{c}") for c in LANGS])
        lang.setCurrentIndex(LANGS.index(s["language"]) if s["language"] in LANGS else 0)
        lang.setMinimumWidth(180)
        lang.currentIndexChanged.connect(lambda i: self._changed("language", LANGS[i]))
        g.addWidget(lang, 8, 1, Qt.AlignLeft)
        lay.addLayout(g)

        sep = QFrame()
        sep.setObjectName("Sep")
        lay.addSpacing(8)
        lay.addWidget(sep)
        lay.addSpacing(8)
        lay.addWidget(_label(self.t("sec_options"), "Field"))
        for key, label in (("sound_cues", "sound_cues"), ("voice_send", "voice_send"), ("use_window_title", "use_window_title"),
                           ("check_updates", "check_updates"),
                           ("start_with_windows", "autostart"), ("keep_audio", "keep_audio")):
            cb = QCheckBox(self.t(label))
            cb.setChecked(bool(s[key]))
            cb.toggled.connect(lambda v, k=key: self._changed(k, v))
            lay.addWidget(cb)
        io = QHBoxLayout()
        io.addWidget(_button(self.t("export"), slot=self._export))
        io.addWidget(_button(self.t("import"), slot=self._import))
        io.addWidget(_label(self.t("export_note"), "Muted"), 1)
        lay.addLayout(io)
        lay.addStretch()

    def _hk_row(self, g, row, label, key):
        g.addWidget(_label(self.t(label), "Field"), row, 0)
        box = QHBoxLayout()
        edit = QLineEdit(format_combo(self.app.settings[key]))
        edit.setReadOnly(True)
        edit.setFixedWidth(170)
        btn = _button(self.t("hotkey_record"))
        btn.clicked.connect(lambda: self._record_hotkey(key, edit, btn))
        box.addWidget(edit)
        box.addWidget(btn)
        box.addStretch()
        g.addLayout(box, row, 1)

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Ucap", "ucap-settings.json", self.t("json_files"))
        if path:
            self.app.export_settings(path)
            QMessageBox.information(self, "Ucap", self.t("exported"))

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Ucap", "", self.t("json_files"))
        if not path or QMessageBox.question(self, "Ucap", self.t("confirm_import")) != QMessageBox.Yes:
            return
        try:
            n = self.app.import_settings(path)
        except (OSError, ValueError):
            QMessageBox.warning(self, "Ucap", self.t("import_bad"))
            return
        QMessageBox.information(self, "Ucap", self.t("imported", n=n))

    def _record_hotkey(self, key, edit, btn):
        btn.setText(self.t("hotkey_press"))
        btn.setEnabled(False)
        self.app.pause_hotkey(True)

        def work():
            try:
                import keyboard
                combo = keyboard.read_hotkey(suppress=False)
            except Exception:
                combo = ""
            self.app.post(("call", lambda: done(combo)))

        def done(combo):
            self.app.pause_hotkey(False)
            btn.setText(self.t("hotkey_record"))
            btn.setEnabled(True)
            keys = list(dict.fromkeys(normalize_key(k) for k in combo.split("+") if k.strip()))
            if keys and keys != ["esc"]:
                value = "+".join(keys)
                other = self.app.hotkey_conflict(key, value)
                if other:
                    QMessageBox.warning(self, "Ucap", self.t("hotkey_conflict", other=self.t(other)))
                    return
                edit.setText(format_combo(value))
                self._changed(key, value)
                self.hk_warn.setVisible(self.app.hotkey_conflicts())
                self.refresh_status()

        threading.Thread(target=work, daemon=True).start()

    # ---- Gemini ----
    def _tab_gemini(self, lay):
        self._key_msg: dict[str, tuple[str, str]] = {}
        lay.addWidget(_label(self.t("keys_title"), "Field"))
        lay.addWidget(_label(self.t("keys_note"), "Muted", wrap=True))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumHeight(150)
        inner = QWidget()
        inner.setObjectName("Card")
        self.keys_layout = QVBoxLayout(inner)
        self.keys_layout.setContentsMargins(0, 4, 6, 4)
        self.keys_layout.setSpacing(6)
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)

        add = QHBoxLayout()
        self.new_label = QLineEdit()
        self.new_label.setPlaceholderText(self.t("key_label_ph"))
        self.new_label.setFixedWidth(150)
        self.new_secret = QLineEdit()
        self.new_secret.setEchoMode(QLineEdit.Password)
        self.new_secret.setPlaceholderText("AIza…")
        self.add_btn = _button(self.t("add_key"), True, self._add_key)
        add.addWidget(self.new_label)
        add.addWidget(self.new_secret, 1)
        add.addWidget(self.add_btn)
        lay.addLayout(add)
        self.key_status = _label("", wrap=True)
        self.key_status.hide()
        lay.addWidget(self.key_status)

        sep = QFrame()
        sep.setObjectName("Sep")
        lay.addSpacing(6)
        lay.addWidget(sep)
        lay.addSpacing(6)
        mrow = QHBoxLayout()
        mrow.addWidget(_label(self.t("model"), "Field"))
        mrow.addSpacing(12)
        self.model_box = QComboBox()
        self.model_box.setEditable(True)
        self.model_box.setMinimumWidth(260)
        self.fill_models()
        self.model_box.currentTextChanged.connect(
            lambda v: self._changed("model", v.strip() or DEFAULT_MODEL))
        mrow.addWidget(self.model_box)
        self.refresh_btn = _button(self.t("refresh"), slot=self._refresh_models)
        mrow.addWidget(self.refresh_btn)
        mrow.addStretch()
        lay.addLayout(mrow)
        lay.addWidget(_label(self.t("model_note", default=DEFAULT_MODEL), "Muted", wrap=True))
        self.refresh_keys()

    def refresh_keys(self):
        lay = self.keys_layout
        while lay.count():
            w = lay.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        keys = self.app.settings["keys"]
        if not keys:
            lay.addWidget(_label(self.t("keys_empty"), "Muted", wrap=True))
        for i, k in enumerate(keys):
            lay.addWidget(self._key_row(k, i, len(keys)))
        lay.addStretch()
        full = len(keys) >= MAX_KEYS
        self.add_btn.setEnabled(not full)
        self.add_btn.setText(self.t("keys_full") if full else self.t("add_key"))
        self.refresh_status()

    def _key_state(self, k):
        kid = k["id"]
        if not self.app.secret(kid):
            return self.t("ks_missing"), th.ERR
        if k.get("invalid"):
            return self.t("ks_invalid"), th.ERR
        if not k.get("enabled", True):
            return self.t("ks_disabled"), th.MUTED
        blocks = self.app.pool.blocks_for(kid)
        if not blocks:
            return self.t("ks_ok"), th.OK
        now = time.time()
        parts = [self.t("ks_daily", model=m, time=time.strftime("%H:%M", time.localtime(u))) if daily
                 else self.t("ks_minute", model=m, secs=max(1, int(u - now))) for m, u, daily in blocks]
        return "; ".join(parts), th.ACCENT_DARK

    def _key_row(self, k, i, n):
        kid = k["id"]
        row = QFrame()
        row.setObjectName("KeyRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 8, 10, 8)
        cb = QCheckBox()
        cb.setChecked(k.get("enabled", True))
        cb.setToolTip(self.t("key_enabled"))
        cb.toggled.connect(lambda v: self._toggle_key(k, v))
        h.addWidget(cb, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(1)
        secret = self.app.secret(kid)
        col.addWidget(QLabel(f"<b>{_esc(k.get('label', ''))}</b>&nbsp;&nbsp;"
                             f"<span style='color:{th.MUTED}'>{_esc(mask(secret)) if secret else ''}</span>"))
        text, color = self._key_state(k)
        st = QLabel(text)
        st.setWordWrap(True)
        st.setStyleSheet(f"color:{color}; font-weight:700; font-size:9pt;")
        col.addWidget(st)
        counts = self.app.pool.today_counts(kid)
        used = " · ".join(f"{m.removeprefix('gemini-')} {c}" for m, c in sorted(counts.items()))
        col.addWidget(_label(self.t("ks_today", counts=used or "0"), "Muted"))
        if kid in self._key_msg:
            msg, mcolor = self._key_msg[kid]
            ml = QLabel(msg)
            ml.setWordWrap(True)
            ml.setStyleSheet(f"color:{mcolor}; font-size:9pt;")
            col.addWidget(ml)
        h.addLayout(col, 1)
        for text, slot, enabled in ((self.t("test_key"), lambda: self._test_key(kid), True),
                                    ("▲", lambda: self._move_key(kid, -1), i > 0),
                                    ("▼", lambda: self._move_key(kid, 1), i < n - 1),
                                    (self.t("remove"), lambda: self._remove_key(k), True)):
            b = _button(text, slot=slot)
            b.setEnabled(enabled)
            if text in ("▲", "▼"):
                b.setFixedWidth(34)
            h.addWidget(b, 0, Qt.AlignTop)
        return row

    def _toggle_key(self, k, on):
        k["enabled"] = on
        self.app.settings.save()
        self.refresh_keys()

    def _move_key(self, kid, delta):
        self.app.move_key(kid, delta)
        self.refresh_keys()

    def _remove_key(self, k):
        ask = self.t("confirm_remove_key", label=k.get("label", ""))
        if QMessageBox.question(self, "Ucap", ask) == QMessageBox.Yes:
            self.app.remove_key(k["id"])
            self._key_msg.pop(k["id"], None)
            self.refresh_keys()

    def _add_key(self):
        secret = self.new_secret.text().strip()
        if not secret:
            return
        try:
            self.app.add_key(self.new_label.text(), secret)
        except Exception as exc:  # keyring failure
            self._set_key_status(str(exc), th.ERR)
            return
        self.new_label.clear()
        self.new_secret.clear()
        self.key_status.hide()
        self.refresh_keys()

    def fill_models(self):
        box = self.model_box
        box.blockSignals(True)
        box.clear()
        box.addItems(self.app.settings["model_list"] or FALLBACK_MODELS)
        box.setCurrentText(self.app.settings["model"])
        box.blockSignals(False)

    def _refresh_models(self):
        self.refresh_btn.setEnabled(False)

        def done(err):
            self.refresh_btn.setEnabled(True)
            if err:
                self._set_key_status(i18n.error_text(self.app.settings["ui_lang"], err), th.ERR)

        self.app.refresh_models(done)

    def _set_key_status(self, text, color):
        self.key_status.setText(text)
        self.key_status.show()
        self.key_status.setStyleSheet(f"color:{color}; font-weight:700;")

    def _test_key(self, kid):
        model = self.model_box.currentText().strip() or DEFAULT_MODEL
        self._key_msg[kid] = (self.t("testing"), th.MUTED)
        self.refresh_keys()

        def done(result, err):
            if err is not None:
                self._key_msg[kid] = (i18n.error_text(self.app.settings["ui_lang"], err), th.ERR)
            elif result["model_error"] is None:
                self._key_msg[kid] = (self.t("key_ok", model=model, secs=f"{result['elapsed']:.1f}"), th.OK)
            else:
                self._key_msg[kid] = (self.t("key_ok_model_bad", model=model, default=DEFAULT_MODEL), th.ACCENT_DARK)
            self.refresh_keys()

        self.app.test_key(kid, model, done)

    # ---- Dictionary ----
    def _tab_dict(self, lay):
        lay.addWidget(_label(self.t("dict_help"), "Muted", wrap=True))
        row = QHBoxLayout()
        entry = QLineEdit()
        entry.setPlaceholderText("PT Sinar Jaya, Kubernetes, Bu Ratna…")
        row.addWidget(entry, 1)
        table = _table([self.t("text")])
        words = self.app.settings["dictionary"]

        def refresh():
            _fill(table, [(w,) for w in words])

        def add():
            w = entry.text().strip()
            if w and w not in words:
                words.append(w)
                self.app.apply_settings()
                refresh()
            entry.clear()

        def remove():
            i = _sel(table)
            if i is not None:
                del words[i]
                self.app.apply_settings()
                refresh()

        def suggest():
            found = suggest_terms([e["text"] for e in self.app.history.items], words)
            if not found:
                QMessageBox.information(self, "Ucap", self.t("dict_suggest_none"))
            elif QMessageBox.question(self, "Ucap", self.t("dict_suggest_ask") + "\n\n" + ", ".join(found)) == QMessageBox.Yes:
                words.extend(found)
                self.app.apply_settings()
                refresh()

        entry.returnPressed.connect(add)
        row.addWidget(_button(self.t("add"), True, add))
        row.addWidget(_button(self.t("remove"), slot=remove))
        row.addWidget(_button(self.t("dict_suggest"), slot=suggest))
        lay.addLayout(row)
        lay.addWidget(table, 1)
        self.refresh_dict = refresh
        refresh()

    # ---- Snippets ----
    def _tab_snippets(self, lay):
        lay.addWidget(_label(self.t("snip_help"), "Muted", wrap=True))
        table = _table([self.t("trigger"), self.t("expansion")])
        table.setColumnWidth(0, 200)
        lay.addWidget(table, 1)
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setColumnStretch(1, 1)
        trig = QLineEdit()
        trig.setPlaceholderText("tanda tangan email")
        exp = QPlainTextEdit()
        exp.setFixedHeight(70)
        exp.setPlaceholderText("Salam,\nNama Anda\n0812-…")
        g.addWidget(_label(self.t("trigger"), "Field"), 0, 0)
        g.addWidget(trig, 0, 1)
        g.addWidget(_label(self.t("expansion"), "Field"), 1, 0, Qt.AlignTop)
        g.addWidget(exp, 1, 1)
        snips = self.app.settings["snippets"]

        def refresh():
            _fill(table, [(s["trigger"], s["expansion"].replace("\n", " ⏎ ")) for s in snips])

        def on_select():
            i = _sel(table)
            if i is not None:
                trig.setText(snips[i]["trigger"])
                exp.setPlainText(snips[i]["expansion"])

        def save(new):
            tr, ex = trig.text().strip(), exp.toPlainText().rstrip("\n")
            if not tr or not ex:
                return
            i = _sel(table)
            if new or i is None:
                snips.append({"trigger": tr, "expansion": ex})
            else:
                snips[i] = {"trigger": tr, "expansion": ex}
            self.app.apply_settings()
            refresh()

        def remove():
            i = _sel(table)
            if i is not None:
                del snips[i]
                self.app.apply_settings()
                refresh()

        table.itemSelectionChanged.connect(on_select)
        btns = QHBoxLayout()
        btns.addWidget(_button(self.t("add"), True, lambda: save(True)))
        btns.addWidget(_button(self.t("edit"), slot=lambda: save(False)))
        btns.addWidget(_button(self.t("remove"), slot=remove))
        btns.addStretch()
        g.addLayout(btns, 2, 1)
        lay.addLayout(g)
        refresh()

    # ---- Per-app styles ----
    def _tab_styles(self, lay):
        lay.addWidget(_label(self.t("styles_help"), "Muted", wrap=True))
        names = [self.t(f"style_{s}") for s in STYLES]
        top = QHBoxLayout()
        top.addWidget(_label(self.t("default_style"), "Field"))
        dflt = QComboBox()
        dflt.addItems(names)
        ds = self.app.settings["default_style"]
        dflt.setCurrentIndex(STYLES.index(ds) if ds in STYLES else 1)
        dflt.currentIndexChanged.connect(lambda i: self._changed("default_style", STYLES[i]))
        top.addWidget(dflt)
        top.addStretch()
        lay.addLayout(top)
        table = _table([self.t("app_exe"), self.t("style")])
        table.setColumnWidth(0, 340)
        lay.addWidget(table, 1)
        m = self.app.settings["app_styles"]
        keys: list[str] = []
        form = QHBoxLayout()
        exe = QLineEdit()
        exe.setPlaceholderText("Notion.exe")
        sty = QComboBox()
        sty.addItems([self.t(f"style_{x}") for x in APP_STYLES])
        sty.setCurrentIndex(1)

        def refresh():
            keys[:] = sorted(m, key=str.lower)
            _fill(table, [(k, self.t(f"style_{m[k]}")) for k in keys])

        def on_select():
            i = _sel(table)
            if i is not None:
                exe.setText(keys[i])
                sty.setCurrentIndex(APP_STYLES.index(m[keys[i]]) if m[keys[i]] in APP_STYLES else 1)

        def save():
            e = exe.text().strip()
            if e:
                if not e.lower().endswith((".exe", ".bin")):
                    e += ".exe"
                for k in [k for k in m if k.lower() == e.lower()]:
                    del m[k]
                m[e] = APP_STYLES[sty.currentIndex()]
                self.app.apply_settings()
                refresh()

        def remove():
            i = _sel(table)
            if i is not None:
                m.pop(keys[i], None)
                self.app.apply_settings()
                refresh()

        table.itemSelectionChanged.connect(on_select)
        form.addWidget(exe, 1)
        form.addWidget(sty)
        form.addWidget(_button(self.t("save"), True, save))
        form.addWidget(_button(self.t("remove"), slot=remove))
        lay.addLayout(form)
        refresh()

    # ---- History ----
    def _tab_history(self, lay):
        btns = QHBoxLayout()
        table = _table([self.t("time"), self.t("app"), self.t("via_col"), self.t("text")])
        table.setColumnWidth(0, 140)
        table.setColumnWidth(1, 120)
        table.setColumnWidth(2, 150)
        self.hist_table = table
        items = lambda: self.app.history.items  # noqa: E731

        def current():
            i = _sel(table)
            return items()[i] if i is not None and i < len(items()) else None

        def copy():
            e = current()
            if e:
                self.app.copy_text(e["text"])

        def reinsert():
            e = current()
            if e:
                self.app.reinsert(e["text"])

        def add_dict():
            e = current()
            if not e:
                return
            word, ok = QInputDialog.getText(self, "Ucap", self.t("add_dict_prompt"), text=e["text"][:60])
            word = word.strip()
            if ok and word and word not in self.app.settings["dictionary"]:
                self.app.settings["dictionary"].append(word)
                self.app.apply_settings()
                self.refresh_dict()

        def remove():
            i = _sel(table)
            if i is not None:
                self.app.history.remove(i)
                self.refresh_history()

        def clear():
            if QMessageBox.question(self, "Ucap", self.t("confirm_clear")) == QMessageBox.Yes:
                self.app.history.clear()
                self.refresh_history()

        btns.addWidget(_button(self.t("copy"), True, copy))
        btns.addWidget(_button(self.t("reinsert"), slot=reinsert))
        btns.addWidget(_button(self.t("add_dict"), slot=add_dict))
        btns.addWidget(_button(self.t("remove"), slot=remove))
        btns.addStretch()
        btns.addWidget(_button(self.t("clear_all"), slot=clear))
        lay.addLayout(btns)
        lay.addWidget(table, 1)
        table.doubleClicked.connect(lambda _: copy())
        self.refresh_history()

    def refresh_history(self):
        _fill(self.hist_table, [(e["time"], e["app"],
                                 " · ".join(x for x in (e.get("key", ""), e.get("model", "").removeprefix("gemini-")) if x),
                                 e["text"].replace("\n", " ⏎ "))
                                for e in self.app.history.items])

    # ---- Meetings ----
    def _tab_meetings(self, lay):
        lay.addWidget(_label(self.t("meet_help"), "Muted", wrap=True))
        for key in ("meeting_system_audio", "meeting_screen_speakers"):
            cb = QCheckBox(self.t(key.replace("meeting_", "meet_")))
            cb.setChecked(bool(self.app.settings[key]))
            cb.toggled.connect(lambda v, k=key: self._changed(k, v))
            lay.addWidget(cb)
        top = QHBoxLayout()
        self.meet_btn = _button("", True, self.app.meeting_toggle)
        self.meet_retry_btn = _button(self.t("meet_retry"), slot=self.app.meeting_retry)
        self.meet_status = _label("", wrap=True)
        top.addWidget(self.meet_btn)
        top.addWidget(self.meet_retry_btn)
        top.addWidget(self.meet_status, 1)
        lay.addLayout(top)
        self.meet_bar = QProgressBar()
        self.meet_bar.setTextVisible(False)
        self.meet_bar.setFixedHeight(6)
        self.meet_bar.hide()
        lay.addWidget(self.meet_bar)

        self.meet_filter = QLineEdit()
        self.meet_filter.setPlaceholderText(self.t("meet_search_ph"))
        self.meet_filter.setClearButtonEnabled(True)
        self.meet_filter.textChanged.connect(lambda _: self.refresh_meetings_list())
        lay.addWidget(self.meet_filter)
        table = _table([self.t("meet_col_title"), self.t("meet_col_date"), self.t("meet_col_len")])
        table.setColumnWidth(0, 330)
        table.setColumnWidth(1, 130)
        table.setMinimumHeight(96)
        self.meet_table = table
        self._meet_rows = []
        lay.addWidget(table, 1)
        detail = QTextEdit()
        detail.setReadOnly(True)
        self.meet_detail = detail
        btns = QHBoxLayout()
        self._meet_btns = {}
        for view in ("notes", "transcript"):
            b = _button(self.t(f"meet_{view}"), slot=lambda _=False, v=view: self._meet_show(v))
            b.setCheckable(True)
            self._meet_btns[view] = b
            btns.addWidget(b)
        btns.addWidget(_button(self.t("meet_rename"), slot=self._meet_rename))
        btns.addWidget(_button(self.t("meet_copy"), slot=self._meet_copy))
        btns.addWidget(_button(self.t("meet_export"), slot=self._meet_export))
        btns.addStretch()
        btns.addWidget(_button(self.t("meet_delete"), slot=self._meet_delete))
        lay.addLayout(btns)
        lay.addWidget(detail, 2)
        table.itemSelectionChanged.connect(lambda: self._meet_show(self._meet_view))

        lay.addWidget(_label(self.t("meet_ask_title"), "Field"))
        ask = QHBoxLayout()
        self.meet_q = QLineEdit()
        self.meet_q.setPlaceholderText(self.t("meet_ask_ph"))
        self.meet_ask_btn = _button(self.t("meet_ask"), True, self._meet_ask)
        self.meet_q.returnPressed.connect(self._meet_ask)
        ask.addWidget(self.meet_q, 1)
        ask.addWidget(self.meet_ask_btn)
        lay.addLayout(ask)
        self.meet_answer = QTextEdit()
        self.meet_answer.setReadOnly(True)
        self.meet_answer.setFixedHeight(76)
        lay.addWidget(self.meet_answer)
        self.refresh_meetings_list()
        self.refresh_meeting()

    def _meet_current(self):
        i = _sel(self.meet_table)
        return self._meet_rows[i] if i is not None and i < len(self._meet_rows) else None

    def _meet_show(self, view):
        self._meet_view = view
        for k, b in self._meet_btns.items():
            b.setChecked(k == view)
        m = self._meet_current()
        if not m:
            self.meet_detail.clear()
        elif view == "notes":
            self.meet_detail.setMarkdown(m["summary"])
        else:
            self.meet_detail.setPlainText(m["transcript"])

    def _meet_copy(self):
        m = self._meet_current()
        if m:
            self.app.copy_text(m["summary"])

    def _meet_rename(self):
        m = self._meet_current()
        if not m:
            return
        title, ok = QInputDialog.getText(self, "Ucap", self.t("meet_rename_prompt"), text=m["title"])
        if ok and title.strip():
            self.app.meetings.update(m["id"], title=title.strip())
            self.refresh_meetings_list(select=m["id"])

    def _meet_export(self):
        m = self._meet_current()
        if not m:
            return
        name = "".join(c for c in m["title"] if c not in '\\/:*?"<>|').strip() or "rapat"
        path, _ = QFileDialog.getSaveFileName(self, "Ucap", f"{name}.md", self.t("md_files"))
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(meetings.to_markdown(m))
            QMessageBox.information(self, "Ucap", self.t("exported"))

    def _meet_delete(self):
        m = self._meet_current()
        if m and QMessageBox.question(self, "Ucap", self.t("confirm_delete_meeting")) == QMessageBox.Yes:
            self.app.meetings.remove(m["id"])
            self.refresh_meetings_list()

    def _meet_ask(self):
        q = self.meet_q.text().strip()
        if not q:
            return
        if not self.app.meetings.items:
            self.meet_answer.setPlainText(self.t("meet_no_notes"))
            return
        self.meet_ask_btn.setEnabled(False)
        self.meet_answer.setPlainText(self.t("meet_asking"))

        def done(answer, err):
            self.meet_ask_btn.setEnabled(True)
            if err is not None:
                self.meet_answer.setPlainText(i18n.error_text(self.app.settings["ui_lang"], err))
            else:
                self.meet_answer.setMarkdown(answer)

        self.app.ask_notes(q, done)

    def refresh_meetings_list(self, select=None):
        """Rebuild the list (filtered by the search box); keeps the selected meeting, or selects `select`."""
        try:
            keep = select or (self._meet_current() or {}).get("id")
            self._meet_rows = meetings.search(self.app.meetings.items, self.meet_filter.text())
            _fill(self.meet_table, [(m["title"], m["started"], f"{max(1, m['secs'] // 60)} min")
                                    for m in self._meet_rows])
            for i, m in enumerate(self._meet_rows):
                if m["id"] == keep:
                    self.meet_table.selectRow(i)
            self._meet_show(self._meet_view)
        except (RuntimeError, AttributeError):  # window being rebuilt
            pass

    def refresh_meeting(self):
        try:
            m = self.app.meet
            rec = m is not None and m.state == "recording"
            busy = m is not None and m.state == "processing"
            self.meet_btn.setText(self.t("meet_stop" if rec else "meet_start"))
            self.meet_btn.setEnabled(not busy)
            self.meet_retry_btn.setVisible(m is not None and m.state == "done" and m.needs_retry)
            self.meet_bar.setVisible(busy)
            if rec:
                e = m.elapsed()
                text = self.t("meet_recording", time=f"{e // 60}:{e % 60:02d}")
                if self.app.settings["meeting_system_audio"] and m.loop is None:
                    text += " · " + self.t("meet_mic_only")
            elif busy:
                self.meet_bar.setMaximum(max(1, m.total))
                self.meet_bar.setValue(m.done)
                text = self.t("meet_working", done=m.done, total=m.total)
            elif m is not None:
                text = self.t("meet_missing", n=max(1, len(m.failed)))
            else:
                text = self.t("meet_idle")
            self.meet_status.setText(text)
        except (RuntimeError, AttributeError):
            pass

    # ---- Stats ----
    def _tab_stats(self, lay):
        g = QGridLayout()
        g.setHorizontalSpacing(24)
        g.setVerticalSpacing(14)
        g.setColumnStretch(2, 1)
        self.stat_vals = {}
        for i, (label, key) in enumerate((("stat_today", "words_today"), ("stat_week", "words_week"),
                                          ("stat_total", "words_total"), ("stat_count", "count_total"),
                                          ("stat_wpm", "wpm"), ("stat_streak", "streak"))):
            g.addWidget(_label(self.t(label), "Field"), i, 0)
            v = QLabel("0")
            v.setStyleSheet("font-size:16pt; font-weight:700;")
            g.addWidget(v, i, 1)
            self.stat_vals[key] = v
        lay.addLayout(g)
        lay.addSpacing(10)
        lay.addWidget(_label(self.t("stat_chart"), "Field"))
        self.stat_chart = _Bars()
        lay.addWidget(self.stat_chart)
        lay.addStretch()
        self.refresh_stats()

    def refresh_stats(self):
        try:
            for key, v in self.app.stats.summary().items():
                self.stat_vals[key].setText(f"{v:.0f}" if key == "wpm" else f"{v:,}".replace(",", "."))
            self.stat_chart.set_data(self.app.stats.last_days())
        except (RuntimeError, AttributeError):
            pass
