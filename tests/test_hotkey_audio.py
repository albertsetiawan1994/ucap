import numpy as np

from ucap.audio import SAMPLE_RATE, is_usable, to_wav
from ucap.hotkey import HotkeyMachine, format_combo, parse_combo


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make():
    clock, log = Clock(), []
    m = HotkeyMachine("ctrl+windows", lambda mode: log.append(("start", mode)), lambda: log.append("stop"),
                      lambda r: log.append(("cancel", r)), clock=clock)
    return m, clock, log


def press(m, clock, at, *keys):
    clock.t = at
    for k in keys:
        m.key_down(k)


def release(m, clock, at, *keys):
    clock.t = at
    for k in keys:
        m.key_up(k)


def test_parse_and_format():
    assert parse_combo("Left Ctrl + Left Windows") == {"ctrl", "windows"}
    assert format_combo("windows+ctrl") == "Ctrl+Win"
    assert parse_combo("") == {"ctrl", "windows"}


def test_hold_to_talk():
    m, c, log = make()
    press(m, c, 0, "ctrl", "left windows")
    release(m, c, 1.5, "left windows", "ctrl")
    assert log == [("start", "hold"), "stop"]


def test_double_tap_handsfree_then_tap_to_stop():
    m, c, log = make()
    press(m, c, 0.0, "ctrl", "windows")
    release(m, c, 0.1, "windows")
    press(m, c, 0.25, "windows")      # ctrl still held: second tap
    release(m, c, 0.3, "windows", "ctrl")
    assert log == [("start", "hold"), ("cancel", "tap"), ("start", "handsfree")]
    press(m, c, 5.0, "ctrl", "windows")
    release(m, c, 5.1, "ctrl", "windows")
    assert log[-1] == "stop" and m.state == "idle"


def test_esc_cancels_and_other_key_cancels_hold():
    m, c, log = make()
    press(m, c, 0, "ctrl", "windows", "esc")
    assert log[-1] == ("cancel", "esc")
    m2, c2, log2 = make()
    press(m2, c2, 0, "ctrl", "windows", "d")   # Ctrl+Win+D = Windows shortcut
    assert log2[-1] == ("cancel", "other_key")


def test_short_or_silent_audio_is_ignored():
    rng = np.random.default_rng(0)
    speech = (rng.standard_normal(SAMPLE_RATE) * 3000).astype(np.int16)
    assert is_usable(speech)
    assert not is_usable(speech[: int(SAMPLE_RATE * 0.2)])           # < 0.3 s
    assert not is_usable(np.zeros(SAMPLE_RATE * 2, dtype=np.int16))  # silent
    wav = to_wav(speech)
    assert wav[:4] == b"RIFF" and len(wav) == 44 + SAMPLE_RATE * 2
