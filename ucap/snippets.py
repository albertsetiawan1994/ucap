"""Post-processing: clean the model output and expand snippets locally."""
from __future__ import annotations

import re

_WORD = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [m.group(0).casefold() for m in _WORD.finditer(text)]


# Han, kana and Thai are written without spaces between words: count each character instead.
_NO_SPACE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u0e00-\u0e7f]")
# Romanization Ucap adds after non-Latin text, e.g. "开会。(kāihuì.)" or "всем. (vsem.)": the same words
# again, so not counted. One plain punctuation mark may sit between the text and the bracket.
_ROMANIZED = re.compile(r"([^\x00-\u024f\u1e00-\u1eff\s][.!?,;:]?)\s*\([^()]*\)")


def count_words(text: str) -> int:
    """Words for the statistics; Chinese/Japanese/Thai count per character (shortcut: Thai is over-counted)."""
    text = _ROMANIZED.sub(r"\1 ", text or "")
    return len(_NO_SPACE.findall(text)) + len(_WORD.findall(_NO_SPACE.sub(" ", text)))


def clean_output(text: str) -> str:
    """Strip code fences / wrapping quotes / labels a model sometimes adds."""
    t = (text or "").strip()
    t = re.sub(r"^```[a-zA-Z]*\s*\n?|\n?```$", "", t).strip()
    if "<heard>" in t or "<text>" in t:  # dictation answer: <heard>exact words</heard><text>final</text>
        m = re.search(r"<text>(.*?)(?:</text>|\Z)", t, re.S)
        if m:
            t = m.group(1)
        else:  # no <text>: whatever follows <heard>, else the exact words are better than nothing
            heard, _, rest = t.partition("</heard>")
            t = rest if rest.strip() else heard.replace("<heard>", "")
        t = t.strip()
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
