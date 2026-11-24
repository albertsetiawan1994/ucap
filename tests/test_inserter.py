from ucap.inserter import insert_text


class FakeClipboard:
    def __init__(self, content):
        self.content = content
        self.log = []

    def snapshot(self):
        self.log.append("snapshot")
        return {"text": self.content}

    def set_text(self, text):
        self.log.append("set")
        self.content = text

    def get_text(self):
        return self.content

    def restore(self, snap):
        self.log.append("restore")
        self.content = snap["text"]


def test_backup_paste_restore():
    cb = FakeClipboard("ORIGINAL")
    pasted, slept = [], []
    result = insert_text("dictated", cb, lambda: pasted.append(cb.content) or True, sleep=slept.append)
    assert result == "pasted"
    assert pasted == ["dictated"]          # the paste saw our text
    assert cb.content == "ORIGINAL"        # original is back afterwards
    assert slept and slept[0] > 0          # restore waits a moment
    assert cb.log == ["snapshot", "set", "restore"]


def test_no_restore_if_user_copied_something_new():
    cb = FakeClipboard("ORIGINAL")

    def sleep(_):
        cb.content = "user copied this"

    insert_text("dictated", cb, lambda: True, sleep=sleep)
    assert cb.content == "user copied this"


def test_fallback_keeps_text_on_clipboard_when_paste_fails():
    cb = FakeClipboard("ORIGINAL")
    assert insert_text("dictated", cb, lambda: False, sleep=lambda _: None) == "clipboard"
    assert cb.content == "dictated"

    def boom():
        raise OSError("SendInput blocked")

    cb2 = FakeClipboard("ORIGINAL")
    assert insert_text("dictated", cb2, boom, sleep=lambda _: None) == "clipboard"
    assert cb2.content == "dictated"


def test_fallback_when_target_cannot_receive_paste():
    cb = FakeClipboard("ORIGINAL")
    called = []
    assert insert_text("dictated", cb, lambda: called.append(1) or True, can_paste=False) == "clipboard"
    assert not called and cb.content == "dictated"
