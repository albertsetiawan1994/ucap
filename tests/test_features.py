from datetime import date
from types import SimpleNamespace

from ucap import gemini_client as gc
from ucap import meetings, storage
from ucap.commands import split_send
from ucap.hotkey import HotkeyListener, HotkeyMachine
from ucap.styles import style_for_app


# ---- voice "send" command ----
def test_split_send_strips_trailing_phrase():
    assert split_send("Oke, aku otw ya. Tekan enter") == ("Oke, aku otw ya.", True)
    assert split_send("see you at 5, press enter.") == ("see you at 5", True)
    assert split_send("Tolong kirim pesan ini ke Budi") == ("Tolong kirim pesan ini ke Budi", False)
    assert split_send("press Enter") == ("", True)
    assert split_send("") == ("", False)


def test_style_off_is_accepted_per_app_only():
    assert style_for_app("game.exe", {"game.exe": "off"}, "casual") == "off"
    assert style_for_app("x.exe", {}, "off") == "casual"  # 'off' is never a default style


# ---- stats ----
def test_stats_summary_and_streak(tmp_path):
    st = storage.Stats(tmp_path / "stats.json")
    st.add(60, 30, "2026-11-22")
    st.add(120, 60, "2026-11-23")
    st.add(30, 15, "2026-11-24")
    st.add(10, 5, "2026-11-10")
    s = st.summary(date(2026, 11, 24))
    assert s["words_total"] == 220 and s["count_total"] == 4
    assert s["words_today"] == 30 and s["words_week"] == 210
    assert s["streak"] == 3 and round(s["wpm"]) == 120
    assert storage.Stats(tmp_path / "stats.json").summary(date(2026, 11, 24))["words_total"] == 220  # persisted
    assert st.summary(date(2026, 11, 26))["streak"] == 0  # gap of 2 days breaks it
    assert storage.Stats(tmp_path / "none.json").summary(date(2026, 11, 24))["wpm"] == 0


# ---- export / import ----
def test_export_excludes_secrets_and_import_validates(tmp_path):
    s = storage.Settings(tmp_path / "s.json")
    s["keys"].append({"id": "1", "label": "A", "enabled": True, "invalid": False})
    s["dictionary"] = ["Kubernetes"]
    data = storage.export_settings(s)
    assert "keys" not in data and "model_list" not in data and data["dictionary"] == ["Kubernetes"]
    t = storage.Settings(tmp_path / "t.json")
    applied = storage.import_settings(t, {**data, "keys": [{"id": "9"}], "language": 5, "snippets": ["bad"],
                                          "bogus": 1})
    assert t["dictionary"] == ["Kubernetes"] and t["keys"] == [] and t["language"] == "auto"
    assert t["snippets"] == [] and "dictionary" in applied and "bogus" not in applied


# ---- command mode prompt / generate ----
def test_command_prompt_and_instruction():
    p = gc.build_command_prompt("casual", ["Kubernetes"])
    assert "spoken instruction" in p and "ONLY the resulting text" in p and "- Kubernetes" in p
    assert "never translate" not in p.lower()  # translating is a normal voice command
    assert "<<<\nhalo\n>>>" in gc.command_instruction("halo")


class _Pool:
    def __init__(self):
        self.k = [{"id": "1", "label": "A"}]

    def usable(self): return self.k
    def blocked_until(self, *_): return 0
    def count(self, *_): pass
    def secret_of(self, _): return "s"


def test_generate_passes_text_contents_and_custom_timeout():
    seen = {}

    def factory(_):
        def gen(**kw):
            seen.update(kw)
            return SimpleNamespace(text=" hi ")
        return SimpleNamespace(models=SimpleNamespace(generate_content=gen))

    r = gc.generate(_Pool(), "m", "SYS", ["q"], client_factory=factory, timeout_ms=120_000, budget_s=300)
    assert r["text"] == "hi" and seen["contents"] == ["q"]
    assert seen["config"].http_options.timeout == 120_000


