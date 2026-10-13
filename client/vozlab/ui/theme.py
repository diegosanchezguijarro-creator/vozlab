"""VozLab design system — colors, spacing, fonts, and CustomTkinter setup."""

import customtkinter as ctk

# --- palette ----------------------------------------------------------------
ACCENT = "#3B82F6"
ACCENT_HOVER = "#2F6FDD"
ACCENT_PRESSED = "#275FBE"

BG = "#0E1014"           # window background
SURFACE = "#161A21"      # cards
SURFACE_2 = "#1D222B"    # inputs, chips
BORDER = "#262C37"

TEXT = "#F4F6F8"
TEXT_MUTED = "#98A1B0"
TEXT_FAINT = "#6B7482"

OK = "#22C55E"
WARN = "#F59E0B"
ERROR = "#EF4444"

# pill (drawn on a raw canvas, with #010203 used as the transparent key color)
PILL_TRANSPARENT = "#010203"
PILL_BG = "#181C24"
PILL_BORDER = "#2B3240"

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


def setup() -> None:
    """Initialise CustomTkinter with VozLab's look."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")


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
