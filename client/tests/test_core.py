"""Core logic tests — run headless, no display/audio hardware needed.

    pip install -r requirements-dev.txt
    pytest tests/ -v
"""

import json
import os
import sys
import threading
import time
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vozlab import config as cfgmod  # noqa: E402
from vozlab import i18n  # noqa: E402


# ---------------------------------------------------------------- config ----
@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "config_dir", lambda: str(tmp_path))
    monkeypatch.setattr(cfgmod, "config_path", lambda: str(tmp_path / "config.json"))
    return tmp_path


def test_config_defaults_and_roundtrip(tmp_config):
    cfg = cfgmod.load()
    assert cfg["hotkey_mode"] == "hold"
    assert cfg["cleanup"] is True
    assert cfg["beeps"] is False, "sound feedback must be off by default"

    cfg["server_host"] = "10.0.0.5"
    cfg["token"] = "abc"
    cfgmod.save(cfg)

    again = cfgmod.load()
    assert again["server_host"] == "10.0.0.5"
    assert again["token"] == "abc"
    # unknown/partial files must not explode
    (tmp_config / "config.json").write_text("{ not json")
    assert cfgmod.load()["hotkey_mode"] == "hold"


def test_migration_silences_existing_configs(tmp_config):
    """v1 configs had beeps=True stored; the v2 migration turns sound off once."""
    (tmp_config / "config.json").write_text(json.dumps({
        "server_host": "10.0.0.5", "beeps": True, "cleanup": False,
    }))
    cfg = cfgmod.load()
    assert cfg["beeps"] is False
    assert cfg["cleanup"] is False, "other user settings must survive migration"
    assert cfg["config_version"] == 2


def test_migration_keeps_sound_when_user_explicitly_enabled_it(tmp_config):
    (tmp_config / "config.json").write_text(json.dumps({
        "config_version": 2, "beeps": True,
    }))
    assert cfgmod.load()["beeps"] is True


def test_server_url_and_parsing():
    cfg = {"server_host": "192.168.0.23", "server_port": 8092}
    assert cfgmod.server_url(cfg) == "http://192.168.0.23:8092"

    cfgmod.parse_server_url("http://10.1.1.7:9000", cfg)
    assert cfg == {"server_host": "10.1.1.7", "server_port": 9000}

    cfgmod.parse_server_url("10.1.1.7", cfg)
    assert cfg["server_host"] == "10.1.1.7"

    assert cfgmod.server_url({"server_host": "", "server_port": 8092}) == ""


# ----------------------------------------------------------------- i18n -----
def test_i18n_translations_and_fallback():
    tr = i18n.Translator("es")
    assert tr("state_listening") == "Escuchando…"
    assert tr("wizard_test_ok", model="small", device="cuda").startswith("¡Conectado!")

    tr.set_language("en")
    assert tr("state_listening") == "Listening…"
    assert tr("does_not_exist") == "does_not_exist"

    tr.set_language("klingon")   # unknown -> english
    assert tr.language == "en"


# ------------------------------------------------------------------ api -----
def _fake_requests(monkeypatch, status=200, payload=None, raise_exc=None):
    import requests as real_requests

    from vozlab import api as apimod

    class Resp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = json.dumps(payload or {})

        def json(self):
            return self._payload

    calls = {}

    def fake_get(url, headers=None, timeout=None):
        calls["url"] = url
        calls["headers"] = headers
        if raise_exc:
            raise raise_exc
        return Resp(status, payload)

    def fake_post(url, params=None, headers=None, data=None, timeout=None):
        calls["url"] = url
        calls["params"] = params
        calls["data_len"] = len(data or b"")
        calls["headers"] = headers
        if raise_exc:
            raise raise_exc
        return Resp(status, payload)

    monkeypatch.setattr(apimod.requests, "get", fake_get)
    monkeypatch.setattr(apimod.requests, "post", fake_post)
    monkeypatch.setattr(apimod.requests, "RequestException", real_requests.RequestException)
    return calls