# ---- meetings ----
def test_meeting_store_roundtrip(tmp_path):
    ms = meetings.MeetingStore(tmp_path / "m.json")
    m = ms.add("Sprint", "2026-11-24 10:00", 600, "teks", "# Sprint\nisi")
    assert meetings.MeetingStore(tmp_path / "m.json").items[0]["id"] == m["id"]
    ms.remove(m["id"])
    assert ms.items == []


def test_parse_title():
    assert meetings.parse_title("# Rapat Q4\n\n- a") == "Rapat Q4"
    assert meetings.parse_title("") == "Rapat"


def test_context_prefers_relevant_transcripts_within_budget():
    ms = [{"id": "a", "title": "Anggaran", "started": "2026-11-01", "summary": "bahas biaya", "transcript": "x" * 50},
          {"id": "b", "title": "Desain", "started": "2026-11-02", "summary": "bahas logo",
           "transcript": "Pak Budi setuju logo biru " + "y" * 50}]
    ctx = meetings.build_context(ms, "siapa yang setuju logo biru?", budget=170)
    assert "bahas biaya" in ctx and "bahas logo" in ctx          # summaries always included
    assert "Pak Budi setuju" in ctx and "x" * 50 not in ctx      # budget keeps only the relevant transcript


def test_prompts_mention_language_and_dictionary():
    assert "Budi" in meetings.transcribe_prompt("id", ["Budi"])
    assert "action items" in meetings.summary_prompt().lower()
    assert "not in the notes" in meetings.qa_prompt().lower()


# ---- hotkey listener with several machines ----
def test_listener_feeds_every_machine():
    log = []
    m1 = HotkeyMachine("ctrl+windows", lambda m: log.append(("d", m)), lambda: None, lambda r: None)
    m2 = HotkeyMachine("ctrl+alt", lambda m: log.append(("c", m)), lambda: None, lambda r: None)
    ln = HotkeyListener([m1, m2])
    for name in ("ctrl", "alt"):
        ln._on_event(SimpleNamespace(scan_code=1, name=name, event_type="down"))
    assert log == [("c", "hold")]


# ---- selection capture ----
class _Clip:
    def __init__(self, text):
        self.text = text

    def snapshot(self): return self.text
    def set_text(self, t): self.text = t
    def get_text(self): return self.text
    def restore(self, snap): self.text = snap


def test_copy_selection_returns_selected_text_and_restores_clipboard():
    from ucap import inserter
    clip = _Clip("old")
    sel = inserter.copy_selection(clip, lambda: clip.set_text("dipilih") or True, sleep=lambda _: None)
    assert sel == "dipilih" and clip.text == "old"
    clip = _Clip("old")
    assert inserter.copy_selection(clip, lambda: True, sleep=lambda _: None) == "" and clip.text == "old"


# ---- hotkey conflicts ----
def test_combos_conflict_same_or_subset():
    from ucap.hotkey import combos_conflict
    assert combos_conflict("ctrl+alt", "alt+ctrl")
    assert combos_conflict("ctrl+windows", "ctrl+windows+shift")  # one fires inside the other
    assert not combos_conflict("ctrl+windows", "alt+windows")
    assert not combos_conflict("alt+windows", "alt+shift+z")


# ---- meeting list helpers ----
def test_search_and_markdown():
    ms = [{"id": "a", "title": "Anggaran", "summary": "biaya", "transcript": "x", "started": "d", "secs": 60},
          {"id": "b", "title": "Desain", "summary": "logo", "transcript": "Pak Budi setuju", "started": "d", "secs": 60}]
    assert [m["id"] for m in meetings.search(ms, "budi")] == ["b"]
    assert [m["id"] for m in meetings.search(ms, "  ")] == ["a", "b"]
    md = meetings.to_markdown(ms[1])
    assert md.startswith("# Desain") and "logo" in md and "Pak Budi setuju" in md


