"""Config handling — stored in %APPDATA%\\VozLab\\config.json on Windows."""

import json
import os
import sys

from . import APP_NAME

DEFAULTS = {
    # bumped when a default changes and existing configs must be migrated
    "config_version": 2,
    # server
    "server_host": "",
    "server_port": 8092,
    "token": "",
    # hotkey
    "hotkey": None,             # scan code (int) or key name; set by calibration
    "hotkey_mode": "hold",      # "hold" (push-to-talk) or "toggle"
    "calibrate": False,         # ask for a key press on next launch
    # recording
    "auto_stop": False,         # stop automatically when you stop speaking
    "silence_ms": 1200,         # silence duration that ends an auto-stop recording
    "silence_rms": 0.012,       # audio level considered "silence"
    "min_seconds": 0.4,         # ignore shorter recordings
    "max_seconds": 60,          # hard cap per recording
    # behaviour
    "cleanup": True,            # run the LLM formatting pass
    "language": "auto",         # language hint sent to the server ("auto", "en", "es", ...)
    "beeps": False,             # sound feedback — off by default, toggle in Settings
    "restore_clipboard": True,
    "debug": False,
    # ui
    "ui_language": "auto",      # "auto" (follow Windows), "en", "es"
    "show_pill": True,
    "pill_position": "bottom-center",   # bottom-center | bottom-right | top-right
    "launch_at_login": False,
    "first_run_done": False,
}


def config_dir() -> str:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_NAME)
    return os.path.join(os.path.expanduser("~"), ".config", APP_NAME.lower())


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


def load() -> dict:
    cfg = dict(DEFAULTS)
    stored = {}
    try:
        with open(config_path()) as f:
            stored = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    cfg.update(stored)

    # --- migrations ---------------------------------------------------------
    # v2: sound feedback used to be on by default; newer versions are silent
    # unless the user turns it on in Settings.
    if stored.get("config_version", 1) < 2:
        cfg["beeps"] = False
        cfg["config_version"] = 2
    return cfg


def save(cfg: dict) -> None:
    os.makedirs(config_dir(), exist_ok=True)
    tmp = config_path() + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    os.replace(tmp, config_path())


def server_url(cfg: dict) -> str:
    """Build the base URL from host/port (accepts a full URL in server_host)."""
    host = (cfg.get("server_host") or "").strip().rstrip("/")
    if not host:
        return ""
    if host.startswith(("http://", "https://")):
        return host
    return f"http://{host}:{cfg.get('server_port') or 8092}"


def parse_server_url(url: str, cfg: dict) -> None:
    """Store a user-entered URL back into host/port fields."""
    url = url.strip().rstrip("/")
    if url.startswith("http://"):
        url = url[len("http://"):]
    elif url.startswith("https://"):
        cfg["server_host"] = "https://" + url[len("https://"):]
        return
    if ":" in url:
        host, _, port = url.rpartition(":")
        if port.isdigit():
            cfg["server_host"] = host
            cfg["server_port"] = int(port)
            return
    cfg["server_host"] = url
