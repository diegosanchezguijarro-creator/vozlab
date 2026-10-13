"""Settings window — grouped cards, toggles and live connection status."""

import threading
import tkinter as tk

import customtkinter as ctk

from .. import APP_NAME, VERSION
from .. import config as cfgmod
from .. import hotkeys as hotkeys_mod
from ..api import ApiError, VozLabAPI
from . import theme, widgets

LANGUAGES = ["auto", "en", "es", "fr", "de", "it", "pt", "nl", "ru", "ja", "zh", "ko", "ar", "hi", "tr", "pl", "sv"]


class HotkeyCaptureDialog:
    """Modal 'press a key' dialog."""

    def __init__(self, app, on_captured):
        self.app = app
        self.on_captured = on_captured
        tr = app.tr

        self.win = ctk.CTkToplevel(app.root)
        self.win.title(tr("settings_hotkey"))
        self.win.geometry("380x190")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)

        ctk.CTkLabel(self.win, text="⌨️", font=theme.font(34)).pack(pady=(22, 4))
        self.label = ctk.CTkLabel(self.win, text=tr("wizard_press_key"),
                                  font=theme.font(15, "bold"))
        self.label.pack()
        self.hint = ctk.CTkLabel(self.win, text=tr("wizard_hotkey_hint"),
                                 font=theme.font(12), text_color=theme.TEXT_MUTED,
                                 wraplength=320, justify="center")
        self.hint.pack(pady=(6, 0), padx=20)

        threading.Thread(target=self._capture, daemon=True).start()

    def _capture(self):
        result = hotkeys_mod.HotkeyManager.capture_next_key(timeout=30)
        if not result:
            self.win.after(0, self.win.destroy)
            return
        code, name = result
        self.win.after(0, lambda: self.label.configure(
            text=self.app.tr("wizard_hotkey_captured", name=name or str(code))))
        self.win.after(500, lambda: self._finish(code, name))

    def _finish(self, code, name):
        self.win.destroy()
        self.on_captured(code, name)