def test_api_health_ok(monkeypatch):
    calls = _fake_requests(monkeypatch, payload={"ok": True, "whisper_model": "small"})
    from vozlab.api import VozLabAPI
    health = VozLabAPI("http://h:8092", "tok").health()
    assert health["ok"] is True
    assert calls["url"] == "http://h:8092/health"
    assert calls["headers"]["Authorization"] == "Bearer tok"


def test_api_transcribe_params(monkeypatch):
    calls = _fake_requests(monkeypatch, payload={"text": "hola", "raw_text": "hola",
                                                 "timings": {"total_s": 1.0}})
    from vozlab.api import VozLabAPI
    out = VozLabAPI("http://h:8092", "tok").transcribe(b"RIFFdata", cleanup=False, language="es")
    assert out["text"] == "hola"
    assert calls["params"] == {"cleanup": "false", "language": "es"}
    assert calls["data_len"] == len(b"RIFFdata")


@pytest.mark.parametrize("status,kind", [(401, "bad_token"), (500, "server")])
def test_api_error_mapping(monkeypatch, status, kind):
    _fake_requests(monkeypatch, status=status, payload={"detail": "nope"})
    from vozlab.api import ApiError, VozLabAPI
    with pytest.raises(ApiError) as err:
        VozLabAPI("http://h:8092", "tok").health()
    assert err.value.kind == kind


def test_api_too_large_maps_to_other(monkeypatch):
    _fake_requests(monkeypatch, status=413, payload={"detail": "too big"})
    from vozlab.api import ApiError, VozLabAPI
    with pytest.raises(ApiError) as err:
        VozLabAPI("http://h:8092", "tok").transcribe(b"RIFF" * 10)
    assert err.value.kind == "other"


def test_api_unreachable(monkeypatch):
    import requests as real_requests
    _fake_requests(monkeypatch, raise_exc=real_requests.ConnectionError("boom"))
    from vozlab.api import ApiError, VozLabAPI
    with pytest.raises(ApiError) as err:
        VozLabAPI("http://h:8092", "tok").health()
    assert err.value.kind == "unreachable"


# -------------------------------------------------------------- hotkeys -----
class FakeEvent:
    def __init__(self, name, scan, etype="down"):
        self.name, self.scan_code, self.event_type = name, scan, etype


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


def test_hotkey_matching_by_scan_code(hotkeys_mod):
    mgr = hotkeys_mod.HotkeyManager()
    mgr.set_hotkey(285)
    assert mgr.matches(FakeEvent("ctrl derecha", 285))
    assert not mgr.matches(FakeEvent("ctrl izquierda", 29))
    assert not mgr.matches(FakeEvent("a", 30))


def test_hotkey_matching_by_name_and_alias(hotkeys_mod):
    mgr = hotkeys_mod.HotkeyManager()
    mgr.set_hotkey("right shift")
    assert mgr.matches(FakeEvent("right shift", 54))
    assert not mgr.matches(FakeEvent("ctrl derecha", 285))

    mgr.set_hotkey("right ctrl")           # english name configured
    assert mgr.matches(FakeEvent("ctrl derecha", 285))  # spanish localized event
    assert mgr.matches(FakeEvent("right ctrl", 285))


def test_hotkey_unset_accepts_right_ctrl(hotkeys_mod):
    mgr = hotkeys_mod.HotkeyManager()
    assert mgr.matches(FakeEvent("ctrl derecha", 285))
    assert mgr.matches(FakeEvent("right ctrl", 285))


def test_hotkey_worker_dispatches(hotkeys_mod):
    seen = []
    mgr = hotkeys_mod.HotkeyManager(on_down=lambda: seen.append("down"),
                                    on_up=lambda: seen.append("up"))
    mgr.set_hotkey(285)
    stop = threading.Event()
    mgr._queue.put("down")
    mgr._queue.put("up")
    t = threading.Thread(target=mgr._run_worker, args=(stop,), daemon=True)
    t.start()
    for _ in range(50):
        if len(seen) == 2:
            break
        time.sleep(0.02)
    stop.set()
    assert seen == ["down", "up"]


