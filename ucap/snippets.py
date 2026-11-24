"""Post-processing: clean the model output and expand snippets locally."""
from __future__ import annotations

import re

_WORD = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [m.group(0).casefold() for m in _WORD.finditer(text)]


def clean_output(text: str) -> str:
    """Strip code fences / wrapping quotes / labels a model sometimes adds."""
    t = (text or "").strip()
    t = re.sub(r"^```[a-zA-Z]*\s*\n?|\n?```$", "", t).strip()
    t = re.sub(r"^(transcript|transkrip|text|teks)\s*:\s*", "", t, flags=re.IGNORECASE)
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'“”" and t.count(t[0]) == 2:
        t = t[1:-1].strip()
    return t


def expand_snippets(text: str, snippets: list[dict]) -> str:
    """Replace trigger phrases with their expansion.

    Matching ignores case and punctuation. If the whole utterance is a trigger, the result is
    exactly the expansion (no trailing period added by the model). Otherwise each trigger found as
    a run of whole words is replaced in place, longest triggers first.
    """
    rules = []
    for s in snippets or []:
        toks = _tokens(s.get("trigger", ""))
        if toks and s.get("expansion"):
            rules.append((toks, s["expansion"]))
    if not rules or not text:
        return text
    rules.sort(key=lambda r: len(r[0]), reverse=True)

    words = list(_WORD.finditer(text))
    folded = [w.group(0).casefold() for w in words]
    for toks, expansion in rules:
        if folded == toks:
            return expansion

    out, pos, i = [], 0, 0
    while i < len(words):
        for toks, expansion in rules:
            n = len(toks)
            if folded[i:i + n] == toks:
                out.append(text[pos:words[i].start()])
                out.append(expansion)
                pos = words[i + n - 1].end()
                i += n
                break
        else:
            i += 1
    out.append(text[pos:])
    return "".join(out)
