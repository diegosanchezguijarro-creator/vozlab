"""Microphone recording with optional silence-based auto-stop."""

import io
import threading
import wave

import numpy as np

try:
    import sounddevice as sd
except (ImportError, OSError):  # PortAudio missing — only matters when recording
    sd = None

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 4  # float32


class AudioError(Exception):
    pass


class Recorder:
    """Records mono float32 audio at 16 kHz and returns 16-bit PCM WAV bytes."""

    def __init__(self,
                 sample_rate: int = SAMPLE_RATE,
                 max_seconds: float = 60,
                 silence_ms: int = 1200,
                 silence_rms: float = 0.012,
                 auto_stop: bool = False,
                 on_auto_stop=None,
                 on_level=None,
                 device=None):
        self.sample_rate = sample_rate
        self.max_seconds = max_seconds
        self.silence_ms = silence_ms
        self.silence_rms = silence_rms
        self.auto_stop = auto_stop
        self.on_auto_stop = on_auto_stop      # called (once) when silence ends the recording
        self.on_level = on_level              # called with current RMS (for UI meters)
        self.device = device                  # None = system default, or a device name/index

        self._stream = None
        self._frames = []
        self._lock = threading.Lock()
        self._recording = False
        self._speech_seen = False
        self._silence_since = None
        self._auto_stopped = False
        self._last_duration = 0.0     # duration of the recording that just finished

    # -- state ---------------------------------------------------------------
    @property
    def recording(self) -> bool:
        return self._recording

    def duration(self) -> float:
        """Seconds captured: live while recording, otherwise the last recording.

        NOTE: stop() clears the frame buffer, so the finished recording's length
        is remembered in _last_duration — callers ask for the duration after
        stopping (and used to always get 0.0).
        """
        with self._lock:
            if not self._recording:
                return self._last_duration
            return sum(len(f) for f in self._frames) / (self.sample_rate * BYTES_PER_SAMPLE)

    # -- control -------------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._recording:
                return
            self._recording = True
            self._frames = []
            self._last_duration = 0.0
            self._speech_seen = False
            self._silence_since = None
            self._auto_stopped = False

        try:
            if sd is None:
                raise AudioError("audio backend unavailable (PortAudio library missing)")
            self._stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=0,
                channels=1,
                dtype="float32",
                callback=self._callback,
                device=self.device if self.device is not None else None,
            )
            self._stream.start()
        except Exception as e:  # PortAudio error, no device, privacy block...
            with self._lock:
                self._recording = False
            self._stream = None
            raise AudioError(str(e)) from e

    def stop(self) -> bytes | None:
        """Stop recording. Returns WAV bytes, or None if nothing was captured."""
        with self._lock:
            if not self._recording:
                return None
            self._recording = False

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        with self._lock:
            frames = self._frames
            self._frames = []
            self._last_duration = sum(len(f) for f in frames) / (
                self.sample_rate * BYTES_PER_SAMPLE)
        if not frames:
            return None
        return _to_wav(frames, self.sample_rate)

    def cancel(self) -> None:
        with self._lock:
            self._recording = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        with self._lock:
            self._frames = []

    # -- internals -----------------------------------------------------------
    def _callback(self, indata, _frames, _time, status):
        if not self._recording:
            return
        chunk = bytes(indata)
        with self._lock:
            self._frames.append(chunk)
            total_bytes = sum(len(f) for f in self._frames)

        # hard cap
        if total_bytes >= self.max_seconds * self.sample_rate * BYTES_PER_SAMPLE:
            if not self._auto_stopped:
                self._auto_stopped = True
                self._fire(self.on_auto_stop)
            return

        if not self.auto_stop and not self.on_level:
            return

        samples = np.frombuffer(chunk, dtype=np.float32)
        rms = float(np.sqrt(np.mean(samples ** 2))) if samples.size else 0.0
        if self.on_level:
            self.on_level(rms)          # live level meter in the UI
        if not self.auto_stop:
            return

        now = _now_ms()
        if rms >= self.silence_rms:
            self._speech_seen = True
            self._silence_since = None
            return

        # silence
        if not self._speech_seen:
            return  # ignore leading silence
        if self._silence_since is None:
            self._silence_since = now
        elif now - self._silence_since >= self.silence_ms and not self._auto_stopped:
            self._auto_stopped = True
            self._fire(self.on_auto_stop)

    @staticmethod
    def _fire(callback):
        if callback:
            threading.Thread(target=callback, daemon=True).start()


def _now_ms() -> float:
    import time
    return time.time() * 1000.0


def list_input_devices() -> list[dict]:
    """Microphones the user can choose from (empty list when unavailable)."""
    if sd is None:
        return []
    try:
        default_in = sd.default.device[0] if sd.default.device else None
    except (AttributeError, IndexError, TypeError):
        default_in = None
    devices = []
    try:
        for index, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) < 1:
                continue
            devices.append({
                "index": index,
                "name": dev.get("name", f"device {index}"),
                "channels": dev.get("max_input_channels", 0),
                "sample_rate": int(dev.get("default_samplerate") or 0),
                "default": index == default_in,
            })
    except Exception:  # noqa: BLE001 — PortAudio can raise on odd hosts
        return []
    return devices


def resolve_device(name_or_index) -> int | None:
    """Turn a saved device name back into a live index (devices move around)."""
    if name_or_index is None or name_or_index == "":
        return None
    if isinstance(name_or_index, int) or str(name_or_index).isdigit():
        return int(name_or_index)
    for dev in list_input_devices():
        if dev["name"] == name_or_index:
            return dev["index"]
    return None


def _to_wav(frames, sample_rate: int) -> bytes:
    """Pack float32 frames into a 16-bit PCM WAV."""
    pcm = (np.frombuffer(b"".join(frames), dtype=np.float32) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()