def test_describe_hotkey(hotkeys_mod):
    assert hotkeys_mod.describe_hotkey(285) == "right Ctrl"
    assert hotkeys_mod.describe_hotkey(54) == "scan code 54"
    assert hotkeys_mod.describe_hotkey(None) == "(not set)"


# ---------------------------------------------------------------- audio -----
def test_to_wav_is_valid_riff():
    import wave

    from vozlab.audio import _to_wav

    frames = [b"\x00\x00\x00\x00" * 1600]  # 0.1s of silence
    data = _to_wav(frames, 16000)
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"

    import io
    with wave.open(io.BytesIO(data)) as w:
        assert w.getframerate() == 16000
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2


def _pcm(value: float, samples: int = 100) -> bytes:
    """Packed little-endian float32 samples with a constant value."""
    import struct
    return struct.pack(f"<{samples}f", *([value] * samples))


def test_auto_stop_fires_after_silence():
    from vozlab.audio import Recorder

    fired = []
    rec = Recorder(auto_stop=True, silence_ms=0, silence_rms=0.01,
                   on_auto_stop=lambda: fired.append(True))
    rec._recording = True

    rec._callback(_pcm(0.5), 100, None, None)      # speech -> arms the detector
    assert not fired
    rec._callback(_pcm(0.0), 100, None, None)      # silence starts the timer…
    assert not fired
    rec._callback(_pcm(0.0), 100, None, None)      # …and the next chunk trips it (silence_ms=0)
    assert fired, "auto-stop did not trigger on trailing silence"


def test_auto_stop_ignores_leading_silence():
    from vozlab.audio import Recorder

    fired = []
    rec = Recorder(auto_stop=True, silence_ms=0, silence_rms=0.01,
                   on_auto_stop=lambda: fired.append(True))
    rec._recording = True
    rec._callback(_pcm(0.0), 100, None, None)
    rec._callback(_pcm(0.0), 100, None, None)
    assert not fired, "auto-stop must not trigger before any speech"


def test_recorder_duration_and_max_seconds():
    from vozlab.audio import Recorder

    rec = Recorder(max_seconds=1, auto_stop=False)
    rec._recording = True
    fired = []
    rec.on_auto_stop = lambda: fired.append(True)
    rec._callback(_pcm(0.0, 16000), 16000, None, None)  # 1s of audio
    assert rec.duration() == pytest.approx(1.0, abs=0.05)
    assert fired, "max length must auto-stop"


def test_duration_survives_stop():
    """Regression: the app asks for duration AFTER stop(), which clears the
    frame buffer — so every recording used to look 0s long and was rejected
    with 'recording too short'."""
    import io
    import wave

    from vozlab.audio import Recorder

    rec = Recorder(max_seconds=60, auto_stop=False)
    rec._recording = True
    rec._callback(_pcm(0.3, 16000), 16000, None, None)   # 1.0s of audio
    wav = rec.stop()

    assert wav is not None, "audio was captured, stop() must return WAV data"
    assert rec.duration() == pytest.approx(1.0, abs=0.05), \
        "duration after stop() must reflect the finished recording"
    assert rec.duration() >= 0.4, "a 1s recording must pass the min_seconds check"

    # and the WAV itself really contains that audio
    with wave.open(io.BytesIO(wav)) as w:
        seconds = w.getnframes() / w.getframerate()
    assert seconds == pytest.approx(1.0, abs=0.05)


def test_stop_twice_is_safe_and_keeps_duration():
    from vozlab.audio import Recorder

    rec = Recorder(max_seconds=60)
    rec._recording = True
    rec._callback(_pcm(0.3, 16000), 16000, None, None)
    first = rec.stop()
    second = rec.stop()          # key-up after an auto-stop, for example
    assert first is not None
    assert second is None
    assert rec.duration() == pytest.approx(1.0, abs=0.05)


def test_cancel_resets_duration():
    from vozlab.audio import Recorder

    rec = Recorder(max_seconds=60)
    rec._recording = True
    rec._callback(_pcm(0.3, 16000), 16000, None, None)
    rec.cancel()
    assert rec.duration() == 0.0


