"""Logging that works both in console (dev) and windowed (frozen) builds.

Everything the app writes to disk goes through `log()`, which also scrubs known
secrets (the server token) so a log file can be shared for support without
leaking the key to the machine.
"""

import datetime
import os
import re
import sys
import threading

from . import config as cfgmod

_lock = threading.Lock()
_debug = False
_log_path = None
_console = None
_secrets: set[str] = set()

_BEARER = re.compile(r"(Bearer\s+)\S+", re.IGNORECASE)
_JSON_TOKEN = re.compile(r'("?token"?\s*[:=]\s*"?)[^",\s}]+', re.IGNORECASE)


def set_secrets(values) -> None:
    """Register values that must never appear in the log file."""
    global _secrets
    _secrets = {str(v) for v in values if v and len(str(v)) >= 8}


def redact(text: str) -> str:
    """Mask anything that looks like a credential."""
    if not isinstance(text, str):
        text = str(text)
    for secret in _secrets:
        text = text.replace(secret, "***")
    text = _BEARER.sub(r"\1***", text)
    return _JSON_TOKEN.sub(r"\1***", text)


def setup(debug: bool = False) -> str:
    """Prepare stdout/stderr and the log file. Returns the log file path."""
    global _debug, _log_path, _console
    _debug = debug

    # A windowed (--noconsole) exe has sys.stdout = None: printing would crash.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    _console = sys.stdout

    try:
        os.makedirs(cfgmod.config_dir(), exist_ok=True)
        _log_path = os.path.join(cfgmod.config_dir(), "scribe.log")
        # keep the log from growing forever
        if os.path.exists(_log_path) and os.path.getsize(_log_path) > 1_000_000:
            os.replace(_log_path, _log_path + ".1")
    except OSError:
        _log_path = None
    return _log_path or ""


def log(msg: str) -> None:
    """Always write to the log file; mirror to the console when there is one."""
    line = f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {redact(msg)}"
    with _lock:
        if _log_path:
            try:
                with open(_log_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass
        if _console is not None:
            try:
                print(line, flush=True)
            except Exception:
                pass


def debug(msg: str) -> None:
    if _debug:
        log(f"[dbg] {msg}")


def read(lines: int = 200) -> str:
    """The last `lines` lines of the log file, secrets already scrubbed."""
    if not _log_path or not os.path.exists(_log_path):
        return ""
    try:
        with open(_log_path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-max(1, lines):])
    except OSError:
        return ""


def clear() -> bool:
    """Truncate the log file (the user asked for it to be empty)."""
    if not _log_path:
        return False
    try:
        with open(_log_path, "w", encoding="utf-8"):
            pass
        for rotated in (_log_path + ".1",):
            if os.path.exists(rotated):
                os.remove(rotated)
        return True
    except OSError:
        return False


def log_path() -> str:
    return _log_path or ""
