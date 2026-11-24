"""User-facing error with a code that the UI translates (see i18n 'err_*' keys)."""


class UcapError(Exception):
    # codes: no_key, invalid_key, quota, offline, mic_busy, no_mic, model, empty, paste_failed, unknown
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
