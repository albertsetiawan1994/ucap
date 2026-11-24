"""One meeting recording: cut into chunks while recording, transcribe them in the background, then summarize."""
from __future__ import annotations

import queue
import threading
import time

from . import audio, gemini_client, meetings
from .errors import UcapError

CHUNK_INSTRUCTION = "Transcribe this meeting recording. Output only the transcript."
MIN_CHUNK_SECONDS = 1.0


class MeetingSession:
    """state: recording -> processing -> done. A done session with `failed` chunks can be retried."""

    def __init__(self, app):
        self.app = app
        self.rec = audio.Recorder()
        self.loop: audio.LoopbackRecorder | None = None
        self.state = "idle"
        self.started = meetings.now_stamp()
        self.t0 = 0.0
        self.last_cut = 0.0
        self.total = self.done = 0
        self.parts: dict[int, str] = {}
        self.failed: dict[int, bytes] = {}
        self.record_id: str | None = None
        self.secs = 0
        self.no_summary = False
        self._q: queue.Queue = queue.Queue()
        s = app.settings
        self._language, self._dictionary = s["language"], list(s["dictionary"])

    # ---- GUI thread ----
    def start(self, device) -> None:
        self.rec.start(device)  # may raise UcapError
        if self.app.settings["meeting_system_audio"]:
            try:  # online meeting participants come out of the speakers; without this only the mic is heard
                loop = audio.LoopbackRecorder()
                loop.start()
                self.loop = loop
            except Exception:  # noqa: BLE001 - library or output device missing: microphone only
                self.loop = None
        self.state, self.t0 = "recording", time.monotonic()
        self.last_cut = self.t0
        threading.Thread(target=self._worker, daemon=True).start()

    def elapsed(self) -> int:
        return int(time.monotonic() - self.t0)

    def tick(self) -> None:
        if self.state == "recording" and time.monotonic() - self.last_cut >= meetings.CHUNK_SECONDS:
            self._cut(self._mix(self.rec.drain()))

    def _mix(self, mic):
        return audio.mix(mic, self.loop.drain()) if self.loop else mic

    def abort(self) -> None:
        self.rec.stop()
        if self.loop:
            self.loop.stop()

    def stop(self) -> None:
        if self.state != "recording":
            return
        self.secs = self.elapsed()
        self._cut(self._mix(self.rec.stop()))
        if self.loop:
            self.loop.stop()
        self.state = "processing"
        self._q.put(("end", None))

    def retry(self) -> None:
        if self.state == "done" and self.needs_retry:
            self.state = "processing"
            self._q.put(("retry", None))
            threading.Thread(target=self._worker, daemon=True).start()

    @property
    def needs_retry(self) -> bool:
        return bool(self.failed) or self.no_summary

    def _cut(self, samples) -> None:
        self.last_cut = time.monotonic()
        if samples.size >= audio.SAMPLE_RATE * MIN_CHUNK_SECONDS and audio.is_usable(samples):
            idx, self.total = self.total, self.total + 1
            self._q.put(("chunk", (idx, audio.to_wav(samples))))

    # ---- worker thread ----
    def _args(self):
        s = self.app.settings
        return s["model"], list(s["model_list"])

    def _transcribe(self, idx: int, wav: bytes) -> None:
        model, available = self._args()
        try:
            r = gemini_client.transcribe(
                wav, self.app.pool, model, meetings.transcribe_prompt(self._language, self._dictionary), available,
                instruction=CHUNK_INSTRUCTION, timeout_ms=meetings.CHUNK_TIMEOUT_MS, budget_s=meetings.CHUNK_BUDGET_S)
            self.parts[idx] = r["text"]
            self.failed.pop(idx, None)
        except Exception:  # noqa: BLE001 - kept in memory for a retry
            self.failed[idx] = wav
        self.done += 1
        self.app.post(("meeting_progress",))

    def _worker(self) -> None:
        while True:
            kind, payload = self._q.get()
            if kind == "chunk":
                self._transcribe(*payload)
            elif kind == "retry":
                for idx, wav in sorted(self.failed.items()):
                    self.done -= 1
                    self._transcribe(idx, wav)
                self._finalize()
                return
            else:  # end
                self._finalize()
                return

    def transcript(self) -> str:
        """Failed parts get a marker; parts Gemini heard no speech in (empty text) are left out."""
        lines = []
        for i in range(self.total):
            if i in self.failed:
                lines.append(f"[bagian {i + 1} tidak dapat ditranskripsi]")
            elif self.parts.get(i):
                lines.append(self.parts[i])
        return "\n\n".join(lines)

    def _finalize(self) -> None:
        text = self.transcript()
        has_speech = any(self.parts.values())
        if not has_speech and not self.failed:
            self.state = "done"
            self.app.post(("meeting_done", None, None))
            return
        summary = ""
        if has_speech:  # all parts failed: keep the meeting for a retry instead of summarizing markers
            model, available = self._args()
            try:
                r = gemini_client.generate(self.app.pool, model, meetings.summary_prompt(), [text], available,
                                           timeout_ms=meetings.CHUNK_TIMEOUT_MS, budget_s=meetings.CHUNK_BUDGET_S)
                summary = r["text"]
            except UcapError:
                pass
        self.no_summary = not summary
        title = meetings.parse_title(summary) if summary else f"Rapat {self.started}"
        fields = {"title": title, "transcript": text, "summary": summary or "(ringkasan gagal dibuat)",
                  "missing": len(self.failed)}
        if self.record_id:
            self.app.meetings.update(self.record_id, **fields)
            m = next(m for m in self.app.meetings.items if m["id"] == self.record_id)
        else:
            m = self.app.meetings.add(title, self.started, self.secs, text, fields["summary"], len(self.failed))
            self.record_id = m["id"]
        self.state = "done"
        self.app.post(("meeting_done", m, None))
