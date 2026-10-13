"""Config handling — stored in %APPDATA%\\VozLab\\config.json on Windows.

The access token is kept out of the file: it is encrypted with Windows DPAPI and
stored base64-encoded in `token_enc` (see secretstore.py). In memory it is always
available as `cfg["token"]`, so the rest of the app doesn't care.
"""

import json
import os
import sys

from . import APP_NAME, secretstore

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
    "input_device": None,       # None = system default; otherwise the device name
    # behaviour
    "cleanup": True,            # run the LLM formatting pass
    "cleanup_guard": True,      # keep the raw text if the cleanup model rewrites it
    "language": "auto",         # language hint sent to the server ("auto", "en", "es", ...)
    "beeps": False,             # sound feedback — off by default, toggle in Settings
    "restore_clipboard": True,
    "debug": False,
    # ui
    "ui_language": "auto",      # "auto" (follow Windows), "en", "es"
    "theme": "dark",            # dark | light | system
    "show_pill": True,
    "pill_position": "bottom-center",   # bottom-center | bottom-right | top-right
    "pill_style": "full",       # full | minimal
    "device_name": "",          # label shown on the server's device list
    "launch_at_login": False,
    "check_updates": False,     # opt-in: the only request that leaves your LAN
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

    # --- secrets ------------------------------------------------------------
    # `token_enc` (DPAPI) wins; a plain `token` from an older version is picked
    # up and re-encrypted on the next save.
    token = ""
    encrypted = stored.get("token_enc")
    if encrypted:
        try:
            token = secretstore.unprotect(encrypted)
        except OSError as e:
            print(f"[vozlab] could not decrypt the stored token: {e}", file=sys.stderr)
            token = ""
    if not token:
        token = stored.get("token", "") or ""
    cfg["token"] = token
    cfg["token_encrypted"] = bool(encrypted)

    # --- migrations ---------------------------------------------------------
    # v2: sound feedback used to be on by default; newer versions are silent
    # unless the user turns it on in Settings.
    if stored.get("config_version", 1) < 2:
        cfg["beeps"] = False
        cfg["config_version"] = 2
    return cfg


def save(cfg: dict) -> None:
    os.makedirs(config_dir(), exist_ok=True)
    payload = dict(cfg)
    payload.pop("token_encrypted", None)
    token = payload.pop("token", "") or ""
    payload.pop("token_enc", None)
    if token:
        try:
            payload["token_enc"] = secretstore.protect(token)
        except OSError:
            payload["token"] = token      # DPAPI unavailable: keep it working
    tmp = config_path() + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
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
