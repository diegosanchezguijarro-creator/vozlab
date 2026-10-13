"""Leak checks: long runs of dictation cycles must not pile up threads or memory.

A tray app runs for days and repeats "start recording -> stop -> paste" hundreds
of times. If each cycle leaked a thread, the app would slow to a crawl. These
tests drive the real managers with a fake audio device and assert the baseline
is restored afterwards.
"""

import gc
import os
import struct
import sys
import threading
import time
import tracemalloc
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _thread_count() -> int:
    """Threads that would keep the process alive (daemons still count for us)."""
    return len(threading.enumerate())


@pytest.fixture
def fake_sd(monkeypatch):
    """A sounddevice stand-in that records open/close calls."""
    opened = []

    class FakeStream:
        def __init__(self, **kw):
            self.kw = kw
            self.closed = False
            opened.append(self)

        def start(self):
            if self.closed:
                raise RuntimeError("started a closed stream")

        def stop(self):
            pass

        def close(self):
            self.closed = True

    sd = types.ModuleType("sounddevice")
    sd.RawInputStream = FakeStream
    sd.query_devices = lambda *a, **k: []
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    return opened


def _pcm(value: float, samples: int = 320) -> bytes:
    return struct.pack(f"<{samples}f", *([value] * samples))


# ------------------------------------------------------------------ recorder --


def test_recorder_cycles_do_not_leak_streams(fake_sd):
    import importlib

    import vozlab.audio as audio
    importlib.reload(audio)

    rec = audio.Recorder(max_seconds=30, auto_stop=False)
    for _ in range(200):
        rec.start()
        rec._callback(_pcm(0.4), 320, None, None)
        rec.stop()

    assert all(s.closed for s in fake_sd), "a stream was left open"
    assert len(fake_sd) == 200
    assert rec._stream is None


def test_recorder_start_stop_does_not_leak_threads(fake_sd):
    import importlib

    import vozlab.audio as audio
    importlib.reload(audio)

    rec = audio.Recorder(max_seconds=30, auto_stop=False)
    rec.start()
    rec.stop()
    gc.collect()
    baseline = _thread_count()

    for _ in range(100):
        rec.start()
        rec._callback(_pcm(0.3), 320, None, None)
        rec.stop()
    gc.collect()

    assert _thread_count() <= baseline + 1, "recording cycles leaked a thread"


def test_cancelled_recordings_release_their_buffers(fake_sd):
    import importlib

    import vozlab.audio as audio
    importlib.reload(audio)

    rec = audio.Recorder(max_seconds=30, auto_stop=False)

    tracemalloc.start()
    try:
        for _ in range(20):
            rec.start()
            for _ in range(50):                       # ~1s of audio each cycle
                rec._callback(_pcm(0.5, 320), 320, None, None)
            rec.cancel()
        gc.collect()
        live = [f for f in tracemalloc.take_snapshot().statistics("filename")
                if "audio.py" in str(f.traceback)]
        current, _peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    # 20 cancelled cycles must not retain ~1s of samples each (20 * 64 kB)
    assert current < 512 * 1024, f"holding {current} bytes of audio after cancels"
    assert live is not None


def test_auto_stop_callback_does_not_block_the_audio_thread(fake_sd):
    """The callback fires on a helper thread; the audio callback returns at once."""
    import importlib

    import vozlab.audio as audio
    importlib.reload(audio)

    done = threading.Event()
    rec = audio.Recorder(auto_stop=True, silence_ms=0, silence_rms=0.01,
                         on_auto_stop=done.set)
    rec._recording = True
    t0 = time.time()
    rec._callback(_pcm(0.5), 320, None, None)
    rec._callback(_pcm(0.0), 320, None, None)
    rec._callback(_pcm(0.0), 320, None, None)
    elapsed = time.time() - t0
    assert done.wait(2.0), "auto-stop callback never ran"
    assert elapsed < 0.5, "audio callback blocked on the auto-stop handler"


# ------------------------------------------------------------------- hotkeys --


@pytest.fixture
def hotkeys_mod(monkeypatch):
    kb = types.ModuleType("keyboard")
    kb.hook = lambda cb: None
    kb.unhook_all = lambda: None
    kb.read_event = lambda suppress=False: None
    monkeypatch.setitem(sys.modules, "keyboard", kb)
    import importlib

    from vozlab import hotkeys
    importlib.reload(hotkeys)
    return hotkeys


def test_hotkey_start_stop_cycles_release_their_worker(hotkeys_mod):
    mgr = hotkeys_mod.HotkeyManager(on_down=lambda: None, on_up=lambda: None)
    mgr.start()
    mgr.stop()
    gc.collect()
    baseline = _thread_count()

    for _ in range(50):
        mgr.start()
        mgr.stop()
    gc.collect()
    time.sleep(0.05)

    assert _thread_count() <= baseline + 1, "hotkey cycles leaked a worker thread"


def test_hotkey_manager_is_not_left_running(hotkeys_mod):
    mgr = hotkeys_mod.HotkeyManager()
    mgr.start()
    mgr.stop()
    assert mgr._running is False


def test_hotkey_restart_drops_stale_events(hotkeys_mod):
    """Events queued for the old worker must not fire after a restart."""
    seen = []
    mgr = hotkeys_mod.HotkeyManager(on_down=lambda: seen.append("down"))
    mgr.set_hotkey(285)
    mgr.start()
    mgr._queue.put("down")            # nothing consumed it yet
    mgr.stop()
    mgr.start()                       # a fresh run must start clean
    time.sleep(0.4)
    mgr.stop()
    assert seen == [], "a stale key event survived the restart"
