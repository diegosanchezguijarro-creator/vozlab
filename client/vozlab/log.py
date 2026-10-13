"""Logging that works both in console (dev) and windowed (frozen) builds."""

import datetime
import os
import sys
import threading

from . import config as cfgmod

_lock = threading.Lock()
_debug = False
_log_path = None
_console = None


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
        _log_path = os.path.join(cfgmod.config_dir(), "vozlab.log")
        # keep the log from growing forever
        if os.path.exists(_log_path) and os.path.getsize(_log_path) > 1_000_000:
            os.replace(_log_path, _log_path + ".1")
    except OSError:
        _log_path = None
    return _log_path or ""


def log(msg: str) -> None:
    """Always write to the log file; mirror to the console when there is one."""
    line = f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
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


def log_path() -> str:
    return _log_path or ""