# ---- audio folder ----
def test_prune_audio_keeps_newest(tmp_path):
    import os
    for i in range(5):
        f = tmp_path / f"{i}.wav"
        f.write_bytes(b"x")
        os.utime(f, (i, i))
    storage.prune_audio(tmp_path, limit=2)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["3.wav", "4.wav"]


# ---- system audio ----
def test_resample_and_mix():
    import numpy as np
    from ucap import audio
    stereo = np.tile(np.array([[1000, 3000]], dtype=np.int16), (48000, 1))      # 1 s, 48 kHz
    out = audio.resample_mono16k(stereo, 48000)
    assert out.dtype == np.int16 and abs(out.size - 16000) <= 1 and set(out.tolist()) == {2000}
    a, b = np.full(10, 30000, np.int16), np.full(4, 30000, np.int16)
    m = audio.mix(a, b)
    assert m.size == 10 and m[0] == 32767 and m[9] == 30000                    # clipped, shorter one padded
    assert audio.mix(a, np.zeros(0, np.int16)).tolist() == a.tolist()


def test_last_days_fills_gaps(tmp_path):
    st = storage.Stats(tmp_path / "s.json")
    st.add(40, 10, "2026-11-22")
    st.add(5, 2, "2026-11-24")
    days = st.last_days(4, date(2026, 11, 24))
    assert [(d.isoformat(), w) for d, w in days] == [("2026-11-21", 0), ("2026-11-22", 40), ("2026-11-23", 0),
                                                      ("2026-11-24", 5)]


# ---- dictionary suggestions / languages ----
def test_suggest_terms_ignores_sentence_starts_and_known():
    from ucap.dictionary import suggest_terms
    texts = ["Besok kita bahas Kubernetes dengan Budi.", "Kirim ke Budi soal Kubernetes. Halo semuanya.",
             "Halo, Budi sudah tahu. Halo lagi", "pakai iPhone dan iPhone lain"]
    assert suggest_terms(texts, ["budi"]) == ["Kubernetes", "iPhone"]  # Halo only starts sentences; Budi known


def test_language_rule_covers_more_languages():
    assert "uses Japanese" in gc.build_system_prompt("ja", "casual")
    assert "uses Indonesian" in gc.build_system_prompt("id", "casual")
    assert "mix of both" in gc.build_system_prompt("zz", "casual")


# ---- window context / code editors ----
def test_prompt_window_title_and_code_mode():
    from ucap.styles import is_code_editor
    p = gc.build_system_prompt("auto", "casual", window_title='Budi "Ketua" - WhatsApp\n' + "x" * 300)
    assert "Budi 'Ketua' - WhatsApp" in p and "never copy it" in p and "x" * 121 not in p
    assert "code editor" not in p and "Context" not in gc.build_system_prompt("auto", "casual")
    assert "user_id" in gc.build_system_prompt("auto", "casual", code=True)
    assert is_code_editor("Code.exe") and not is_code_editor("WhatsApp.exe") and not is_code_editor("")


# ---- update check ----
def test_update_check():
    from ucap import updater
    rel = {"tag_name": "v1.2.0", "html_url": "https://github.com/me/ucap/releases/tag/v1.2.0"}
    assert updater.check("1.1.0", "me/ucap", lambda url: rel) == {"version": "1.2.0", "url": rel["html_url"]}
    assert updater.check("1.2.0", "me/ucap", lambda url: rel) is None              # same version
    assert updater.check("1.1.0", "", lambda url: rel) is None                     # no repo configured
    assert updater.check("1.1.0", "me/ucap", lambda url: {**rel, "html_url": "https://evil.example/x"}) is None

    def boom(url):
        raise OSError("offline")
    assert updater.check("1.1.0", "me/ucap", boom) is None
    assert updater.parse_version("v2") == (2, 0, 0) and updater.parse_version("beta") == ()
