"""Styled About dialog."""

import customtkinter as ctk

from .. import DISPLAY_NAME, VERSION
from .. import config as cfgmod
from .. import hotkeys as hotkeys_mod
from . import theme


class AboutWindow:
    def __init__(self, app):
        self.app = app
        tr = app.tr
        cfg = app.cfg

        self.win = ctk.CTkToplevel(app.root)
        self.win.title(tr("menu_about"))
        self.win.geometry("420x420")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)

        ctk.CTkLabel(self.win, text="🎙️", font=theme.font(46)).pack(pady=(34, 6))
        ctk.CTkLabel(self.win, text=DISPLAY_NAME, font=theme.font(24, "bold")).pack()
        ctk.CTkLabel(self.win, text=f"v{VERSION}", font=theme.font(12),
                     text_color=theme.TEXT_MUTED).pack(pady=(2, 0))
        ctk.CTkLabel(self.win, text=tr("about_tagline"), font=theme.font(12),
                     text_color=theme.TEXT_MUTED, wraplength=330, justify="center").pack(pady=(12, 0))

        info = ctk.CTkFrame(self.win, fg_color=theme.SURFACE, corner_radius=theme.RADIUS_CARD,
                            border_width=1, border_color=theme.BORDER)
        info.pack(fill="x", padx=theme.PAD_L, pady=theme.PAD_L)
        rows = [
            (tr("settings_server"), cfgmod.server_url(cfg) or "—"),
            (tr("settings_hotkey"), hotkeys_mod.describe_hotkey(cfg.get("hotkey"))),
            (tr("settings_token"), (cfg.get("token") or "—")[:12] + "…"),
        ]
        for label, value in rows:
            row = ctk.CTkFrame(info, fg_color="transparent")
            row.pack(fill="x", padx=theme.PAD, pady=5)
            ctk.CTkLabel(row, text=label, font=theme.font(12),
                         text_color=theme.TEXT_MUTED).pack(side="left")
            ctk.CTkLabel(row, text=value, font=theme.font(12, "bold")).pack(side="right")

        ctk.CTkButton(self.win, text=tr("about_close"), width=120, height=38,
                      corner_radius=theme.RADIUS_CONTROL, font=theme.font(13),
                      fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                      command=self.win.destroy).pack(pady=(0, theme.PAD_L))
