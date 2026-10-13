"""Reusable CustomTkinter widgets: cards, status rows, key caps, toggles."""

import customtkinter as ctk

from . import theme


class Card(ctk.CTkFrame):
    """Rounded surface with an optional section title and subtitle."""

    def __init__(self, master, title: str = "", subtitle: str = "", **kwargs):
        super().__init__(master, fg_color=theme.SURFACE, corner_radius=theme.RADIUS_CARD,
                         border_width=1, border_color=theme.BORDER, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        row = 0
        if title:
            ctk.CTkLabel(self, text=title, font=theme.font(13, "bold"),
                         text_color=theme.TEXT).grid(
                row=row, column=0, sticky="w", padx=theme.PAD, pady=(theme.PAD_S + 4, 0))
            row += 1
        if subtitle:
            ctk.CTkLabel(self, text=subtitle, font=theme.font(12),
                         text_color=theme.TEXT_MUTED, justify="left", wraplength=460).grid(
                row=row, column=0, sticky="w", padx=theme.PAD, pady=(2, 0))
            row += 1
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=row, column=0, sticky="ew", padx=theme.PAD,
                       pady=(theme.PAD_S, theme.PAD))
        self.body.grid_columnconfigure(0, weight=1)


class StatusDot(ctk.CTkFrame):
    """Small colored dot used for connection state."""

    SIZE = 10

    def __init__(self, master, color: str = theme.TEXT_FAINT):
        super().__init__(master, width=self.SIZE, height=self.SIZE,
                         corner_radius=self.SIZE // 2, fg_color=color, border_width=0)

    def set_color(self, color: str) -> None:
        self.configure(fg_color=color)


class KeyCap(ctk.CTkFrame):
    """Keyboard-key looking chip that displays the dictation key."""

    def __init__(self, master, text: str = "—"):
        super().__init__(master, fg_color=theme.SURFACE_2, corner_radius=8,
                         border_width=1, border_color=theme.BORDER, height=34)
        self.label = ctk.CTkLabel(self, text=text, font=theme.font(13, "bold"),
                                  text_color=theme.TEXT, padx=14)
        self.label.pack(padx=4, pady=5)

    def set_text(self, text: str) -> None:
        self.label.configure(text=text)


class Field(ctk.CTkFrame):
    """Labeled text entry."""

    def __init__(self, master, label: str, value: str = "", placeholder: str = "",
                 show: str | None = None, width: int = 380):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=label, font=theme.font(12), text_color=theme.TEXT_MUTED).grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        self.var = ctk.StringVar(value=value)
        self.entry = ctk.CTkEntry(
            self, textvariable=self.var, placeholder_text=placeholder, height=38,
            width=width, corner_radius=theme.RADIUS_CONTROL, fg_color=theme.SURFACE_2,
            border_color=theme.BORDER, border_width=1, text_color=theme.TEXT,
            show=show,
        )
        self.entry.grid(row=1, column=0, sticky="ew")

    def get(self) -> str:
        return self.var.get().strip()

    def set(self, value: str) -> None:
        self.var.set(value)
