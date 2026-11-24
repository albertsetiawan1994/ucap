"""UcapApp._process end to end with Gemini and the Windows paste/clipboard calls replaced."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from ucap import gemini_client, inserter, storage  # noqa: E402

JOB = {"wav": b"", "prompt": "p", "snippets": [], "target": (0, "wa.exe"), "command": False,
       "voice_send": True, "secs": 3.0}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from ucap.app import UcapApp
    a = UcapApp(screenshot=str(tmp_path / "x.png"))
    a.log, a.seen = [], {"reply": "Oke aku jalan. Tekan enter", "selection": "teks panjang"}
    monkeypatch.setattr(inserter, "wait_keys_released", lambda *x, **k: None)
    monkeypatch.setattr(inserter, "can_paste_into_foreground", lambda: True)
    monkeypatch.setattr(inserter, "WinClipboard", lambda: None)
    monkeypatch.setattr(inserter, "insert_text", lambda text, *x, **k: a.log.append(("paste", text)) or "pasted")
    monkeypatch.setattr(inserter, "send_enter", lambda: a.log.append("enter") or True)
    monkeypatch.setattr(inserter, "copy_selection", lambda *x, **k: a.seen["selection"])

    def transcribe(wav, pool, model, prompt, available, instruction="", **k):
        a.seen["instruction"] = instruction
        return {"text": a.seen["reply"], "model": "m", "label": "A", "switched": False}

    monkeypatch.setattr(gemini_client, "transcribe", transcribe)
    return a


def test_voice_send_pastes_then_presses_enter(app):
    app._process(JOB, "m", [], False)
    assert app.log == [("paste", "Oke aku jalan."), "enter"]
    assert app.q.get_nowait()[:2] == ("done", "Oke aku jalan.")
    assert app.stats.summary()["words_total"] == 3


def test_voice_send_off_keeps_the_words(app):
    app._process({**JOB, "voice_send": False}, "m", [], False)
    assert app.log == [("paste", "Oke aku jalan. Tekan enter")]


def test_command_mode_replaces_selection(app):
    app.seen["reply"] = "teks singkat"
    app._process({**JOB, "command": True}, "m", [], False)
    assert app.log == [("paste", "teks singkat")] and "<<<\nteks panjang\n>>>" in app.seen["instruction"]


def test_command_mode_without_selection_reports_it(app):
    app.seen["selection"] = ""
    app._process({**JOB, "command": True}, "m", [], False)
    ev = app.q.get_nowait()
    assert ev[0] == "fail" and ev[1].code == "no_selection" and ev[2] is None and app.log == []


def test_app_set_to_off_does_not_record(app, monkeypatch):
    from ucap import app as app_mod
    monkeypatch.setattr(app_mod, "foreground_app", lambda: (0, "game.exe"))
    app.settings["app_styles"]["game.exe"] = "off"
    app.machine.state = "hold"
    app._on_start("hold", "dictate")
    assert not app.recorder.active and app.machine.state == "idle"


def test_defaults_avoid_altgr_and_surprise_enter():
    d = storage.DEFAULT_SETTINGS
    assert not {"ctrl", "alt"} <= set(d["command_hotkey"].split("+")) and d["voice_send"] is False


def test_import_rejects_empty_or_retired_model(tmp_path):
    s = storage.Settings(tmp_path / "s.json")
    assert "model" not in storage.import_settings(s, {"model": " "})
    assert "model" not in storage.import_settings(s, {"model": "gemini-2.5-flash"})
    assert "model" in storage.import_settings(s, {"model": "gemini-3.6-flash"})


def test_meeting_hotkey_message_only_when_it_stopped_a_recording(app, monkeypatch):
    from types import SimpleNamespace
    shown = []
    monkeypatch.setattr(app.pill, "show_message", lambda text, **k: shown.append(text))
    monkeypatch.setattr(app, "meeting_toggle", lambda: None)
    app.meet = SimpleNamespace(state="processing")
    app._on_meeting_hotkey()
    assert shown == []                                      # nothing was stopped
    app.meet = SimpleNamespace(state="recording")
    app._on_meeting_hotkey()
    assert shown == [app.t("meet_stopping")]
