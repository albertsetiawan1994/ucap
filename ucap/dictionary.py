"""Suggest personal-dictionary terms from past dictations."""
from __future__ import annotations

import re
from collections import Counter

# Capitalised word, or a word with an inner capital / digit (iPhone, Kubernetes, GPT4).
_TERM = re.compile(r"\b(?:[A-Z][\w'-]{2,}|[a-z]+[A-Z]\w*)\b")
_SENTENCE_END = ".!?\n:"


def suggest_terms(texts: list[str], dictionary: list[str], min_count: int = 2, limit: int = 15) -> list[str]:
    """Terms said at least `min_count` times mid-sentence (a capital at a sentence start proves nothing)."""
    known = {w.casefold() for w in dictionary}
    counts: Counter = Counter()
    for text in texts:
        for m in _TERM.finditer(text):
            before = text[:m.start()].rstrip(" \t\"'(")
            if m.group(0)[0].isupper() and (not before or before[-1] in _SENTENCE_END):
                continue
            counts[m.group(0)] += 1
    return [w for w, n in counts.most_common() if n >= min_count and w.casefold() not in known][:limit]
