from ucap.styles import DEFAULT_APP_STYLES, style_for_app


def test_default_categories():
    m = DEFAULT_APP_STYLES
    assert style_for_app("WhatsApp.exe", m) == "casual"
    assert style_for_app("Telegram.exe", m) == "casual"
    assert style_for_app("slack.exe", m) == "casual"
    assert style_for_app("ms-teams.exe", m) == "casual"
    assert style_for_app("OUTLOOK.EXE", m) == "formal"
    assert style_for_app("WINWORD.EXE", m) == "formal"
    assert "chrome.exe" in m


def test_case_insensitive_and_unknown_default():
    m = {"Slack.exe": "very_casual"}
    assert style_for_app("SLACK.EXE", m) == "very_casual"
    assert style_for_app("notepad.exe", m, "formal") == "formal"
    assert style_for_app("", m, "very_casual") == "very_casual"
    assert style_for_app(None, m) == "casual"


def test_invalid_values_fall_back():
    assert style_for_app("x.exe", {"x.exe": "shouty"}, "formal") == "formal"
    assert style_for_app("y.exe", {}, "nonsense") == "casual"
