"""Spoken commands handled locally after transcription."""
from __future__ import annotations

import re

# Multi-word on purpose: a single word like "kirim" appears in normal sentences.
SEND_PHRASES = ("tekan enter", "press enter", "kirim pesan ini sekarang", "send message now")
_WORD = re.compile(r"\w+", re.UNICODE)


def split_send(text: str) -> tuple[str, bool]:
    """('text without the trailing send phrase', True) when the dictation ends with one, else (text, False)."""
    words = list(_WORD.finditer(text or ""))
    folded = [w.group(0).casefold() for w in words]
    for phrase in SEND_PHRASES:
        toks = phrase.split()
        n = len(toks)
        if len(folded) >= n and folded[-n:] == toks:
            return text[:words[-n].start()].rstrip(" \t\n,;:-"), True
    return text, False
