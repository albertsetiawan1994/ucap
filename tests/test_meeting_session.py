import time
from types import SimpleNamespace

import numpy as np
import pytest

from ucap import audio, gemini_client, meetings, storage
from ucap.errors import UcapError
from ucap.meeting_session import MeetingSession

SPEECH = (np.random.default_rng(0).standard_normal(audio.SAMPLE_RATE * 2) * 3000).astype(np.int16)


class FakeApp:
    def __init__(self, tmp_path):
        self.settings = {"language": "auto", "dictionary": [], "model": "m", "model_list": []}
        self.meetings = meetings.MeetingStore(tmp_path / "m.json")
        self.pool = object()
        self.events = []

    def post(self, ev):
        self.events.append(ev)


def run(session, chunks=2):
    """Feed `chunks` speech chunks, then end the meeting and wait for the worker."""
    import threading
    for _ in range(chunks):
        session._cut(SPEECH)
    session.state = "processing"
    session._q.put(("end", None))
    t = threading.Thread(target=session._worker)
    t.start()
    t.join(5)
    assert session.state == "done"


@pytest.fixture
def fake_gemini(monkeypatch):
    calls = {"n": 0, "fail": set()}

    def transcribe(*a, **k):
        calls["n"] += 1
        if calls["n"] in calls["fail"]:
            raise UcapError("busy")
        return {"text": f"Speaker 1: bagian {calls['n']}"}

    monkeypatch.setattr(gemini_client, "transcribe", transcribe)
    monkeypatch.setattr(gemini_client, "generate", lambda *a, **k: {"text": "# Rapat Uji\n## Ringkasan\nok"})
    return calls


def test_partial_failure_is_saved_and_retry_fills_the_gap(tmp_path, fake_gemini):
    app = FakeApp(tmp_path)
    s = MeetingSession(app)
    fake_gemini["fail"] = {2}
    run(s)
    m = app.meetings.items[0]
    assert m["title"] == "Rapat Uji" and m["missing"] == 1 and "[bagian 2 tidak dapat" in m["transcript"]
    assert s.needs_retry
    fake_gemini["fail"] = set()
    s.state = "processing"
    s._q.put(("retry", None))
    import threading
    t = threading.Thread(target=s._worker)
    t.start()
    t.join(5)
    assert not s.needs_retry and len(app.meetings.items) == 1
    assert app.meetings.items[0]["missing"] == 0 and "[bagian" not in app.meetings.items[0]["transcript"]


def test_every_part_failing_keeps_the_meeting_for_retry(tmp_path, fake_gemini):
    app = FakeApp(tmp_path)
    s = MeetingSession(app)
    fake_gemini["fail"] = {1, 2}
    run(s)
    assert len(app.meetings.items) == 1 and app.meetings.items[0]["missing"] == 2
    assert s.needs_retry and app.events[-1][0] == "meeting_done" and app.events[-1][1] is not None


def test_no_speech_saves_nothing(tmp_path, fake_gemini):
    app = FakeApp(tmp_path)
    s = MeetingSession(app)
    run(s, chunks=0)
    assert app.meetings.items == [] and app.events[-1] == ("meeting_done", None, None)


def test_silent_part_is_not_marked_as_failed(tmp_path, monkeypatch, fake_gemini):
    texts = iter(["Speaker 1: halo", ""])
    monkeypatch.setattr(gemini_client, "transcribe", lambda *a, **k: {"text": next(texts)})
    app = FakeApp(tmp_path)
    s = MeetingSession(app)
    run(s)
    assert app.meetings.items[0]["transcript"] == "Speaker 1: halo" and not s.needs_retry


def test_known_speakers_and_screenshots_reach_the_next_chunk(tmp_path, monkeypatch):
    seen = []

    def transcribe(wav, pool, model, prompt, available, instruction="", images=(), **k):
        seen.append((prompt, instruction, list(images)))
        return {"text": "Pak Budi: Selamat pagi semua." if len(seen) == 1 else "Sari: Siap."}

    monkeypatch.setattr(gemini_client, "transcribe", transcribe)
    monkeypatch.setattr(gemini_client, "generate", lambda *a, **k: {"text": "# R"})
    app = FakeApp(tmp_path)
    s = MeetingSession(app)
    s.shots = [(15, b"jpg1")]
    s._cut(SPEECH)
    s._cut(SPEECH)
    run(s, chunks=0)
    assert seen[0][2] == [b"jpg1"] and "15s" in seen[0][1] and seen[1][2] == []
    assert "Pak Budi" in seen[1][0] and "identified earlier" not in seen[0][0]
    assert s.speakers == ["Pak Budi", "Sari"]
