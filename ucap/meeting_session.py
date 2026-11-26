"""One meeting recording: cut into chunks while recording, transcribe them in the background, then summarize."""
from __future__ import annotations

import queue
import threading
import time

from . import audio, gemini_client, meetings, screen
from .errors import UcapError

MIN_CHUNK_SECONDS = 1.0
SHOT_INTERVAL_S = 15  # one screenshot of the meeting window this often (names on video tiles, active speaker)
# 5 min of WAV is ~9.6 MB; with this many image bytes the base64 request stays well under Gemini's 20 MB limit.
SHOT_BUDGET_BYTES = 2_000_000


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
        self.failed: dict[int, tuple] = {}  # idx -> (wav, shots), kept in memory for a retry
        self.shots: list[tuple[int, bytes]] = []  # (seconds into the current chunk, jpeg)
        self.speakers: list[str] = []  # names found so far, passed to the next chunk
        self.last_shot = 0.0
        self.record_id: str | None = None
        self.secs = 0
        self.no_summary = False
        self._q: queue.Queue = queue.Queue()
        s = app.settings
        self._language, self._dictionary = s["language"], list(s["dictionary"])
        self._romanize = bool(s["romanize"])

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
        self.last_cut = self.last_shot = self.t0
        threading.Thread(target=self._worker, daemon=True).start()

    def elapsed(self) -> int:
        return int(time.monotonic() - self.t0)

    def tick(self) -> None:
        if self.state != "recording":
            return
        now = time.monotonic()
        if self.app.settings["meeting_screen_speakers"] and now - self.last_shot >= SHOT_INTERVAL_S:
            self.last_shot = now
            jpg = screen.capture(screen.pick_meeting_window(screen.list_windows()))
            if jpg:
                self.add_shot(int(now - self.last_cut), jpg)
        if now - self.last_cut >= meetings.CHUNK_SECONDS:
            self._cut(self._mix(self.rec.drain()))

    def add_shot(self, secs: int, jpg: bytes) -> None:
        """Keep a screenshot for the current chunk unless the chunk's image budget is used up."""
        if sum(len(j) for _, j in self.shots) + len(jpg) <= SHOT_BUDGET_BYTES:
            self.shots.append((secs, jpg))

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
        shots, self.shots = self.shots, []
        if samples.size >= audio.SAMPLE_RATE * MIN_CHUNK_SECONDS and audio.is_usable(samples):
            idx, self.total = self.total, self.total + 1
            self._q.put(("chunk", (idx, audio.to_wav(audio.normalize(samples)), shots)))

    # ---- worker thread ----
    def _args(self):
        s = self.app.settings
        return s["model"], list(s["model_list"])

    def _transcribe(self, idx: int, wav: bytes, shots: list) -> None:
        model, available = self._args()
        prompt = meetings.transcribe_prompt(self._language, self._dictionary, self.speakers, bool(shots),
                                            self._romanize)
        try:
            r = gemini_client.transcribe(
                wav, self.app.pool, model, prompt, available,
                instruction=meetings.chunk_instruction([t for t, _ in shots]), images=[j for _, j in shots],
                timeout_ms=meetings.CHUNK_TIMEOUT_MS, budget_s=meetings.CHUNK_BUDGET_S)
            self.parts[idx] = r["text"]
            self.failed.pop(idx, None)
            for name in meetings.extract_speakers(r["text"]):
                if name not in self.speakers:
                    self.speakers.append(name)
        except Exception:  # noqa: BLE001 - kept in memory for a retry
            self.failed[idx] = (wav, shots)
        self.done += 1
        self.app.post(("meeting_progress",))

    def _worker(self) -> None:
        while True:
            kind, payload = self._q.get()
            if kind == "chunk":
                self._transcribe(*payload)
            elif kind == "retry":
                for idx, (wav, _shots) in sorted(self.failed.items()):
                    self.done -= 1
                    self._transcribe(idx, wav, [])  # audio only: the images may be why it failed
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
                r = gemini_client.generate(self.app.pool, model, meetings.summary_prompt(self._romanize, self._language), [text], available,
                                           timeout_ms=meetings.CHUNK_TIMEOUT_MS, budget_s=meetings.CHUNK_BUDGET_S)
                summary = meetings.clean_summary(r["text"])
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
