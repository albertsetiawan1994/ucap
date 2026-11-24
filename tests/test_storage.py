import json

import pytest

from ucap.gemini_client import DEFAULT_MODEL
from ucap.storage import History, Settings


@pytest.mark.parametrize("old", ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash",
                                 "gemini-2.5-flash-lite", ""])
def test_retired_model_is_migrated(tmp_path, old):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"model": old, "language": "id"}), encoding="utf-8")
    s = Settings(p)
    assert s["model"] == DEFAULT_MODEL == "gemini-3.5-flash-lite"
    assert s["language"] == "id"


def test_current_model_and_cached_list_kept(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"model": "gemini-3.6-flash", "model_list": ["gemini-3.6-flash"]}), encoding="utf-8")
    s = Settings(p)
    assert s["model"] == "gemini-3.6-flash" and s["model_list"] == ["gemini-3.6-flash"]
    s.save()
    assert json.loads(p.read_text(encoding="utf-8"))["model_list"] == ["gemini-3.6-flash"]


def test_history_records_model(tmp_path):
    h = History(tmp_path / "history.json", limit=2)
    h.add("a", "x.exe", "gemini-3.5-flash-lite")
    h.add("b", "y.exe", "gemini-3.6-flash")
    h.add("c", "z.exe")
    assert [e["text"] for e in h.items] == ["c", "b"]
    assert History(tmp_path / "history.json").items[1]["model"] == "gemini-3.6-flash"
