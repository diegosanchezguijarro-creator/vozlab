"""Platform differences, in one place.

VozLab's supported client is Windows. The app runs on macOS and Linux for
development and for the parts that do not need a global keyboard hook, so the
handful of places that genuinely differ live here instead of being scattered
through the code as `sys.platform` checks.
"""

import sys

WINDOWS = sys.platform.startswith("win")
MACOS = sys.platform == "darwin"
LINUX = sys.platform.startswith("linux")


def paste_shortcut() -> str:
    """The key combination that pastes into the focused app."""
    return "command+v" if MACOS else "ctrl+v"


def hotkey_note() -> str:
    """Why global hotkeys may not work on this platform ('' = they should)."""
    if MACOS:
        return ("macOS needs Accessibility permission for global hotkeys: "
                "System Settings → Privacy & Security → Accessibility → add your "
                "terminal or pythonw. Paste uses ⌘V.")
    if LINUX:
        return ("Linux needs read access to /dev/input (add your user to the "
                "'input' group) and an X11 session for global hotkeys.")
    return ""


def secrets_are_encrypted() -> bool:
    """Whether the token can be encrypted at rest (Windows DPAPI only)."""
    return WINDOWS


def tray_backend() -> str:
    if WINDOWS:
        return "win32"
    if MACOS:
        return "darwin"
    return "xorg"


def describe() -> str:
    """One line for the diagnostics report."""
    from . import foreground
    parts = [f"{sys.platform}"]
    if WINDOWS:
        parts.append("global hotkeys: yes" if foreground.available() else "global hotkeys: limited")
    else:
        parts.append("global hotkeys: best-effort")
    parts.append("token encrypted at rest: " + ("yes (DPAPI)" if secrets_are_encrypted() else "no"))
    return " · ".join(parts)
