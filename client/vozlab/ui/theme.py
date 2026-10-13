"""VozLab design system — colors, spacing, fonts, and CustomTkinter setup.

Two palettes (dark / light) live here. `apply(mode)` switches the *live* module
constants, so any window built afterwards uses the new colors; long-lived
surfaces (the tray pill) are rebuilt by the app when the theme changes.
"""

import customtkinter as ctk

# --- palettes ---------------------------------------------------------------
DARK = {
    "ACCENT": "#3B82F6",
    "ACCENT_HOVER": "#2F6FDD",
    "ACCENT_PRESSED": "#275FBE",
    "BG": "#0E1014",            # window background
    "SURFACE": "#161A21",       # cards
    "SURFACE_2": "#1D222B",     # inputs, chips
    "BORDER": "#262C37",
    "TEXT": "#F4F6F8",
    "TEXT_MUTED": "#98A1B0",
    "TEXT_FAINT": "#6B7482",
    "OK": "#22C55E",
    "WARN": "#F59E0B",
    "ERROR": "#EF4444",
    "PILL_BG": "#181C24",
    "PILL_BORDER": "#2B3240",
}

LIGHT = {
    "ACCENT": "#2563EB",
    "ACCENT_HOVER": "#1D4FD8",
    "ACCENT_PRESSED": "#1A44BB",
    "BG": "#F4F6FA",
    "SURFACE": "#FFFFFF",
    "SURFACE_2": "#EDF0F5",
    "BORDER": "#D6DBE4",
    "TEXT": "#11151C",
    "TEXT_MUTED": "#5A6472",
    "TEXT_FAINT": "#8A93A1",
    "OK": "#15803D",
    "WARN": "#B45309",
    "ERROR": "#DC2626",
    "PILL_BG": "#FFFFFF",
    "PILL_BORDER": "#C9D0DB",
}

PALETTES = {"dark": DARK, "light": LIGHT}

# --- live values (replaced by apply()) --------------------------------------
ACCENT = DARK["ACCENT"]
ACCENT_HOVER = DARK["ACCENT_HOVER"]
ACCENT_PRESSED = DARK["ACCENT_PRESSED"]

BG = DARK["BG"]
SURFACE = DARK["SURFACE"]
SURFACE_2 = DARK["SURFACE_2"]
BORDER = DARK["BORDER"]

TEXT = DARK["TEXT"]
TEXT_MUTED = DARK["TEXT_MUTED"]
TEXT_FAINT = DARK["TEXT_FAINT"]

OK = DARK["OK"]
WARN = DARK["WARN"]
ERROR = DARK["ERROR"]

# pill (drawn on a raw canvas, with #010203 used as the transparent key color)
PILL_TRANSPARENT = "#010203"
PILL_BG = DARK["PILL_BG"]
PILL_BORDER = DARK["PILL_BORDER"]

_current = "dark"
STATE_COLORS = {
    "idle": ACCENT,
    "listening": ERROR,
    "transcribing": WARN,
    "done": OK,
    "error": ERROR,
    "info": ACCENT,
}

# --- metrics ----------------------------------------------------------------
RADIUS_CARD = 14
RADIUS_CONTROL = 10
PAD = 16
PAD_S = 10
PAD_L = 24

FONT_FAMILY = "Segoe UI"


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def font_tuple(size: int = 13, weight: str = "normal"):
    return (FONT_FAMILY, size, weight)


def current() -> str:
    return _current


def apply(mode: str = "dark") -> str:
    """Switch palettes. `mode` is dark | light | system.

    Returns the palette that is now live ("dark" or "light"); "system" follows
    the OS setting and is resolved by CustomTkinter.
    """
    global _current, ACCENT, ACCENT_HOVER, ACCENT_PRESSED, BG, SURFACE, SURFACE_2
    global BORDER, TEXT, TEXT_MUTED, TEXT_FAINT, OK, WARN, ERROR, PILL_BG, PILL_BORDER
    global STATE_COLORS

    mode = (mode or "dark").lower()
    if mode not in ("dark", "light", "system"):
        mode = "dark"

    ctk.set_appearance_mode(mode)
    resolved = mode
    if mode == "system":
        try:
            resolved = "light" if ctk.get_appearance_mode().lower() == "light" else "dark"
        except Exception:  # noqa: BLE001 — very old CTk builds
            resolved = "dark"
    palette = PALETTES[resolved]
    _current = resolved

    ACCENT = palette["ACCENT"]
    ACCENT_HOVER = palette["ACCENT_HOVER"]
    ACCENT_PRESSED = palette["ACCENT_PRESSED"]
    BG = palette["BG"]
    SURFACE = palette["SURFACE"]
    SURFACE_2 = palette["SURFACE_2"]
    BORDER = palette["BORDER"]
    TEXT = palette["TEXT"]
    TEXT_MUTED = palette["TEXT_MUTED"]
    TEXT_FAINT = palette["TEXT_FAINT"]
    OK = palette["OK"]
    WARN = palette["WARN"]
    ERROR = palette["ERROR"]
    PILL_BG = palette["PILL_BG"]
    PILL_BORDER = palette["PILL_BORDER"]
    STATE_COLORS = {
        "idle": ACCENT, "listening": ERROR, "transcribing": WARN,
        "done": OK, "error": ERROR, "info": ACCENT,
    }
    return resolved


def setup(mode: str = "dark") -> None:
    """Initialise CustomTkinter with VozLab's look."""
    ctk.set_default_color_theme("blue")
    apply(mode)


class Text:
    """Named text styles (typography scale)."""

    @staticmethod
    def display():
        return font(24, "bold")

    @staticmethod
    def title():
        return font(17, "bold")

    @staticmethod
    def subtitle():
        return font(14)

    @staticmethod
    def body():
        return font(13)

    @staticmethod
    def small():
        return font(12)

    @staticmethod
    def mono():
        return ctk.CTkFont(family="Cascadia Mono", size=12)
