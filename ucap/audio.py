"""Microphone capture at 16 kHz mono int16."""
from __future__ import annotations

import io
import threading
import wave

import numpy as np

from .errors import UcapError

SAMPLE_RATE = 16000
MIN_SECONDS = 0.3
SILENCE_RMS = 120  # int16 RMS; quieter than this over the whole clip counts as silence


def to_wav(samples: np.ndarray, rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.astype(np.int16).tobytes())
    return buf.getvalue()


def rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))


def is_usable(samples: np.ndarray, rate: int = SAMPLE_RATE) -> bool:
    """False for clips shorter than MIN_SECONDS or silent ones."""
    if samples.size < MIN_SECONDS * rate:
        return False
    # loudest 100 ms window, so a short phrase in a long pause still counts
    win = rate // 10
    n = samples.size // win
    if n == 0:
        return rms(samples) >= SILENCE_RMS
    blocks = samples[: n * win].astype(np.float64).reshape(n, win)
    return float(np.sqrt((blocks ** 2).mean(axis=1)).max()) >= SILENCE_RMS


def resample_mono16k(data: np.ndarray, rate: int) -> np.ndarray:
    """Interleaved int16 frames (n, channels) at `rate` -> mono int16 at 16 kHz."""
    mono = data.astype(np.float32).mean(axis=1) if data.ndim == 2 else data.astype(np.float32)
    if mono.size == 0:
        return np.zeros(0, dtype=np.int16)
    n = max(1, round(mono.size * SAMPLE_RATE / rate))
    out = np.interp(np.linspace(0, mono.size - 1, n), np.arange(mono.size), mono)
    return np.clip(out, -32768, 32767).astype(np.int16)


def mix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Sum two mono int16 tracks (the shorter one is padded with silence), clipped."""
    n = max(a.size, b.size)
    out = np.zeros(n, dtype=np.int32)
    out[:a.size] += a
    out[:b.size] += b
    return np.clip(out, -32768, 32767).astype(np.int16)


class LoopbackRecorder:
    """What the speakers play (WASAPI loopback, via PyAudioWPatch). Silent stretches are padded with zeros
    because loopback delivers no frames while nothing plays, which would otherwise shift later audio earlier."""

    def __init__(self):
        self._pa = self._stream = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._rate, self._channels, self._t0, self._count = SAMPLE_RATE, 2, 0.0, 0

    def start(self) -> None:
        import time

        import pyaudiowpatch as pa
        self._pa = pa.PyAudio()
        try:
            dev = self._pa.get_default_wasapi_loopback()
            self._rate, self._channels = int(dev["defaultSampleRate"]), int(dev["maxInputChannels"])
            self._t0, self._count = time.monotonic(), 0

            def on_audio(in_data, frame_count, time_info, status):
                block = np.frombuffer(in_data, dtype=np.int16).reshape(-1, self._channels)
                with self._lock:
                    gap = int((time.monotonic() - self._t0) * self._rate) - self._count - len(block)
                    if gap > self._rate // 5:  # more than 200 ms of nothing played
                        self._chunks.append(np.zeros((gap, self._channels), dtype=np.int16))
                        self._count += gap
                    self._chunks.append(block.copy())
                    self._count += len(block)
                return None, pa.paContinue

            self._stream = self._pa.open(format=pa.paInt16, channels=self._channels, rate=self._rate, input=True,
                                         input_device_index=dev["index"], stream_callback=on_audio)
        except Exception:
            self.stop()
            raise

    def drain(self) -> np.ndarray:
        """Audio since the last drain as mono int16 at 16 kHz, ending at the current moment."""
        import time
        with self._lock:
            if self._stream is not None:  # pad a trailing silence so this chunk lines up with the microphone
                gap = int((time.monotonic() - self._t0) * self._rate) - self._count
                if gap > self._rate // 5:
                    self._chunks.append(np.zeros((gap, self._channels), dtype=np.int16))
                    self._count += gap
            data = np.concatenate(self._chunks) if self._chunks else np.zeros((0, self._channels), dtype=np.int16)
            self._chunks = []
        return resample_mono16k(data, self._rate)

    def stop(self) -> None:
        try:
            if self._stream is not None:
                self._stream.stop_stream()
                self._stream.close()
        except Exception:
            pass
        try:
            if self._pa is not None:
                self._pa.terminate()
        except Exception:
            pass
        self._stream = self._pa = None


def list_input_devices() -> list[tuple[int, str]]:
    try:
        import sounddevice as sd
        hostapis = sd.query_hostapis()
        mme = next((i for i, h in enumerate(hostapis) if "MME" in h["name"]), None)
        out = []
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and (mme is None or d["hostapi"] == mme) and "Sound Mapper" not in d["name"]:
                out.append((i, d["name"]))
        return out
    except Exception:
        return []


class Recorder:
    def __init__(self):
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()
        self.level = 0.0  # 0..1 for the waveform

    def start(self, device: int | None = None) -> None:
        import sounddevice as sd
        self._chunks = []
        self.level = 0.0
        try:
            self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                          device=device, callback=self._on_audio, blocksize=800)
            self._stream.start()
        except Exception as exc:
            self._stream = None
            msg = str(exc).lower()
            if "invalid device" in msg or "no default" in msg or "invalid number of channels" in msg:
                raise UcapError("no_mic", str(exc)) from exc
            raise UcapError("mic_busy", str(exc)) from exc

    def _on_audio(self, indata, frames, time_info, status):
        block = indata[:, 0].copy()
        with self._lock:
            self._chunks.append(block)
        self.level = min(1.0, rms(block) / 3000.0)

    def drain(self) -> np.ndarray:
        """Everything captured so far; recording continues (used to cut long meetings into chunks)."""
        with self._lock:
            data = np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.int16)
            self._chunks = []
        return data

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        data = self.drain()
        self.level = 0.0
        return data

    @property
    def active(self) -> bool:
        return self._stream is not None
