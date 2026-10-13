"""Headless checks for the parts of the UI layer that are pure logic."""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vozlab import config as cfgmod  # noqa: E402
from vozlab.ui import theme  # noqa: E402


# ---------------------------------------------------------------- palette --


def test_dark_and_light_define_the_same_tokens():
    assert set(theme.DARK) == set(theme.LIGHT)
    assert theme.DARK != theme.LIGHT


def test_apply_switches_the_live_palette():
    theme.apply("dark")
    assert theme.BG == theme.DARK["BG"]
    assert theme.current() == "dark"

    assert theme.apply("light") == "light"
    assert theme.BG == theme.LIGHT["BG"]
    assert theme.current() == "light"

    theme.apply("dark")          # leave the module as we found it


def test_light_palette_is_readable():
    """Guard against a light theme with white-on-white text."""

    def luminance(hex_color: str) -> float:
        r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    for name, palette in (("light", theme.LIGHT), ("dark", theme.DARK)):
        assert abs(luminance(palette["TEXT"]) - luminance(palette["BG"])) > 0.4, name
        assert abs(luminance(palette["TEXT_MUTED"]) - luminance(palette["SURFACE"])) > 0.15, name


def test_state_colors_follow_the_palette():
    theme.apply("light")
    assert theme.STATE_COLORS["idle"] == theme.LIGHT["ACCENT"]
    theme.apply("dark")
    assert theme.STATE_COLORS["idle"] == theme.DARK["ACCENT"]


def test_unknown_theme_falls_back_to_dark():
    assert theme.apply("neon-disco") == "dark"


# ------------------------------------------------------------- mic devices --


@pytest.fixture
def fake_sd(monkeypatch):
    """Two microphones, the second one being the system default."""
    devices = [
        {"name": "Webcam Mic", "max_input_channels": 1, "default_samplerate": 44100.0},
        {"name": "USB Microphone", "max_input_channels": 2, "default_samplerate": 48000.0},
        {"name": "Speakers (output only)", "max_input_channels": 0, "default_samplerate": 48000.0},
    ]
    sd = types.ModuleType("sounddevice")
    sd.query_devices = lambda: devices
    sd.default = types.SimpleNamespace(device=[1, 2])
    monkeypatch.setitem(sys.modules, "sounddevice", sd)

    import importlib

    import vozlab.audio as audio
    importlib.reload(audio)
    return audio


def test_input_devices_skip_outputs(fake_sd):
    names = [d["name"] for d in fake_sd.list_input_devices()]
    assert names == ["Webcam Mic", "USB Microphone"]


def test_input_devices_flag_the_default(fake_sd):
    devices = fake_sd.list_input_devices()
    assert [d["default"] for d in devices] == [False, True]


def test_resolve_device_by_name_and_index(fake_sd):
    assert fake_sd.resolve_device("USB Microphone") == 1
    assert fake_sd.resolve_device(None) is None
    assert fake_sd.resolve_device("") is None
    assert fake_sd.resolve_device(1) == 1
    assert fake_sd.resolve_device("1") == 1


def test_a_vanished_device_falls_back_to_the_system_default(fake_sd):
    """Mics get unplugged: a stale name must not break recording."""
    assert fake_sd.resolve_device("Headset that is gone") is None


def test_devices_without_a_backend_return_empty(monkeypatch):
    import importlib

    import vozlab.audio as audio
    monkeypatch.setattr(audio, "sd", None)
    importlib.reload(audio)
    assert audio.list_input_devices() == []
    assert audio.resolve_device("anything") is None


# --------------------------------------------------------------- tray icon --


@pytest.fixture
def tray_mod(monkeypatch):
    """pystray needs a display to import on Linux; only the icons matter here."""
    fake = types.ModuleType("pystray")
    fake.Icon = lambda *a, **k: types.SimpleNamespace(
        run=lambda: None, stop=lambda: None, update_menu=lambda: None)
    fake.Menu = lambda *items: items
    fake.MenuItem = lambda *a, **k: None
    fake.Menu.SEPARATOR = None
    monkeypatch.setitem(sys.modules, "pystray", fake)
    monkeypatch.syspath_prepend(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    import importlib

    from vozlab import tray
    importlib.reload(tray)
    return tray


def test_paused_icon_differs_from_idle(tray_mod):
    assert tray_mod.make_icon("paused").tobytes() != tray_mod.make_icon("idle").tobytes()


def test_icons_render_for_every_state(tray_mod):
    for state in ("idle", "listening", "transcribing", "done", "error", "paused", "nonsense"):
        img = tray_mod.make_icon(state, size=32)
        assert img.size == (32, 32)


# ------------------------------------------------------------ new settings --


def test_new_config_keys_have_sane_defaults():
    cfg = dict(cfgmod.DEFAULTS)
    assert cfg["theme"] == "dark"
    assert cfg["pill_style"] == "full"
    assert cfg["cleanup_guard"] is True
    assert cfg["input_device"] is None           # follow the system default
    assert cfg["silence_ms"] == 1200
    assert 0 < cfg["silence_rms"] < 0.1
    assert cfg["max_seconds"] >= cfg["min_seconds"]


def test_every_config_default_survives_a_json_roundtrip(tmp_path, monkeypatch):
    """Settings are written to disk as JSON: no tuples, no sets, no bytes."""
    import json

    monkeypatch.setattr(cfgmod, "config_dir", lambda: str(tmp_path))
    monkeypatch.setattr(cfgmod, "config_path", lambda: str(tmp_path / "config.json"))
    cfgmod.save(dict(cfgmod.DEFAULTS))
    raw = json.loads((tmp_path / "config.json").read_text())
    assert set(raw) <= set(cfgmod.DEFAULTS)