# ----------------------------------------------------------- diagnostics ----
def test_diagnostics_redacts_transcripts_and_token(tmp_path):
    from vozlab import diagnostics

    log = tmp_path / "vozlab.log"
    log.write_text(
        "2026-10-13 10:00:00 VozLab 1.1.2 starting\n"
        "2026-10-13 10:00:05 dictation (0.42s): my bank password is hunter2\n"
        "2026-10-13 10:00:06 [dbg] transcribed in 0.42s raw='um my bank password is hunter2' final='My bank password is hunter2.'\n"
        "2026-10-13 10:00:07 server ok {'version': '1.1.2'}\n",
        encoding="utf-8",
    )
    report = diagnostics.build_report(
        {"token": "super-secret-token", "server_host": "192.168.0.23", "hotkey": 285},
        log_path=str(log),
        server_health={"version": "1.1.2", "whisper_model": "small", "device": "cuda"},
    )

    assert "hunter2" not in report, "dictated text must never appear in a report"
    assert "my bank password" not in report
    assert "super-secret-token" not in report
    assert "<redacted>" in report

    # useful information must survive
    assert "192.168.0.23" in report
    assert "whisper_model" in report and "cuda" in report
    assert "VozLab 1.1.2 starting" in report


def test_diagnostics_handles_missing_log(tmp_path):
    from vozlab import diagnostics

    report = diagnostics.build_report({"token": "x"}, log_path=str(tmp_path / "nope.log"))
    assert "(no log file)" in report


def test_diagnostics_write_report(tmp_path):
    from vozlab import diagnostics

    path = diagnostics.write_report(str(tmp_path), {"token": "x", "beeps": False})
    assert os.path.exists(path)
    content = open(path, encoding="utf-8").read()
    assert "VozLab diagnostics" in content
    assert "x" not in content.split("token")[1].split("\n")[0]  # token value redacted


# ------------------------------------------------------------- updater ------
def test_version_parsing():
    from vozlab.updater import parse_version

    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("1.2.3") == (1, 2, 3)
    assert parse_version("1.2") == (1, 2, 0)
    assert parse_version("v1.2.3-rc4") == (1, 2, 3)
    assert parse_version("") == (0, 0, 0)
    assert parse_version("garbage") == (0, 0, 0)


def test_is_newer():
    from vozlab.updater import is_newer

    assert is_newer("1.1.1", "1.1.0")
    assert is_newer("1.2.0", "1.1.9")
    assert is_newer("2.0.0", "1.99.99")
    assert not is_newer("1.1.0", "1.1.0")
    assert not is_newer("1.0.9", "1.1.0")
    assert not is_newer("garbage", "1.1.0")


def test_version_mismatch_only_cares_about_major_minor():
    from vozlab.updater import version_mismatch

    assert not version_mismatch("1.1.2", "1.1.9")      # patch drift is fine
    assert version_mismatch("1.0.0", "1.1.0")
    assert version_mismatch("2.0.0", "1.1.0")
    assert not version_mismatch("1.1.2", "1.1.2")


def test_updater_check_returns_none_when_current(monkeypatch):
    from vozlab import updater

    monkeypatch.setattr(updater, "latest_release",
                        lambda repo=updater.DEFAULT_REPO, timeout=8.0: {
                            "tag": "v1.1.0", "version": "1.1.0", "url": "", "notes": ""})
    assert updater.check(current="1.1.0") is None
    found = updater.check(current="1.0.0")
    assert found and found["version"] == "1.1.0"


def test_updater_raises_friendly_error(monkeypatch):
    import requests

    from vozlab import updater

    def boom(*_a, **_k):
        raise requests.ConnectionError("no internet")

    monkeypatch.setattr(updater.requests, "get", boom)
    with pytest.raises(updater.UpdateError):
        updater.latest_release()


def test_update_check_is_off_by_default():
    from vozlab import config as cfgmod

    assert cfgmod.DEFAULTS["check_updates"] is False, \
        "zero telemetry: no network calls unless the user opts in"


# ------------------------------------------------------------- packaging ----
def test_version_exposed():
    from vozlab import VERSION
    assert VERSION.count(".") == 2