class SettingsWindow:
    def __init__(self, app, on_saved=None):
        self.app = app
        self.on_saved = on_saved
        self.cfg = dict(app.cfg)
        tr = app.tr

        self.win = ctk.CTkToplevel(app.root)
        self.win.title(f"{APP_NAME} — {tr('settings_title')}")
        self.win.geometry("700x720")
        self.win.minsize(680, 560)

        # ------------------------------------------------------------------ head
        head = ctk.CTkFrame(self.win, fg_color="transparent")
        head.pack(fill="x", padx=theme.PAD_L, pady=(theme.PAD_L, theme.PAD_S))

        left = ctk.CTkFrame(head, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text=APP_NAME, font=theme.font(22, "bold")).pack(anchor="w")
        ctk.CTkLabel(left, text=f"v{VERSION} · 100% local", font=theme.font(12),
                     text_color=theme.TEXT_MUTED).pack(anchor="w")

        status = ctk.CTkFrame(head, fg_color="transparent")
        status.pack(side="right")
        self.status_dot = widgets.StatusDot(status, theme.TEXT_FAINT)
        self.status_dot.pack(side="left", padx=(0, 8))
        self.status_label = ctk.CTkLabel(status, text=tr("status_unknown"),
                                         font=theme.font(12), text_color=theme.TEXT_MUTED)
        self.status_label.pack(side="left")

        # ---------------------------------------------------------------- body
        scroll = ctk.CTkScrollableFrame(self.win, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=theme.PAD_L - 6, pady=0)

        self._build_connection(scroll)
        self._build_dictation(scroll)
        self._build_ai(scroll)
        self._build_appearance(scroll)
        self._build_system(scroll)

        # -------------------------------------------------------------- footer
        footer = ctk.CTkFrame(self.win, fg_color="transparent")
        footer.pack(fill="x", padx=theme.PAD_L, pady=theme.PAD)
        self.save_btn = ctk.CTkButton(
            footer, text=tr("settings_save"), height=40, corner_radius=theme.RADIUS_CONTROL,
            font=theme.font(13, "bold"), fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            command=self._save)
        self.save_btn.pack(side="right")
        ctk.CTkButton(
            footer, text=tr("settings_cancel"), height=40, width=110,
            corner_radius=theme.RADIUS_CONTROL, font=theme.font(13),
            fg_color="transparent", border_width=1, border_color=theme.BORDER,
            hover_color=theme.SURFACE_2, command=self.win.destroy).pack(side="right", padx=(0, 10))

        self._probe_status()

    # ---------------------------------------------------------------- sections
    def _build_connection(self, parent):
        tr = self.app.tr
        card = widgets.Card(parent, tr("group_connection"), tr("group_connection_hint"))
        card.pack(fill="x", pady=(0, theme.PAD_S))

        self.server_field = widgets.Field(card.body, tr("settings_server"),
                                          cfgmod.server_url(self.cfg),
                                          placeholder="http://192.168.0.23:8092", width=420)
        self.server_field.pack(fill="x")

        self.token_field = widgets.Field(card.body, tr("settings_token"),
                                         self.cfg.get("token", ""),
                                         placeholder="paste the token from your server", width=420)
        self.token_field.pack(fill="x", pady=(theme.PAD_S, 0))

        row = ctk.CTkFrame(card.body, fg_color="transparent")
        row.pack(fill="x", pady=(theme.PAD_S, 0))
        self.test_btn = ctk.CTkButton(row, text=tr("wizard_test"), height=36, width=150,
                                      corner_radius=theme.RADIUS_CONTROL,
                                      fg_color=theme.SURFACE_2, hover_color=theme.BORDER,
                                      border_width=1, border_color=theme.BORDER,
                                      font=theme.font(12), command=self._test)
        self.test_btn.pack(side="left")
        self.test_label = ctk.CTkLabel(row, text="", font=theme.font(12),
                                       text_color=theme.TEXT_MUTED, wraplength=260, justify="left")
        self.test_label.pack(side="left", padx=12)

    def _build_dictation(self, parent):
        tr = self.app.tr
        card = widgets.Card(parent, tr("group_dictation"))
        card.pack(fill="x", pady=(0, theme.PAD_S))

        row = ctk.CTkFrame(card.body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text=tr("settings_hotkey"), font=theme.font(12),
                     text_color=theme.TEXT_MUTED).pack(side="left", padx=(0, 12))
        self.keycap = widgets.KeyCap(row, hotkeys_mod.describe_hotkey(self.cfg.get("hotkey")))
        self.keycap.pack(side="left")
        ctk.CTkButton(row, text=tr("settings_hotkey_change"), width=110, height=32,
                      corner_radius=theme.RADIUS_CONTROL, font=theme.font(12),
                      fg_color="transparent", border_width=1, border_color=theme.BORDER,
                      hover_color=theme.SURFACE_2,
                      command=self._change_hotkey).pack(side="left", padx=10)

        mode_row = ctk.CTkFrame(card.body, fg_color="transparent")
        mode_row.pack(fill="x", pady=(theme.PAD, 0))
        ctk.CTkLabel(mode_row, text=tr("settings_mode"), font=theme.font(12),
                     text_color=theme.TEXT_MUTED).pack(anchor="w", pady=(0, 6))
        self.mode_seg = ctk.CTkSegmentedButton(
            mode_row, values=[tr("settings_mode_hold"), tr("settings_mode_toggle")],
            height=34, font=theme.font(12), corner_radius=theme.RADIUS_CONTROL,
            selected_color=theme.ACCENT, selected_hover_color=theme.ACCENT_HOVER,
            unselected_color=theme.SURFACE_2, unselected_hover_color=theme.BORDER)
        self.mode_seg.set(tr("settings_mode_hold") if self.cfg.get("hotkey_mode") == "hold"
                          else tr("settings_mode_toggle"))
        self.mode_seg.pack(anchor="w")

        self.auto_stop_switch = self._switch(card.body, tr("settings_auto_stop"),
                                             self.cfg.get("auto_stop", False),
                                             tr("settings_auto_stop_hint"))

    def _build_ai(self, parent):
        tr = self.app.tr
        card = widgets.Card(parent, tr("group_ai"), tr("group_ai_hint"))
        card.pack(fill="x", pady=(0, theme.PAD_S))

        self.cleanup_switch = self._switch(card.body, tr("settings_cleanup"),
                                           self.cfg.get("cleanup", True))

        lang_row = ctk.CTkFrame(card.body, fg_color="transparent")
        lang_row.pack(fill="x", pady=(theme.PAD, 0))
        ctk.CTkLabel(lang_row, text=tr("settings_language"), font=theme.font(12),
                     text_color=theme.TEXT_MUTED).pack(side="left")
        self.language_menu = ctk.CTkOptionMenu(
            lang_row, values=LANGUAGES, height=32, width=170, font=theme.font(12),
            corner_radius=theme.RADIUS_CONTROL, fg_color=theme.SURFACE_2,
            button_color=theme.SURFACE_2, button_hover_color=theme.BORDER,
            dropdown_fg_color=theme.SURFACE_2, dropdown_hover_color=theme.BORDER)
        self.language_menu.set(self.cfg.get("language", "auto"))
        self.language_menu.pack(side="right")

    def _build_appearance(self, parent):
        tr = self.app.tr
        card = widgets.Card(parent, tr("group_appearance"))
        card.pack(fill="x", pady=(0, theme.PAD_S))

        self.pill_switch = self._switch(card.body, tr("settings_pill"),
                                        self.cfg.get("show_pill", True))

        pos_row = ctk.CTkFrame(card.body, fg_color="transparent")
        pos_row.pack(fill="x", pady=(theme.PAD, 0))
        ctk.CTkLabel(pos_row, text=tr("settings_pill_position"), font=theme.font(12),
                     text_color=theme.TEXT_MUTED).pack(side="left")
        self.positions = {
            tr("position_bottom_center"): "bottom-center",
            tr("position_bottom_right"): "bottom-right",
            tr("position_top_right"): "top-right",
        }
        current = self.cfg.get("pill_position", "bottom-center")
        reverse = {v: k for k, v in self.positions.items()}
        self.position_menu = ctk.CTkOptionMenu(
            pos_row, values=list(self.positions.keys()), height=32, width=170,
            font=theme.font(12), corner_radius=theme.RADIUS_CONTROL,
            fg_color=theme.SURFACE_2, button_color=theme.SURFACE_2,
            button_hover_color=theme.BORDER, dropdown_fg_color=theme.SURFACE_2,
            dropdown_hover_color=theme.BORDER)
        self.position_menu.set(reverse.get(current, list(self.positions)[0]))
        self.position_menu.pack(side="right")

        ui_row = ctk.CTkFrame(card.body, fg_color="transparent")
        ui_row.pack(fill="x", pady=(theme.PAD, 0))
        ctk.CTkLabel(ui_row, text=tr("settings_ui_language"), font=theme.font(12),
                     text_color=theme.TEXT_MUTED).pack(side="left")
        self.ui_language_menu = ctk.CTkOptionMenu(
            ui_row, values=["auto", "en", "es"], height=32, width=170, font=theme.font(12),
            corner_radius=theme.RADIUS_CONTROL, fg_color=theme.SURFACE_2,
            button_color=theme.SURFACE_2, button_hover_color=theme.BORDER,
            dropdown_fg_color=theme.SURFACE_2, dropdown_hover_color=theme.BORDER)
        self.ui_language_menu.set(self.cfg.get("ui_language", "auto"))
        self.ui_language_menu.pack(side="right")

    def _build_system(self, parent):
        tr = self.app.tr
        card = widgets.Card(parent, tr("group_system"))
        card.pack(fill="x", pady=(0, theme.PAD))

        self.startup_switch = self._switch(card.body, tr("settings_startup"),
                                           self.cfg.get("launch_at_login", False))
        self.beeps_switch = self._switch(card.body, tr("settings_beeps"),
                                         self.cfg.get("beeps", True))
        self.clipboard_switch = self._switch(card.body, tr("settings_clipboard"),
                                             self.cfg.get("restore_clipboard", True))
        self.debug_switch = self._switch(card.body, tr("settings_debug"),
                                         self.cfg.get("debug", False))
        ctk.CTkButton(card.body, text=tr("menu_folder"), height=32, font=theme.font(12),
                      corner_radius=theme.RADIUS_CONTROL, fg_color="transparent",
                      border_width=1, border_color=theme.BORDER, hover_color=theme.SURFACE_2,
                      command=self.app.open_config_folder).pack(anchor="w", pady=(theme.PAD_S, 0))

    def _switch(self, parent, text: str, value: bool, hint: str = ""):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=6)
        box = ctk.CTkFrame(row, fg_color="transparent")
        box.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(box, text=text, font=theme.font(12), text_color=theme.TEXT,
                     anchor="w").pack(anchor="w")
        if hint:
            ctk.CTkLabel(box, text=hint, font=theme.font(11), text_color=theme.TEXT_FAINT,
                         anchor="w", justify="left", wraplength=420).pack(anchor="w")
        switch = ctk.CTkSwitch(row, text="", width=44, switch_width=40, switch_height=20,
                               progress_color=theme.ACCENT, fg_color=theme.SURFACE_2)
        switch.pack(side="right")
        switch.select() if value else switch.deselect()
        return switch

    # ----------------------------------------------------------------- status
    def _probe_status(self):
        def run():
            cfg = dict(self.cfg)
            cfgmod.parse_server_url(self.server_field.get(), cfg)
            try:
                health = VozLabAPI(cfgmod.server_url(cfg), self.token_field.get()).health()
                self.app.post(lambda: self._set_status(
                    True, self.app.tr("status_connected", model=health.get("whisper_model", "?"),
                                      device=health.get("device", "?"))))
            except ApiError as e:
                kind = {"unreachable": "err_server_unreachable",
                        "bad_token": "err_bad_token"}.get(e.kind)
                msg = self.app.tr(kind, error=e.detail) if kind else self.app.tr(
                    "err_generic", error=e.detail)
                self.app.post(lambda: self._set_status(False, msg))
        threading.Thread(target=run, daemon=True).start()

    def _set_status(self, ok: bool, message: str) -> None:
        self.status_dot.set_color(theme.OK if ok else theme.ERROR)
        self.status_label.configure(text=message, text_color=theme.TEXT_MUTED)

    # ---------------------------------------------------------------- actions
    def _test(self):
        self.test_label.configure(text="…", text_color=theme.TEXT_MUTED)
        self.test_btn.configure(state="disabled")

        def run():
            cfg = dict(self.cfg)
            cfgmod.parse_server_url(self.server_field.get(), cfg)
            try:
                health = VozLabAPI(cfgmod.server_url(cfg), self.token_field.get()).health()
                msg = self.app.tr("wizard_test_ok", model=health.get("whisper_model", "?"),
                                  device=health.get("device", "?"))
                color = theme.OK
            except ApiError as e:
                kind = {"unreachable": "err_server_unreachable",
                        "bad_token": "err_bad_token"}.get(e.kind)
                msg = self.app.tr(kind, error=e.detail) if kind else self.app.tr(
                    "err_generic", error=e.detail)
                color = theme.ERROR

            def done():
                self.test_label.configure(text=msg, text_color=color)
                self.test_btn.configure(state="normal")
                self._set_status(color == theme.OK, msg)
            self.app.post(done)

        threading.Thread(target=run, daemon=True).start()

    def _change_hotkey(self):
        def captured(code, name):
            self.cfg["hotkey"] = code
            self.keycap.set_text(name or str(code))
        HotkeyCaptureDialog(self.app, captured)

    def _save(self):
        cfg = dict(self.cfg)
        cfgmod.parse_server_url(self.server_field.get(), cfg)
        cfg["token"] = self.token_field.get()
        cfg["hotkey_mode"] = ("hold" if self.mode_seg.get() == self.app.tr("settings_mode_hold")
                              else "toggle")
        cfg["auto_stop"] = bool(self.auto_stop_switch.get())
        cfg["cleanup"] = bool(self.cleanup_switch.get())
        cfg["language"] = self.language_menu.get()
        cfg["show_pill"] = bool(self.pill_switch.get())
        cfg["pill_position"] = self.positions.get(self.position_menu.get(), "bottom-center")
        cfg["ui_language"] = self.ui_language_menu.get()
        cfg["launch_at_login"] = bool(self.startup_switch.get())
        cfg["beeps"] = bool(self.beeps_switch.get())
        cfg["restore_clipboard"] = bool(self.clipboard_switch.get())
        cfg["debug"] = bool(self.debug_switch.get())
        cfg["calibrate"] = False
        cfg["first_run_done"] = True

        self.app.apply_config(cfg)
        self.win.destroy()
        if self.on_saved:
            self.on_saved()
