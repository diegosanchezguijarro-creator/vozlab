"""Settings window — six tabs, everything in one place.

Dictation · Audio · Formatting · Server · Appearance · System

The **Server** tab is the unified-settings part: models, language and cleanup
are changed on the remote server through the API (`PATCH /settings`), so a user
never needs SSH or a container restart.
"""

import json
import os
import socket
import threading
import time
import webbrowser

import customtkinter as ctk

from .. import DISPLAY_NAME, VERSION
from .. import audio, config as cfgmod, diagnostics, log
from .. import hotkeys as hotkeys_mod
from ..api import ApiError, VozLabAPI
from . import theme, widgets

LANGUAGES = ["auto", "en", "es", "fr", "de", "it", "pt", "nl", "ru", "ja", "zh",
             "ko", "ar", "hi", "tr", "pl", "sv"]


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
        self.dirty = False
        self.server_status: dict | None = None
        tr = app.tr

        self.win = ctk.CTkToplevel(app.root)
        self.win.title(tr("settings_title"))
        self.win.geometry("760x760")
        self.win.minsize(720, 600)

        # ------------------------------------------------------------------ head
        head = ctk.CTkFrame(self.win, fg_color="transparent")
        head.pack(fill="x", padx=theme.PAD_L, pady=(theme.PAD_L, theme.PAD_S))

        left = ctk.CTkFrame(head, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text=DISPLAY_NAME, font=theme.font(22, "bold")).pack(anchor="w")
        ctk.CTkLabel(left, text=f"v{VERSION} · 100% local", font=theme.font(12),
                     text_color=theme.TEXT_MUTED).pack(anchor="w")

        right = ctk.CTkFrame(head, fg_color="transparent")
        right.pack(side="right")
        status = ctk.CTkFrame(right, fg_color="transparent")
        status.pack(side="right")
        self.status_dot = widgets.StatusDot(status, theme.TEXT_FAINT)
        self.status_dot.pack(side="left", padx=(0, 8))
        self.status_label = ctk.CTkLabel(status, text=tr("status_unknown"),
                                         font=theme.font(12), text_color=theme.TEXT_MUTED)
        self.status_label.pack(side="left")

        # ------------------------------------------------------------------ tabs
        self.tabs = ctk.CTkTabview(
            self.win, fg_color=theme.SURFACE, segmented_button_fg_color=theme.SURFACE_2,
            segmented_button_selected_color=theme.ACCENT,
            segmented_button_selected_hover_color=theme.ACCENT_HOVER,
            segmented_button_unselected_color=theme.SURFACE_2,
            segmented_button_unselected_hover_color=theme.BORDER,
            corner_radius=theme.RADIUS_CARD, border_width=1, border_color=theme.BORDER,
            text_color=theme.TEXT)
        self.tabs.pack(fill="both", expand=True, padx=theme.PAD_L, pady=0)

        for key in ("tab_dictation", "tab_audio", "tab_formatting", "tab_server",
                    "tab_appearance", "tab_system"):
            self.tabs.add(tr(key))

        self._scrolls = {}
        self._build_dictation(self._tab("tab_dictation"))
        self._build_audio(self._tab("tab_audio"))
        self._build_formatting(self._tab("tab_formatting"))
        self._build_server(self._tab("tab_server"))
        self._build_appearance(self._tab("tab_appearance"))
        self._build_system(self._tab("tab_system"))

        # ---------------------------------------------------------------- footer
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

        self.dirty_label = ctk.CTkLabel(footer, text="", font=theme.font(11),
                                        text_color=theme.WARN)
        self.dirty_label.pack(side="left")

        self._probe_status()

    # ------------------------------------------------------------------ helpers
    def _tab(self, key: str) -> ctk.CTkScrollableFrame:
        """A scrollable body inside one tab (content can be taller than the tab)."""
        scroll = ctk.CTkScrollableFrame(self.tabs.tab(self.app.tr(key)),
                                        fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=2, pady=2)
        self._scrolls[key] = scroll
        return scroll

    def _switch(self, parent, text: str, value: bool, hint: str = ""):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=6)
        box = ctk.CTkFrame(row, fg_color="transparent")
        box.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(box, text=text, font=theme.font(12), text_color=theme.TEXT,
                     anchor="w").pack(anchor="w")
        if hint:
            ctk.CTkLabel(box, text=hint, font=theme.font(11), text_color=theme.TEXT_FAINT,
                         anchor="w", justify="left", wraplength=430).pack(anchor="w")
        switch = ctk.CTkSwitch(row, text="", width=44, switch_width=40, switch_height=20,
                               progress_color=theme.ACCENT, fg_color=theme.SURFACE_2,
                               command=self._mark_dirty)
        switch.pack(side="right")
        switch.select() if value else switch.deselect()
        return switch

    def _option_row(self, parent, label: str, values: list, current: str, width: int = 190):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(theme.PAD_S, 0))
        ctk.CTkLabel(row, text=label, font=theme.font(12),
                     text_color=theme.TEXT_MUTED).pack(side="left")
        menu = ctk.CTkOptionMenu(
            row, values=values, height=32, width=width, font=theme.font(12),
            corner_radius=theme.RADIUS_CONTROL, fg_color=theme.SURFACE_2,
            button_color=theme.SURFACE_2, button_hover_color=theme.BORDER,
            dropdown_fg_color=theme.SURFACE_2, dropdown_hover_color=theme.BORDER,
            command=lambda _v: self._mark_dirty())
        menu.set(current if current in values else values[0])
        menu.pack(side="right")
        return menu

    def _number_row(self, parent, label: str, key: str, value, width: int = 110,
                    is_float: bool = False):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(theme.PAD_S, 0))
        ctk.CTkLabel(row, text=label, font=theme.font(12), text_color=theme.TEXT_MUTED,
                     wraplength=470, justify="left").pack(side="left")
        var = ctk.StringVar(value=str(value))
        var.trace_add("write", lambda *_: self._mark_dirty())
        entry = ctk.CTkEntry(row, textvariable=var, width=width, height=32,
                             font=theme.font(12), corner_radius=theme.RADIUS_CONTROL,
                             fg_color=theme.SURFACE_2, border_color=theme.BORDER,
                             border_width=1, text_color=theme.TEXT)
        entry.pack(side="right")
        entry._is_float = is_float          # read back in _save
        entry._var = var
        return entry

    def _mark_dirty(self, *_args):
        self.dirty = True
        try:
            self.dirty_label.configure(text=self.app.tr("settings_unsaved"))
        except Exception:
            pass

    def _button(self, parent, text: str, command, width: int = 150, accent: bool = False):
        btn = ctk.CTkButton(
            parent, text=text, height=32, width=width, font=theme.font(12),
            corner_radius=theme.RADIUS_CONTROL,
            fg_color=theme.ACCENT if accent else "transparent",
            hover_color=theme.ACCENT_HOVER if accent else theme.SURFACE_2,
            border_width=0 if accent else 1,
            border_color=theme.BORDER, command=command)
        return btn

    def _new_api(self) -> VozLabAPI:
        cfg = dict(self.cfg)
        cfgmod.parse_server_url(self.server_field.get(), cfg)
        return VozLabAPI(cfgmod.server_url(cfg), self.token_field.get())

    # -------------------------------------------------------------- dictation --
    def _build_dictation(self, parent):
        tr = self.app.tr
        card = widgets.Card(parent, tr("group_dictation"), tr("settings_dictation_hint"))
        card.pack(fill="x", pady=(0, theme.PAD_S))

        row = ctk.CTkFrame(card.body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text=tr("settings_hotkey"), font=theme.font(12),
                     text_color=theme.TEXT_MUTED).pack(side="left", padx=(0, 12))
        self.keycap = widgets.KeyCap(row, hotkeys_mod.describe_hotkey(self.cfg.get("hotkey")))
        self.keycap.pack(side="left")
        self._button(row, tr("settings_hotkey_change"), self._change_hotkey, 120).pack(
            side="left", padx=10)

        self.mode_seg = ctk.CTkSegmentedButton(
            card.body, values=[tr("settings_mode_hold"), tr("settings_mode_toggle")],
            height=34, font=theme.font(12), corner_radius=theme.RADIUS_CONTROL,
            selected_color=theme.ACCENT, selected_hover_color=theme.ACCENT_HOVER,
            unselected_color=theme.SURFACE_2, unselected_hover_color=theme.BORDER,
            command=lambda _v: self._mark_dirty())
        self.mode_seg.set(tr("settings_mode_hold") if self.cfg.get("hotkey_mode") == "hold"
                          else tr("settings_mode_toggle"))
        self.mode_seg.pack(anchor="w", pady=(theme.PAD, 0))

        self.auto_stop_switch = self._switch(card.body, tr("settings_auto_stop"),
                                             self.cfg.get("auto_stop", False),
                                             tr("settings_auto_stop_hint"))

        lang_card = widgets.Card(parent, tr("settings_language"), tr("settings_language_hint"))
        lang_card.pack(fill="x", pady=(0, theme.PAD_S))
        self.language_menu = self._option_row(lang_card.body, "", LANGUAGES,
                                              self.cfg.get("language", "auto"), width=190)

    # ------------------------------------------------------------------ audio --
    def _build_audio(self, parent):
        tr = self.app.tr
        card = widgets.Card(parent, tr("group_audio"), tr("group_audio_hint"))
        card.pack(fill="x", pady=(0, theme.PAD_S))

        self.device_names = [tr("settings_device_default")]
        self._device_map = {self.device_names[0]: None}
        for dev in audio.list_input_devices():
            label = f"{dev['name']} ({dev['channels']}ch)"
            if dev["default"]:
                label += " · default"
            self.device_names.append(label)
            self._device_map[label] = dev["name"]
        saved = self.cfg.get("input_device")
        current = next((k for k, v in self._device_map.items() if v == saved),
                       self.device_names[0])
        self.device_menu = self._option_row(card.body, tr("settings_input_device"),
                                            self.device_names, current, width=330)

        level_row = ctk.CTkFrame(card.body, fg_color="transparent")
        level_row.pack(fill="x", pady=(theme.PAD, 0))
        ctk.CTkLabel(level_row, text=tr("settings_audio_level"), font=theme.font(12),
                     text_color=theme.TEXT_MUTED).pack(side="left")
        self.level_bar = ctk.CTkProgressBar(
            level_row, height=10, corner_radius=5, progress_color=theme.ACCENT,
            fg_color=theme.SURFACE_2, width=300)
        self.level_bar.set(0)
        self.level_bar.pack(side="right")

        test_row = ctk.CTkFrame(card.body, fg_color="transparent")
        test_row.pack(fill="x", pady=(theme.PAD_S, 0))
        self.mic_btn = self._button(test_row, tr("settings_test_mic"), self._test_mic, 160)
        self.mic_btn.pack(side="left")
        self.mic_label = ctk.CTkLabel(test_row, text=tr("settings_test_mic_hint"),
                                      font=theme.font(11), text_color=theme.TEXT_FAINT,
                                      wraplength=380, justify="left")
        self.mic_label.pack(side="left", padx=10)

        tune = widgets.Card(parent, tr("settings_auto_stop"))
        tune.pack(fill="x", pady=(0, theme.PAD_S))
        self.silence_ms_entry = self._number_row(tune.body, tr("settings_silence_ms"),
                                                 "silence_ms", self.cfg.get("silence_ms", 1200))
        self.silence_rms_entry = self._number_row(tune.body, tr("settings_silence_rms"),
                                                  "silence_rms",
                                                  self.cfg.get("silence_rms", 0.012),
                                                  is_float=True)
        self.min_seconds_entry = self._number_row(tune.body, tr("settings_min_seconds"),
                                                  "min_seconds",
                                                  self.cfg.get("min_seconds", 0.4),
                                                  is_float=True)
        self.max_seconds_entry = self._number_row(tune.body, tr("settings_max_seconds"),
                                                  "max_seconds",
                                                  self.cfg.get("max_seconds", 60),
                                                  is_float=True)

    # ------------------------------------------------------------ formatting --
    def _build_formatting(self, parent):
        tr = self.app.tr
        card = widgets.Card(parent, tr("group_ai"), tr("group_ai_hint"))
        card.pack(fill="x", pady=(0, theme.PAD_S))

        self.cleanup_switch = self._switch(card.body, tr("settings_cleanup"),
                                           self.cfg.get("cleanup", True))
        self.cleanup_guard_switch = self._switch(card.body, tr("settings_cleanup_guard"),
                                                 self.cfg.get("cleanup_guard", True),
                                                 tr("settings_cleanup_guard_hint"))

        self.style_names = {
            tr("style_default"): "default",
            tr("style_formal"): "formal",
            tr("style_casual"): "casual",
            tr("style_concise"): "concise",
            tr("style_bullets"): "bullets",
        }
        style_reverse = {v: k for k, v in self.style_names.items()}
        self.style_menu = self._option_row(
            card.body, tr("settings_style"), list(self.style_names),
            style_reverse.get(self.cfg.get("style", "default"), list(self.style_names)[0]),
            width=200)
        ctk.CTkLabel(card.body, text=tr("settings_style_hint"), font=theme.font(11),
                     text_color=theme.TEXT_FAINT, justify="left", wraplength=470).pack(anchor="w")

        # --- per-app profiles ------------------------------------------------
        profiles_card = widgets.Card(parent, tr("group_profiles"), tr("group_profiles_hint"))
        profiles_card.pack(fill="x", pady=(0, theme.PAD_S))
        self.per_app_switch = self._switch(profiles_card.body, tr("settings_per_app"),
                                           self.cfg.get("per_app_profiles", True))

        self._profile_rules = dict(cfgmod.profiles_map(self.cfg))
        self.rules_box = ctk.CTkFrame(profiles_card.body, fg_color="transparent")
        self.rules_box.pack(fill="x", pady=(theme.PAD_S, 0))

        add_row = ctk.CTkFrame(profiles_card.body, fg_color="transparent")
        add_row.pack(fill="x", pady=(theme.PAD_S, 0))
        self.app_var = ctk.StringVar(value="")
        ctk.CTkEntry(add_row, textvariable=self.app_var, width=170, height=32,
                     placeholder_text="slack.exe", font=theme.font(12),
                     corner_radius=theme.RADIUS_CONTROL, fg_color=theme.SURFACE_2,
                     border_color=theme.BORDER, border_width=1,
                     text_color=theme.TEXT).pack(side="left")
        self.new_style = ctk.CTkOptionMenu(
            add_row, values=list(self.style_names), height=32, width=140,
            font=theme.font(12), corner_radius=theme.RADIUS_CONTROL,
            fg_color=theme.SURFACE_2, button_color=theme.SURFACE_2,
            button_hover_color=theme.BORDER, dropdown_fg_color=theme.SURFACE_2,
            dropdown_hover_color=theme.BORDER)
        self.new_style.set(tr("style_default"))
        self.new_style.pack(side="left", padx=8)
        self._button(add_row, tr("settings_add_rule"), self._add_rule, 110).pack(side="left")
        self._button(add_row, tr("settings_use_current_app"),
                     self._use_current_app, 190).pack(side="left", padx=8)
        self.rules_label = ctk.CTkLabel(profiles_card.body, text="", font=theme.font(11),
                                        text_color=theme.TEXT_MUTED, wraplength=470,
                                        justify="left")
        self.rules_label.pack(anchor="w", pady=(6, 0))
        self._render_rules()

        # --- custom vocabulary ----------------------------------------------
        vocab_card = widgets.Card(parent, tr("group_vocabulary"), tr("group_vocabulary_hint"))
        vocab_card.pack(fill="x", pady=(0, theme.PAD_S))
        self.vocab_box = ctk.CTkTextbox(vocab_card.body, height=80, font=theme.font(12),
                                        fg_color=theme.SURFACE_2,
                                        border_color=theme.BORDER, border_width=1,
                                        text_color=theme.TEXT)
        self.vocab_box.pack(fill="x")
        self.vocab_box.insert("1.0", ", ".join(self.cfg.get("vocabulary") or []))
        vocab_row = ctk.CTkFrame(vocab_card.body, fg_color="transparent")
        vocab_row.pack(fill="x", pady=(theme.PAD_S, 0))
        self._button(vocab_row, tr("settings_save_vocabulary"),
                     self._save_vocabulary, 190, accent=True).pack(side="left")
        self.vocab_label = ctk.CTkLabel(vocab_row, text="", font=theme.font(11),
                                        text_color=theme.TEXT_MUTED, wraplength=330,
                                        justify="left")
        self.vocab_label.pack(side="left", padx=10)

    def _render_rules(self):
        for child in self.rules_box.winfo_children():
            child.destroy()
        tr = self.app.tr
        reverse = {v: k for k, v in self.style_names.items()}
        if not self._profile_rules:
            ctk.CTkLabel(self.rules_box, text=tr("settings_no_rules"),
                         font=theme.font(11), text_color=theme.TEXT_FAINT).pack(anchor="w")
            return
        for app, style in sorted(self._profile_rules.items()):
            row = ctk.CTkFrame(self.rules_box, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=f"{app}  →  {reverse.get(style, style)}",
                         font=theme.font(11), text_color=theme.TEXT_MUTED).pack(side="left")
            self._button(row, tr("settings_remove"), lambda a=app: self._remove_rule(a),
                         90).pack(side="right")

    def _add_rule(self):
        app = self.app_var.get().strip()
        if not app:
            return
        self._profile_rules[app] = self.style_names.get(self.new_style.get(), "default")
        self.app_var.set("")
        self._render_rules()
        self._mark_dirty()

    def _remove_rule(self, app: str):
        self._profile_rules.pop(app, None)
        self._render_rules()
        self._mark_dirty()

    def _use_current_app(self):
        """Create a rule for the window that has focus right now."""
        from .. import foreground
        tr = self.app.tr
        app = foreground.foreground_app()
        if not app:
            self.rules_label.configure(text=tr("settings_no_foreground"),
                                       text_color=theme.WARN)
            return
        self.app_var.set(app)
        self.rules_label.configure(text=tr("settings_detected_app", app=app),
                                   text_color=theme.OK)

    def _save_vocabulary(self):
        """Send the term list to the server (it biases Whisper and the formatter)."""
        tr = self.app.tr
        terms = [t.strip() for t in self.vocab_box.get("1.0", "end")
                 .replace(";", ",").split(",") if t.strip()]
        self.cfg["vocabulary"] = terms
        self.vocab_label.configure(text=tr("settings_vocabulary_saving"),
                                   text_color=theme.TEXT_MUTED)
        api = self._new_api()

        def run():
            try:
                out = api.patch_settings({"vocabulary": terms})
                saved = out.get("applied", {}).get("vocabulary", terms)
                msg, color = tr("settings_vocabulary_saved", count=len(saved)), theme.OK
            except ApiError as e:
                msg, color = tr("settings_vocabulary_local", error=e.detail), theme.WARN
            self.app.post(lambda: self.vocab_label.configure(text=msg, text_color=color))

        threading.Thread(target=run, daemon=True).start()
        self._mark_dirty()

    # ---------------------------------------------------------------- server --
    def _build_server(self, parent):
        tr = self.app.tr

        conn = widgets.Card(parent, tr("group_connection"), tr("group_connection_hint"))
        conn.pack(fill="x", pady=(0, theme.PAD_S))

        self.server_field = widgets.Field(conn.body, tr("settings_server"),
                                          cfgmod.server_url(self.cfg),
                                          placeholder="http://192.168.0.23:8092", width=420)
        self.server_field.pack(fill="x")
        self.token_field = widgets.Field(conn.body, tr("settings_token"),
                                         self.cfg.get("token", ""),
                                         placeholder="paste the token from your server",
                                         width=420)
        self.token_field.pack(fill="x", pady=(theme.PAD_S, 0))
        if self.cfg.get("token_encrypted"):
            ctk.CTkLabel(conn.body, text="🔒 encrypted with Windows DPAPI",
                         font=theme.font(11), text_color=theme.OK).pack(anchor="w", pady=(4, 0))

        row = ctk.CTkFrame(conn.body, fg_color="transparent")
        row.pack(fill="x", pady=(theme.PAD_S, 0))
        self._button(row, tr("wizard_find_server"), self._find_servers, 160).pack(side="left")
        self._button(row, tr("wizard_test"), self._test, 140).pack(side="left", padx=8)
        self.test_label = ctk.CTkLabel(row, text="", font=theme.font(12),
                                       text_color=theme.TEXT_MUTED, wraplength=360,
                                       justify="left")
        self.test_label.pack(side="left", padx=4)

        # created lazily: an empty CTkFrame keeps its default 200px height
        self.found_box = ctk.CTkFrame(conn.body, fg_color="transparent")

        # --- certificate pinning --------------------------------------------
        self.pin_card = ctk.CTkFrame(conn.body, fg_color=theme.SURFACE_2,
                                     corner_radius=theme.RADIUS_CONTROL,
                                     border_width=1, border_color=theme.BORDER)
        self.pin_label = ctk.CTkLabel(self.pin_card, text="", font=theme.font(11),
                                      text_color=theme.TEXT_MUTED, justify="left",
                                      wraplength=420, anchor="w")
        self.pin_label.pack(anchor="w", padx=12, pady=(10, 6))
        pin_row = ctk.CTkFrame(self.pin_card, fg_color="transparent")
        pin_row.pack(anchor="w", padx=12, pady=(0, 10))
        self._button(pin_row, tr("settings_repin"), self._repin, 150).pack(side="left")
        self._button(pin_row, tr("settings_forget_cert"), self._forget_pin, 170).pack(
            side="left", padx=8)
        self._render_pin()

        # --- remote settings ---------------------------------------------------
        remote = widgets.Card(parent, tr("group_server"), tr("group_server_hint"))
        remote.pack(fill="x", pady=(0, theme.PAD_S))

        self.server_model_menu = self._option_row(
            remote.body, tr("settings_server_model"), [self.cfg.get("whisper_model") or "small"],
            self.cfg.get("whisper_model") or "small", width=220)
        ctk.CTkLabel(remote.body, text=tr("settings_server_model_hint"), font=theme.font(11),
                     text_color=theme.TEXT_FAINT, justify="left", wraplength=470).pack(anchor="w")
        self.server_language_menu = self._option_row(
            remote.body, tr("settings_server_language"), LANGUAGES,
            self.cfg.get("language", "auto"), width=220)
        self.server_cleanup_switch = self._switch(remote.body, tr("settings_cleanup"),
                                                  self.cfg.get("cleanup", True))
        self.cleanup_model_menu = self._option_row(
            remote.body, tr("settings_cleanup_model"),
            [self.cfg.get("cleanup_model") or "qwen2.5:7b-instruct"],
            self.cfg.get("cleanup_model") or "qwen2.5:7b-instruct", width=260)

        btn_row = ctk.CTkFrame(remote.body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(theme.PAD, 0))
        self.apply_btn = self._button(btn_row, tr("settings_apply_server"),
                                      self._apply_server_settings, 170, accent=True)
        self.apply_btn.pack(side="left")
        self.preload_btn = self._button(btn_row, tr("settings_preload"),
                                        self._preload, 160)
        self.preload_btn.pack(side="left", padx=8)
        self.selftest_btn = self._button(btn_row, tr("settings_self_test"),
                                        self._self_test, 150)
        self.selftest_btn.pack(side="left")
        self.remote_label = ctk.CTkLabel(remote.body, text="", font=theme.font(11),
                                         text_color=theme.TEXT_MUTED, wraplength=470,
                                         justify="left")
        self.remote_label.pack(anchor="w", pady=(8, 0))

        self.server_info = ctk.CTkLabel(remote.body, text="", font=theme.font(11),
                                        text_color=theme.TEXT_FAINT, wraplength=470,
                                        justify="left")
        self.server_info.pack(anchor="w", pady=(6, 0))

        # --- devices -----------------------------------------------------------
        self._build_devices(parent)

        # --- server logs -------------------------------------------------------
        logs_card = widgets.Card(parent, tr("settings_server_logs"))
        logs_card.pack(fill="x", pady=(0, theme.PAD))
        self.server_logs = ctk.CTkTextbox(logs_card.body, height=150, font=theme.font(11),
                                          fg_color=theme.SURFACE_2,
                                          border_color=theme.BORDER, border_width=1,
                                          text_color=theme.TEXT_MUTED)
        self.server_logs.pack(fill="x")
        self.server_logs.configure(state="disabled")
        self._button(logs_card.body, tr("settings_refresh"), self._load_server_logs,
                     130).pack(anchor="w", pady=(theme.PAD_S, 0))

    def _build_devices(self, parent):
        tr = self.app.tr
        card = widgets.Card(parent, tr("group_devices"), tr("group_devices_hint"))
        card.pack(fill="x", pady=(0, theme.PAD_S))

        self.devices_box = ctk.CTkFrame(card.body, fg_color="transparent")
        self.devices_box.pack(fill="x")
        self.devices_label = ctk.CTkLabel(self.devices_box, text="…", font=theme.font(11),
                                          text_color=theme.TEXT_FAINT)
        self.devices_label.pack(anchor="w")

        name_row = ctk.CTkFrame(card.body, fg_color="transparent")
        name_row.pack(fill="x", pady=(theme.PAD_S, 0))
        ctk.CTkLabel(name_row, text=tr("settings_device_name"), font=theme.font(12),
                     text_color=theme.TEXT_MUTED).pack(side="left", padx=(0, 10))
        default_name = self.cfg.get("device_name") or socket.gethostname()[:40]
        self.device_name_var = ctk.StringVar(value=default_name)
        ctk.CTkEntry(name_row, textvariable=self.device_name_var, width=220, height=32,
                     font=theme.font(12), corner_radius=theme.RADIUS_CONTROL,
                     fg_color=theme.SURFACE_2, border_color=theme.BORDER, border_width=1,
                     text_color=theme.TEXT).pack(side="left")
        self._button(name_row, tr("settings_issue_token"), self._issue_token, 220).pack(
            side="left", padx=10)

        self.token_box = ctk.CTkTextbox(card.body, height=44, font=theme.font(11, "bold"),
                                        fg_color=theme.SURFACE_2, border_color=theme.OK,
                                        border_width=1, text_color=theme.TEXT)
        self.token_box.pack(fill="x", pady=(theme.PAD_S, 0))
        self.token_box.insert("1.0", "")
        self.token_box.configure(state="disabled")

    # ------------------------------------------------------------ appearance --
    def _build_appearance(self, parent):
        tr = self.app.tr
        card = widgets.Card(parent, tr("group_appearance"))
        card.pack(fill="x", pady=(0, theme.PAD_S))

        self.themes = {tr("theme_dark"): "dark", tr("theme_light"): "light",
                       tr("theme_system"): "system"}
        reverse = {v: k for k, v in self.themes.items()}
        self.theme_menu = self._option_row(
            card.body, tr("settings_theme"), list(self.themes),
            reverse.get(self.cfg.get("theme", "dark"), tr("theme_dark")), width=190)

        self.pill_switch = self._switch(card.body, tr("settings_pill"),
                                        self.cfg.get("show_pill", True))

        self.positions = {
            tr("position_bottom_center"): "bottom-center",
            tr("position_bottom_right"): "bottom-right",
            tr("position_top_right"): "top-right",
        }
        pos_reverse = {v: k for k, v in self.positions.items()}
        self.position_menu = self._option_row(
            card.body, tr("settings_pill_position"), list(self.positions),
            pos_reverse.get(self.cfg.get("pill_position", "bottom-center"),
                            list(self.positions)[0]), width=190)

        self.styles = {tr("pill_full"): "full", tr("pill_minimal"): "minimal"}
        style_reverse = {v: k for k, v in self.styles.items()}
        self.style_menu = self._option_row(
            card.body, tr("settings_pill_style"), list(self.styles),
            style_reverse.get(self.cfg.get("pill_style", "full"), tr("pill_full")), width=190)

        ui_card = widgets.Card(parent, tr("settings_ui_language"))
        ui_card.pack(fill="x", pady=(0, theme.PAD_S))
        self.ui_language_menu = self._option_row(ui_card.body, "", ["auto", "en", "es"],
                                                 self.cfg.get("ui_language", "auto"),
                                                 width=190)
        self.beeps_switch = self._switch(ui_card.body, tr("settings_beeps"),
                                         self.cfg.get("beeps", False),
                                         tr("settings_beeps_hint"))

    # ---------------------------------------------------------------- system --
    def _build_system(self, parent):
        tr = self.app.tr
        card = widgets.Card(parent, tr("group_system"), tr("settings_privacy_note"))
        card.pack(fill="x", pady=(0, theme.PAD_S))

        self.startup_switch = self._switch(card.body, tr("settings_startup"),
                                           self.cfg.get("launch_at_login", False))
        self.clipboard_switch = self._switch(card.body, tr("settings_clipboard"),
                                             self.cfg.get("restore_clipboard", True))
        self.debug_switch = self._switch(card.body, tr("settings_debug"),
                                         self.cfg.get("debug", False))

        self.check_updates_switch = self._switch(card.body, tr("settings_check_updates"),
                                                 self.cfg.get("check_updates", False),
                                                 tr("settings_check_updates_hint"))
        update_row = ctk.CTkFrame(card.body, fg_color="transparent")
        update_row.pack(fill="x", pady=(theme.PAD_S, 0))
        self._button(update_row, tr("settings_check_now"), self._check_updates, 130).pack(
            side="left")
        if self.app.updater_script():
            self._button(update_row, tr("settings_update_now"),
                         self.app.run_updater, 130, accent=True).pack(side="left", padx=8)
        self.update_label = ctk.CTkLabel(update_row, text="", font=theme.font(12),
                                         text_color=theme.TEXT_MUTED, wraplength=240,
                                         justify="left")
        self.update_label.pack(side="left", padx=8)

        # --- logs --------------------------------------------------------------
        logs = widgets.Card(parent, tr("settings_logs"))
        logs.pack(fill="x", pady=(0, theme.PAD_S))
        self.client_logs = ctk.CTkTextbox(logs.body, height=140, font=theme.font(11),
                                          fg_color=theme.SURFACE_2,
                                          border_color=theme.BORDER, border_width=1,
                                          text_color=theme.TEXT_MUTED)
        self.client_logs.pack(fill="x")
        self.client_logs.configure(state="disabled")
        log_row = ctk.CTkFrame(logs.body, fg_color="transparent")
        log_row.pack(fill="x", pady=(theme.PAD_S, 0))
        self._button(log_row, tr("settings_show_logs"), self._load_client_logs, 130).pack(
            side="left")
        self._button(log_row, tr("settings_clear_logs"), self._clear_logs, 130).pack(
            side="left", padx=8)
        self._button(log_row, tr("menu_folder"), self.app.open_config_folder, 150).pack(
            side="left")
        self.logs_label = ctk.CTkLabel(log_row, text="", font=theme.font(11),
                                       text_color=theme.TEXT_MUTED)
        self.logs_label.pack(side="left", padx=8)

        # --- import / export / reset ------------------------------------------
        data_card = widgets.Card(parent, tr("settings_save"))
        data_card.pack(fill="x", pady=(0, theme.PAD_S))
        data_row = ctk.CTkFrame(data_card.body, fg_color="transparent")
        data_row.pack(fill="x")
        self._button(data_row, tr("settings_export"), self._export_settings, 150).pack(
            side="left")
        self._button(data_row, tr("settings_import"), self._import_settings, 150).pack(
            side="left", padx=8)
        self._button(data_row, tr("settings_reset"), self._reset_settings, 170).pack(side="left")
        self.data_label = ctk.CTkLabel(data_card.body, text="", font=theme.font(11),
                                       text_color=theme.TEXT_MUTED, wraplength=470,
                                       justify="left")
        self.data_label.pack(anchor="w", pady=(6, 0))

        # --- help --------------------------------------------------------------
        help_card = widgets.Card(parent, tr("settings_help"))
        help_card.pack(fill="x", pady=(0, theme.PAD))
        help_row = ctk.CTkFrame(help_card.body, fg_color="transparent")
        help_row.pack(fill="x")
        self._button(help_row, tr("settings_diagnostics"), self._export_diagnostics, 150).pack(
            side="left")
        self._button(help_row, tr("settings_report_issue"),
                     lambda: webbrowser.open(diagnostics.ISSUE_URL), 150).pack(side="left", padx=8)
        self._button(help_row, tr("settings_help"),
                     lambda: webbrowser.open(diagnostics.DOCS_URL), 110).pack(side="left")
        self.diag_label = ctk.CTkLabel(help_card.body, text="", font=theme.font(11),
                                       text_color=theme.TEXT_MUTED, wraplength=470,
                                       justify="left")
        self.diag_label.pack(anchor="w", pady=(6, 0))

        self._show_last_update()
        self.app.update_reporter = self._show_last_update

    # ----------------------------------------------------------- status/probe --
    def _probe_status(self):
        def run():
            try:
                status = self._new_api().status()
            except ApiError as e:
                if e.kind == "bad_token":
                    # do NOT fall back to /health here: it would report "connected"
                    # while the server is actually rejecting our token
                    msg = self.app.tr("err_bad_token", error=e.detail)
                    self.app.post(lambda: self._set_status(False, msg))
                    return
                try:
                    health = self._new_api().health()      # older server, no /status
                    status = {"version": health.get("version")}
                except ApiError as e2:
                    kind = {"unreachable": "err_server_unreachable",
                            "bad_token": "err_bad_token"}.get(e2.kind)
                    msg = self.app.tr(kind, error=e2.detail) if kind else self.app.tr(
                        "err_generic", error=e2.detail)
                    self.app.post(lambda: self._set_status(False, msg))
                    return
            self.app.post(lambda: self._apply_status(status))

        threading.Thread(target=run, daemon=True).start()

    def _set_status(self, ok: bool, message: str) -> None:
        self.status_dot.set_color(theme.OK if ok else theme.ERROR)
        self.status_label.configure(text=message, text_color=theme.TEXT_MUTED)

    def _apply_status(self, status: dict) -> None:
        """Fill the Server tab from a live /status response."""
        self.server_status = status
        model = status.get("whisper_model") or "?"
        device = status.get("device") or "?"
        self._set_status(True, self.app.tr("status_connected", model=model, device=device))

        # model lists
        whisper_models = sorted(set(status.get("whisper_models_cached") or [])
                                | {status.get("whisper_model") or "small", "tiny", "base",
                                   "small", "medium", "large-v3", "small.en", "base.en"})
        current = status.get("whisper_model") or "small"
        try:
            self.server_model_menu.configure(values=whisper_models)
            self.server_model_menu.set(current)
        except Exception:
            pass

        cleanup_models = status.get("ollama_models") or []
        if cleanup_models:
            try:
                current_cleanup = status.get("cleanup_model") or cleanup_models[0]
                self.cleanup_model_menu.configure(values=cleanup_models)
                self.cleanup_model_menu.set(current_cleanup)
            except Exception:
                pass

        if status.get("language"):
            self.server_language_menu.set(status["language"])
            self.language_menu.set(status["language"])

        if "cleanup" in status:
            self.server_cleanup_switch.select() if status["cleanup"] \
                else self.server_cleanup_switch.deselect()

        gpu = status.get("gpu") or {}
        bits = []
        if gpu.get("name"):
            bits.append(f"{gpu['name']} · {gpu.get('memory_used_mb', '?')}/"
                        f"{gpu.get('memory_total_mb', '?')} MB")
        if status.get("uptime_s") is not None:
            bits.append(self.app.tr("settings_uptime",
                                    minutes=max(1, status["uptime_s"] // 60)))
        if status.get("requests") is not None:
            bits.append(self.app.tr("settings_requests", count=status["requests"]))
        auth = status.get("auth") or {}
        if auth.get("role") == "admin":
            bits.append(self.app.tr("settings_connected_as",
                                    role=self.app.tr("settings_auth_admin")))
        elif auth.get("role") == "device":
            bits.append(self.app.tr("settings_connected_as",
                                    role=self.app.tr("settings_auth_device",
                                                     name=auth.get("device") or "?")))
        if status.get("reloading"):
            bits.append("⏳ reloading the speech model…")
        try:
            self.server_info.configure(text="\n".join(bits))
        except Exception:
            pass
        self._load_server_logs()
        self._load_devices()

    # -------------------------------------------------------------- server ops --
    def _find_servers(self):
        """Broadcast a probe and offer what answers."""
        from .. import discovery
        tr = self.app.tr
        self.test_label.configure(text=tr("wizard_searching"), text_color=theme.TEXT_MUTED)

        def run():
            found = discovery.discover()

            def show():
                for child in self.found_box.winfo_children():
                    child.destroy()
                if not found:
                    self.found_box.pack_forget()
                    self.test_label.configure(text=tr("wizard_find_none"),
                                              text_color=theme.WARN)
                    return
                self.found_box.pack(fill="x", pady=(theme.PAD_S, 0))
                self.test_label.configure(text=tr("wizard_find_count", count=len(found)),
                                          text_color=theme.TEXT_MUTED)
                for entry in found:
                    label = entry["url"] + (f"  ·  v{entry['version']}"
                                            if entry.get("version") else "")
                    self._button(self.found_box, label,
                                 lambda u=entry["url"]: self._use_found(u), 340).pack(
                        anchor="w", pady=2)
            self.app.post(show)

        threading.Thread(target=run, daemon=True).start()

    def _use_found(self, url: str) -> None:
        self.server_field.set(url)
        self.test_label.configure(text=url, text_color=theme.OK)
        if url.startswith("https://"):
            self._repin()

    def _render_pin(self) -> None:
        tr = self.app.tr
        pin = self.cfg.get("tls_pin") or ""
        https = (self.server_field.get() or "").strip().lower().startswith("https://")
        if not https:
            self.pin_label.configure(text=tr("settings_pin_not_needed"),
                                     text_color=theme.TEXT_FAINT)
        elif pin:
            from ..api import format_fingerprint
            self.pin_label.configure(
                text=tr("settings_pin_set", fingerprint=format_fingerprint(pin)),
                text_color=theme.OK)
        else:
            self.pin_label.configure(text=tr("settings_pin_missing"),
                                     text_color=theme.WARN)
        self.pin_card.pack(fill="x", pady=(theme.PAD_S, 0))

    def _repin(self):
        """Read the certificate the server presents now and remember it."""
        from .. import api as apimod
        tr = self.app.tr
        cfg = dict(self.cfg)
        cfgmod.parse_server_url(self.server_field.get(), cfg)
        if not cfgmod.server_url(cfg).startswith("https://"):
            self.pin_label.configure(text=tr("settings_pin_not_needed"),
                                     text_color=theme.TEXT_FAINT)
            return
        self.pin_label.configure(text=tr("wizard_pin_checking"), text_color=theme.TEXT_MUTED)

        def run():
            try:
                fingerprint = apimod.fetch_fingerprint(cfg["server_host"], cfg["server_port"])
            except (OSError, ValueError) as err:
                # capture as a default arg: `err` dies with the except block
                self.app.post(lambda err=err: self.pin_label.configure(
                    text=tr("wizard_pin_failed", error=err), text_color=theme.ERROR))
                return

            def show():
                self.cfg["tls_pin"] = fingerprint
                self._render_pin()
            self.app.post(show)

        threading.Thread(target=run, daemon=True).start()

    def _forget_pin(self):
        self.cfg["tls_pin"] = ""
        self._render_pin()
        self._mark_dirty()

    def _test(self):
        self.test_label.configure(text="…", text_color=theme.TEXT_MUTED)
        api = self._new_api()

        def run():
            try:
                status = api.status()
                msg = self.app.tr("wizard_test_ok",
                                  model=status.get("whisper_model", "?"),
                                  device=status.get("device", "?"))
                color = theme.OK
            except ApiError as e:
                kind = {"unreachable": "err_server_unreachable",
                        "bad_token": "err_bad_token"}.get(e.kind)
                msg = self.app.tr(kind, error=e.detail) if kind else self.app.tr(
                    "err_generic", error=e.detail)
                color = theme.ERROR

            def done():
                self.test_label.configure(text=msg, text_color=color)
                self._set_status(color == theme.OK, msg)
                if color == theme.OK:
                    self._apply_status(status)
            self.app.post(done)

        threading.Thread(target=run, daemon=True).start()

    def _apply_server_settings(self):
        tr = self.app.tr
        changes = {
            "whisper_model": self.server_model_menu.get(),
            "language": self.server_language_menu.get(),
            "cleanup": bool(self.server_cleanup_switch.get()),
            "cleanup_model": self.cleanup_model_menu.get(),
        }
        self.remote_label.configure(text="…", text_color=theme.TEXT_MUTED)
        api = self._new_api()

        def run():
            try:
                out = api.patch_settings(changes)
                msg = tr("settings_server_applied",
                         keys=", ".join(f"{k}={v}" for k, v in out.get("applied", {}).items()))
                color = theme.OK
            except ApiError as e:
                msg = tr("err_generic", error=e.detail)
                color = theme.ERROR
            self.app.post(lambda: self.remote_label.configure(text=msg, text_color=color))

        threading.Thread(target=run, daemon=True).start()

    def _preload(self):
        tr = self.app.tr
        self.remote_label.configure(text="…", text_color=theme.TEXT_MUTED)
        api = self._new_api()
        model = self.cleanup_model_menu.get()

        def run():
            try:
                out = api.preload_model(model)
                msg = tr("settings_preload_ok", model=out.get("model", model),
                         seconds=out.get("seconds", "?"))
                color = theme.OK
            except ApiError as e:
                msg = tr("settings_self_test_fail", error=e.detail)
                color = theme.ERROR
            self.app.post(lambda: self.remote_label.configure(text=msg, text_color=color))

        threading.Thread(target=run, daemon=True).start()

    def _self_test(self):
        tr = self.app.tr
        self.remote_label.configure(text="…", text_color=theme.TEXT_MUTED)
        api = self._new_api()

        def run():
            try:
                out = api.self_test()
                if out.get("ok"):
                    t = out.get("timings", {})
                    msg = tr("settings_self_test_ok", text=out.get("text", ""),
                             total=t.get("total_s", "?"), whisper=t.get("whisper_s", "?"),
                             cleanup=t.get("cleanup_s", "?"))
                    color = theme.OK
                else:
                    msg = tr("settings_self_test_fail",
                             error=out.get("cleanup_error") or "unknown error")
                    color = theme.WARN
            except ApiError as e:
                msg = tr("settings_self_test_fail", error=e.detail)
                color = theme.ERROR
            self.app.post(lambda: self.remote_label.configure(text=msg, text_color=color))

        threading.Thread(target=run, daemon=True).start()

    def _load_server_logs(self):
        api = self._new_api()

        def run():
            try:
                lines = api.logs(120)
            except ApiError as e:
                lines = [self.app.tr("err_generic", error=e.detail)]

            def show():
                self.server_logs.configure(state="normal")
                self.server_logs.delete("1.0", "end")
                self.server_logs.insert("1.0", "\n".join(lines))
                self.server_logs.configure(state="disabled")
            self.app.post(show)

        threading.Thread(target=run, daemon=True).start()

    def _load_devices(self):
        api = self._new_api()

        def run():
            try:
                tokens = api.list_tokens()
            except ApiError:
                self.app.post(lambda: self.devices_label.configure(
                    text=self.app.tr("err_server_unreachable", error="")))
                return

            def show():
                for child in self.devices_box.winfo_children():
                    child.destroy()
                if not tokens:
                    ctk.CTkLabel(self.devices_box, text="—", font=theme.font(11),
                                 text_color=theme.TEXT_FAINT).pack(anchor="w")
                for entry in tokens:
                    row = ctk.CTkFrame(self.devices_box, fg_color="transparent")
                    row.pack(fill="x", pady=2)
                    when = entry.get("last_used")
                    detail = (time.strftime("%Y-%m-%d %H:%M", time.localtime(when))
                              if when else self.app.tr("settings_device_never_used"))
                    ctk.CTkLabel(row, text=f"{entry.get('name')} · "
                                           f"{self.app.tr('settings_device_last_used', when=detail)}"
                                           + (f" · {entry['last_ip']}" if entry.get("last_ip") else ""),
                                 font=theme.font(11), text_color=theme.TEXT_MUTED).pack(side="left")
                    self._button(row, self.app.tr("settings_revoke"),
                                 lambda tid=entry.get("id"): self._revoke(tid),
                                 90).pack(side="right")
            self.app.post(show)

        threading.Thread(target=run, daemon=True).start()

    def _issue_token(self):
        name = self.device_name_var.get().strip()
        if not name:
            return
        api = self._new_api()

        def run():
            try:
                out = api.create_token(name)
                text = self.app.tr("settings_token_created", name=name) + "\n" + out["token"]

                def show():
                    self.token_box.configure(state="normal")
                    self.token_box.delete("1.0", "end")
                    self.token_box.insert("1.0", text)
                    self.token_box.configure(state="disabled")
                    self._load_devices()
                self.app.post(show)
            except ApiError as err:
                # bind as a default arg: `e` is deleted when the except block ends
                self.app.post(lambda err=err: self.remote_label.configure(
                    text=self.app.tr("err_generic", error=err.detail),
                    text_color=theme.ERROR))

        threading.Thread(target=run, daemon=True).start()

    def _revoke(self, token_id):
        api = self._new_api()

        def run():
            try:
                api.revoke_token(token_id)
            except ApiError:
                pass
            self.app.post(lambda: self.remote_label.configure(
                text=self.app.tr("settings_revoked"), text_color=theme.OK))
            self._load_devices()

        threading.Thread(target=run, daemon=True).start()

    # -------------------------------------------------------------- local ops --
    def _test_mic(self):
        tr = self.app.tr
        self.mic_btn.configure(state="disabled")
        self.mic_label.configure(text=tr("settings_testing"), text_color=theme.TEXT_MUTED)
        device = self._device_map.get(self.device_menu.get())
        api = self._new_api()

        def on_level(rms):
            self.app.post(lambda: self.level_bar.set(min(1.0, rms * 8)))

        def run():
            recorder = audio.Recorder(max_seconds=3, auto_stop=False, on_level=on_level,
                                      device=audio.resolve_device(device))
            try:
                recorder.start()
                time.sleep(3)
                wav = recorder.stop()
                if not wav:
                    raise audio.AudioError("no audio captured")
                out = api.transcribe(wav, cleanup=False, language="auto")
                text = (out.get("text") or "").strip() or "(empty)"
                msg, color = tr("settings_mic_ok", text=text), theme.OK
            except (audio.AudioError, ApiError) as e:
                detail = getattr(e, "detail", None) or str(e)
                msg, color = tr("settings_mic_fail", error=detail), theme.ERROR

            def done():
                self.mic_label.configure(text=msg, text_color=color)
                self.mic_btn.configure(state="normal")
                self.level_bar.set(0)
            self.app.post(done)

        threading.Thread(target=run, daemon=True).start()

    def _load_client_logs(self):
        text = log.read(lines=200) or "(empty)"
        self.client_logs.configure(state="normal")
        self.client_logs.delete("1.0", "end")
        self.client_logs.insert("1.0", text)
        self.client_logs.configure(state="disabled")
        self.client_logs.see("end")

    def _clear_logs(self):
        ok = log.clear()
        self._load_client_logs()
        self.logs_label.configure(text=self.app.tr("settings_logs_cleared") if ok else "—",
                                  text_color=theme.OK if ok else theme.ERROR)

    def _export_settings(self):
        tr = self.app.tr
        try:
            cfg = self._collect()
            cfg.pop("token", None)                 # never export the secret
            path = os.path.join(cfgmod.config_dir(), "vozlab-settings.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, sort_keys=True)
                f.write("\n")
            self.data_label.configure(text=tr("settings_exported", file=os.path.basename(path)),
                                      text_color=theme.OK)
            self.app.open_config_folder()
        except Exception as e:  # noqa: BLE001
            self.data_label.configure(text=tr("err_generic", error=e), text_color=theme.ERROR)

    def _import_settings(self):
        tr = self.app.tr
        path = os.path.join(cfgmod.config_dir(), "vozlab-settings.json")
        try:
            with open(path, encoding="utf-8") as f:
                imported = json.load(f)
            if not isinstance(imported, dict):
                raise ValueError("expected a JSON object")
            # a hand-edited file could contain anything: keep only known keys
            keep = {k: v for k, v in imported.items() if k in cfgmod.DEFAULTS}
            keep["token"] = self.token_field.get()      # the secret always stays local
            self.cfg.update(keep)
            self.app.apply_config(self.cfg)
            self.win.destroy()
            if self.on_saved:
                self.on_saved()
        except Exception as e:  # noqa: BLE001
            self.data_label.configure(text=tr("settings_import_failed", error=e),
                                      text_color=theme.ERROR)

    def _reset_settings(self):
        tr = self.app.tr
        if not _ask(self.win, tr("settings_reset"), tr("settings_reset_confirm")):
            return
        fresh = dict(cfgmod.DEFAULTS)
        fresh["token"] = self.cfg.get("token", "")
        fresh["server_host"] = self.cfg.get("server_host", "")
        fresh["server_port"] = self.cfg.get("server_port", 8092)
        fresh["first_run_done"] = True
        self.app.apply_config(fresh)
        self.win.destroy()
        if self.on_saved:
            self.on_saved()

    def _export_diagnostics(self):
        tr = self.app.tr
        try:
            cfg = self._collect()
            path = diagnostics.write_report(
                cfgmod.config_dir(), cfg,
                log_path=os.path.join(cfgmod.config_dir(), "vozlab.log"),
                server_status=self.server_status,
                server_health=getattr(self.app, "last_server_health", None),
            )
        except Exception as e:  # noqa: BLE001
            self.diag_label.configure(text=tr("err_generic", error=e), text_color=theme.ERROR)
            return
        self.diag_label.configure(
            text=tr("settings_diagnostics_done", file=os.path.basename(path)),
            text_color=theme.OK)
        self.app.open_config_folder()

    def _show_last_update(self) -> None:
        message = getattr(self.app, "last_update_message", "")
        url = getattr(self.app, "last_update_url", "")
        if not message:
            return
        try:
            self.update_label.configure(text=message,
                                        text_color=theme.WARN if url else theme.TEXT_MUTED)
        except Exception:
            pass

    def _check_updates(self) -> None:
        self.update_label.configure(text="…", text_color=theme.TEXT_MUTED)
        self.app.check_for_updates(manual=True)

    def _change_hotkey(self):
        def captured(code, name):
            self.cfg["hotkey"] = code
            self.keycap.set_text(name or str(code))
            self._mark_dirty()
        HotkeyCaptureDialog(self.app, captured)

    # ------------------------------------------------------------------- save --
    def _collect(self) -> dict:
        """Read every widget back into a config dict (no side effects)."""
        tr = self.app.tr
        cfg = dict(self.cfg)
        cfgmod.parse_server_url(self.server_field.get(), cfg)
        cfg["token"] = self.token_field.get()
        cfg["hotkey_mode"] = ("hold" if self.mode_seg.get() == tr("settings_mode_hold")
                              else "toggle")
        cfg["auto_stop"] = bool(self.auto_stop_switch.get())
        cfg["cleanup"] = bool(self.cleanup_switch.get())
        cfg["cleanup_guard"] = bool(self.cleanup_guard_switch.get())
        cfg["language"] = self.language_menu.get()
        cfg["style"] = self.style_names.get(self.style_menu.get(), "default")
        cfg["per_app_profiles"] = bool(self.per_app_switch.get())
        cfg["profiles"] = dict(self._profile_rules)
        vocab = [t.strip() for t in self.vocab_box.get("1.0", "end")
                 .replace(";", ",").split(",") if t.strip()]
        cfg["vocabulary"] = vocab
        cfg["tls_pin"] = self.cfg.get("tls_pin", "")
        cfg["input_device"] = self._device_map.get(self.device_menu.get())

        for entry, key in ((self.silence_ms_entry, "silence_ms"),
                           (self.silence_rms_entry, "silence_rms"),
                           (self.min_seconds_entry, "min_seconds"),
                           (self.max_seconds_entry, "max_seconds")):
            raw = entry._var.get().replace(",", ".").strip()
            try:
                cfg[key] = float(raw) if entry._is_float else int(float(raw))
            except ValueError:
                cfg[key] = cfgmod.DEFAULTS[key]      # ignore junk instead of crashing
        cfg["silence_ms"] = max(0, int(cfg["silence_ms"]))
        cfg["silence_rms"] = min(0.5, max(0.0005, float(cfg["silence_rms"])))
        cfg["min_seconds"] = max(0.0, float(cfg["min_seconds"]))
        cfg["max_seconds"] = max(1.0, float(cfg["max_seconds"]))

        cfg["theme"] = self.themes.get(self.theme_menu.get(), "dark")
        cfg["show_pill"] = bool(self.pill_switch.get())
        cfg["pill_position"] = self.positions.get(self.position_menu.get(), "bottom-center")
        cfg["pill_style"] = self.styles.get(self.style_menu.get(), "full")
        cfg["ui_language"] = self.ui_language_menu.get()
        cfg["beeps"] = bool(self.beeps_switch.get())
        cfg["launch_at_login"] = bool(self.startup_switch.get())
        cfg["restore_clipboard"] = bool(self.clipboard_switch.get())
        cfg["debug"] = bool(self.debug_switch.get())
        cfg["check_updates"] = bool(self.check_updates_switch.get())
        cfg["device_name"] = self.device_name_var.get().strip()
        cfg["calibrate"] = False
        cfg["first_run_done"] = True
        return cfg

    def _save(self):
        self.app.apply_config(self._collect())
        self.win.destroy()
        if self.on_saved:
            self.on_saved()


def _ask(parent, title: str, message: str) -> bool:
    """Minimal yes/no modal (no messagebox dependency)."""
    box = ctk.CTkToplevel(parent)
    box.title(title)
    box.geometry("420x180")
    box.resizable(False, False)
    box.attributes("-topmost", True)
    result = {"ok": False}

    ctk.CTkLabel(box, text=message, font=theme.font(13), wraplength=370,
                 justify="center").pack(pady=(28, 18), padx=20)
    row = ctk.CTkFrame(box, fg_color="transparent")
    row.pack()

    def yes():
        result["ok"] = True
        box.destroy()

    ctk.CTkButton(row, text="OK", width=110, height=36, fg_color=theme.ERROR,
                  hover_color=theme.ERROR, corner_radius=theme.RADIUS_CONTROL,
                  command=yes).pack(side="left", padx=6)
    ctk.CTkButton(row, text="✕", width=110, height=36, fg_color="transparent",
                  border_width=1, border_color=theme.BORDER, hover_color=theme.SURFACE_2,
                  corner_radius=theme.RADIUS_CONTROL, command=box.destroy).pack(side="left", padx=6)
    box.transient(parent)
    box.grab_set()
    parent.wait_window(box)
    return result["ok"]
