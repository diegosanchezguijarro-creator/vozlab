"""Which app is in the foreground? (Windows only, no dependencies.)

Per-app profiles need to know where the text will land: dictating into Slack
should read differently from dictating into Outlook. Everything here is a thin
ctypes wrapper around well-documented Win32 calls, and every function degrades
to a safe answer when it cannot know (non-Windows, no permission, no window).
"""

import ctypes
import os
import sys

IS_WINDOWS = sys.platform.startswith("win")

# Win32 constants
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_user32 = ctypes.windll.user32 if IS_WINDOWS else None
_kernel32 = ctypes.windll.kernel32 if IS_WINDOWS else None
# without these two the "process name" calls return nothing useful
try:
    import ctypes.wintypes as _wintypes
    _DWORD = _wintypes.DWORD
except (ImportError, AttributeError):  # pragma: no cover - non-Windows
    _DWORD = ctypes.c_ulong


def available() -> bool:
    return IS_WINDOWS and _user32 is not None and _kernel32 is not None


def foreground_window() -> int:
    """Handle of the window that currently has focus (0 when unknown)."""
    if not available():
        return 0
    try:
        return int(_user32.GetForegroundWindow())
    except Exception:  # noqa: BLE001 — never break dictation over this
        return 0


def window_pid(hwnd: int) -> int:
    if not available() or not hwnd:
        return 0
    try:
        pid = _DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)
    except Exception:  # noqa: BLE001
        return 0


def process_name(pid: int) -> str:
    """Executable name (lowercased, e.g. 'outlook.exe') for a process id."""
    if not available() or not pid:
        return ""
    handle = None
    try:
        handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ""
        size = _DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        ok = _kernel32.QueryFullProcessImageNameW(handle, 0, buffer,
                                                   ctypes.byref(size))
        if not ok:
            return ""
        return os.path.basename(buffer.value).lower()
    except Exception:  # noqa: BLE001
        return ""
    finally:
        if handle:
            try:
                _kernel32.CloseHandle(handle)
            except Exception:  # noqa: BLE001
                pass


def foreground_app() -> str:
    """The app you are typing into right now, or '' when it cannot be known."""
    return process_name(window_pid(foreground_window()))


def window_title(hwnd: int) -> str:
    if not available() or not hwnd:
        return ""
    try:
        length = _user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value
    except Exception:  # noqa: BLE001
        return ""
