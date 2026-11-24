"""Meeting notes: stored notes, Gemini prompts, and the context builder for questions about past meetings."""
from __future__ import annotations

import re
import threading
import time
import uuid
from pathlib import Path

from . import storage
from .gemini_client import language_rule

CHUNK_SECONDS = 300          # 5 min of 16 kHz WAV is ~9.6 MB, well under the 20 MB request limit
CHUNK_TIMEOUT_MS = 120_000   # long audio takes longer than a dictation
CHUNK_BUDGET_S = 300.0
QA_BUDGET_CHARS = 250_000    # transcripts beyond this are left out, summaries never are

_WORD = re.compile(r"\w+", re.UNICODE)
_STOP = {"yang", "dan", "di", "ke", "dari", "itu", "ini", "apa", "siapa", "kapan", "bagaimana", "untuk", "dengan",
         "the", "and", "who", "what", "when", "how", "was", "were", "did", "about", "that", "this", "for", "with"}


class MeetingStore:
    def __init__(self, path: Path | None = None):
        self.path = path or storage.data_dir() / "meetings.json"
        self._lock = threading.Lock()
        items = storage._read_json(self.path, [])
        self.items: list[dict] = items if isinstance(items, list) else []

    def add(self, title: str, started: str, secs: int, transcript: str, summary: str, missing: int = 0) -> dict:
        m = {"id": uuid.uuid4().hex[:8], "title": title, "started": started, "secs": int(secs),
             "transcript": transcript, "summary": summary, "missing": missing}
        with self._lock:
            self.items.insert(0, m)
            storage._write_json(self.path, self.items)
        return m

    def update(self, meeting_id: str, **fields) -> None:
        with self._lock:
            for m in self.items:
                if m["id"] == meeting_id:
                    m.update(fields)
            storage._write_json(self.path, self.items)

    def remove(self, meeting_id: str) -> None:
        with self._lock:
            self.items[:] = [m for m in self.items if m["id"] != meeting_id]
            storage._write_json(self.path, self.items)


def parse_title(summary: str) -> str:
    for line in (summary or "").splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:80]
    return "Rapat"


def _lang(language: str) -> str:
    return language_rule(language)


def transcribe_prompt(language: str = "auto", dictionary: list[str] | None = None) -> str:
    lines = ["You transcribe a recording of a meeting. Return ONLY the transcript.",
             "", "Rules:", "1. " + _lang(language),
             "2. Write complete sentences with punctuation. Drop filler words (eh, em, um, uh).",
             "3. Start a new line whenever the speaker seems to change and label speakers 'Speaker 1:', "
             "'Speaker 2:' ... consistently within this recording.",
             "4. Never summarize, answer or comment. If there is no speech, return an empty string."]
    words = [w.strip() for w in (dictionary or []) if w and w.strip()]
    if words:
        lines += ["", "Spell these names/terms exactly like this:"] + [f"- {w}" for w in words]
    return "\n".join(lines)


def summary_prompt() -> str:
    return "\n".join([
        "You write meeting notes (notulen) from a transcript. Write in the main language of the transcript.",
        "Use exactly this markdown layout:",
        "# <short descriptive title>",
        "## Ringkasan  (3-6 sentences)",
        "## Poin penting  (bullets)",
        "## Keputusan  (bullets, or '-' if none)",
        "## Tindak lanjut  (action items as bullets: task - owner - deadline; '-' if none)",
        "Only use facts from the transcript. Never invent names, numbers or deadlines. "
        "Some parts may be marked as missing; mention that in the summary if so.",
    ])


def qa_prompt() -> str:
    return ("You answer questions about the user's past meetings using only the notes provided. "
            "Answer in the language of the question, concisely, and say which meeting (title and date) each fact "
            "comes from. If the answer is not in the notes, say that it is not in the notes. Never guess.")


def _tokens(text: str) -> set[str]:
    return {w for w in (m.group(0).casefold() for m in _WORD.finditer(text or "")) if len(w) >= 3 and w not in _STOP}


def build_context(meetings: list[dict], question: str, budget: int = QA_BUDGET_CHARS) -> str:
    """All summaries, plus full transcripts of the most relevant meetings while they fit in `budget` characters."""
    q = _tokens(question)

    def score(m):
        text = f"{m['title']} {m['summary']} {m['transcript']}".casefold()
        return sum(text.count(t) for t in q)

    head = [f"## [{m['id']}] {m['title']} ({m['started']})\n{m['summary']}" for m in meetings]
    out, used = ["# Meeting summaries", *head], sum(len(h) for h in head)
    extra = []
    for m in sorted(meetings, key=score, reverse=True):
        if score(m) == 0 or not m["transcript"] or used + len(m["transcript"]) > budget:
            continue
        used += len(m["transcript"])
        extra.append(f"## Transcript of [{m['id']}] {m['title']}\n{m['transcript']}")
    return "\n\n".join(out + (["# Full transcripts", *extra] if extra else []))


def search(items: list[dict], query: str) -> list[dict]:
    q = (query or "").strip().casefold()
    return [m for m in items if not q or q in f"{m['title']} {m['summary']} {m['transcript']}".casefold()]


def to_markdown(m: dict) -> str:
    return f"# {m['title']}\n\n{m['started']}\n\n{m['summary']}\n\n---\n\n## Transkrip\n\n{m['transcript']}\n"


def now_stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M")
