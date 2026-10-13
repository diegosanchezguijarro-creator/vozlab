"""Tkinter UI: settings window, hotkey capture dialog and the first-run wizard."""

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import config as cfgmod
from . import hotkeys as hotkeys_mod


class HotkeyCaptureDialog:
    """Modal 'press a key' dialog used to rebind the dictation key."""

    def __init__(self, app, on_captured):
        self.app = app
        self.on_captured = on_captured
        tr = app.tr
        self.win = tk.Toplevel(app.root)
        self.win.title(tr("settings_hotkey"))
        self.win.geometry("360x130")
        self.win.attributes("-topmost", True)
        self.win.resizable(False, False)

        ttk.Label(self.win, text=tr("wizard_press_key"),
                  font=("Segoe UI", 12)).pack(pady=(28, 6))
        self.status = ttk.Label(self.win, text="")
        self.status.pack()
        ttk.Button(self.win, text=tr("settings_cancel"), command=self.win.destroy).pack(pady=12)

        threading.Thread(target=self._capture, daemon=True).start()

    def _capture(self):
        result = hotkeys_mod.HotkeyManager.capture_next_key(timeout=30)
        if not result:
            self.win.after(0, self.win.destroy)
            return
        code, name = result
        self.win.after(0, lambda: self.status.configure(
            text=self.app.tr("wizard_hotkey_captured", name=name or str(code))))
        self.win.after(400, lambda: self._finish(code, name))

    def _finish(self, code, name):
        self.win.destroy()
        self.on_captured(code, name)


class SettingsWindow:
    """All user-facing options in one form."""

    def __init__(self, app, on_saved=None):
        self.app = app
        self.on_saved = on_saved
        self.cfg = dict(app.cfg)
        tr = app.tr

        self.win = tk.Toplevel(app.root)
        self.win.title(tr("settings_title"))
        self.win.geometry("560x520")
        self.win.resizable(False, False)

        pad = {"padx": 12, "pady": 6}
        row = 0

        # ---- server ----
        ttk.Label(self.win, text=tr("settings_server")).grid(row=row, column=0, sticky="w", **pad)
        self.server_var = tk.StringVar(value=cfgmod.server_url(self.cfg))
        ttk.Entry(self.win, textvariable=self.server_var, width=44).grid(row=row, column=1, **pad)
        row += 1

        ttk.Label(self.win, text=tr("settings_token")).grid(row=row, column=0, sticky="w", **pad)
        self.token_var = tk.StringVar(value=self.cfg.get("token", ""))
        ttk.Entry(self.win, textvariable=self.token_var, width=44).grid(row=row, column=1, **pad)
        row += 1

        test_row = ttk.Frame(self.win)
        test_row.grid(row=row, column=0, columnspan=2, sticky="w", padx=12)
        ttk.Button(test_row, text=tr("settings_test"), command=self._test).pack(side="left")
        self.test_label = ttk.Label(test_row, text="")
        self.test_label.pack(side="left", padx=10)
        row += 1

        ttk.Separator(self.win, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=8, padx=12)
        row += 1

        # ---- hotkey ----
        ttk.Label(self.win, text=tr("settings_hotkey")).grid(row=row, column=0, sticky="w", **pad)
        hk = ttk.Frame(self.win)
        hk.grid(row=row, column=1, sticky="w", **pad)
        self.hotkey_label = ttk.Label(hk, text=hotkeys_mod.describe_hotkey(self.cfg.get("hotkey")))
        self.hotkey_label.pack(side="left")
        ttk.Button(hk, text=tr("settings_hotkey_change"), command=self._change_hotkey).pack(
            side="left", padx=8)
        row += 1

        ttk.Label(self.win, text=tr("settings_mode")).grid(row=row, column=0, sticky="w", **pad)
        self.mode_var = tk.StringVar(value=self.cfg.get("hotkey_mode", "hold"))
        mode = ttk.Frame(self.win)
        mode.grid(row=row, column=1, sticky="w", **pad)
        ttk.Radiobutton(mode, text=tr("settings_mode_hold"), value="hold",
                        variable=self.mode_var).pack(side="left")
        ttk.Radiobutton(mode, text=tr("settings_mode_toggle"), value="toggle",
                        variable=self.mode_var).pack(side="left", padx=10)
        row += 1

        # ---- behaviour ----
        self.auto_stop_var = tk.BooleanVar(value=self.cfg.get("auto_stop", False))
        self.cleanup_var = tk.BooleanVar(value=self.cfg.get("cleanup", True))
        self.beeps_var = tk.BooleanVar(value=self.cfg.get("beeps", True))
        self.clip_var = tk.BooleanVar(value=self.cfg.get("restore_clipboard", True))
        self.pill_var = tk.BooleanVar(value=self.cfg.get("show_pill", True))
        self.startup_var = tk.BooleanVar(value=self.cfg.get("launch_at_login", False))
        self.debug_var = tk.BooleanVar(value=self.cfg.get("debug", False))

        checks = [
            (tr("settings_auto_stop"), self.auto_stop_var),
            (tr("settings_cleanup"), self.cleanup_var),
            (tr("settings_beeps"), self.beeps_var),
            (tr("settings_clipboard"), self.clip_var),
            (tr("settings_pill"), self.pill_var),
            (tr("settings_startup"), self.startup_var),
            (tr("settings_debug"), self.debug_var),
        ]
        for text, var in checks:
            ttk.Checkbutton(self.win, text=text, variable=var).grid(
                row=row, column=0, columnspan=2, sticky="w", padx=12, pady=2)
            row += 1

        ttk.Separator(self.win, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=8, padx=12)
        row += 1

        # ---- languages ----
        ttk.Label(self.win, text=tr("settings_language")).grid(row=row, column=0, sticky="w", **pad)
        self.lang_var = tk.StringVar(value=self.cfg.get("language", "auto"))
        ttk.Combobox(self.win, textvariable=self.lang_var, width=20, state="readonly",
                     values=["auto", "en", "es", "fr", "de", "it", "pt", "nl", "ru",
                             "ja", "zh", "ko", "ar", "hi", "tr", "pl", "sv"]).grid(
            row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Label(self.win, text=tr("settings_ui_language")).grid(row=row, column=0, sticky="w", **pad)
        self.ui_lang_var = tk.StringVar(value=self.cfg.get("ui_language", "auto"))
        ttk.Combobox(self.win, textvariable=self.ui_lang_var, width=20, state="readonly",
                     values=["auto", "en", "es"]).grid(row=row, column=1, sticky="w", **pad)
        row += 1

        # ---- buttons ----
        buttons = ttk.Frame(self.win)
        buttons.grid(row=row, column=0, columnspan=2, pady=16)
        ttk.Button(buttons, text=tr("settings_save"), command=self._save).pack(side="left", padx=6)
        ttk.Button(buttons, text=tr("settings_cancel"), command=self.win.destroy).pack(side="left")

    # -- actions -------------------------------------------------------------
    def _test(self):
        self.test_label.configure(text="…")
        cfg = dict(self.cfg)
        cfgmod.parse_server_url(self.server_var.get(), cfg)
        cfg["token"] = self.token_var.get().strip()
        threading.Thread(target=self._test_thread, args=(cfg,), daemon=True).start()

    def _test_thread(self, cfg):
        from .api import ApiError, VozLabAPI
        try:
            health = VozLabAPI(cfgmod.server_url(cfg), cfg["token"]).health()
            msg = self.app.tr("wizard_test_ok",
                              model=health.get("whisper_model", "?"),
                              device=health.get("device", "?"))
            color = "#0a7d3f"
        except ApiError as e:
            key = {"unreachable": "err_server_unreachable", "bad_token": "err_bad_token"}.get(
                e.kind, None)
            msg = self.app.tr(key, error=e.detail) if key else self.app.tr("err_generic", error=e.detail)
            color = "#b91c1c"
        def show():
            self.test_label.configure(text=msg, foreground=color)
        self.app.post(show)

    def _change_hotkey(self):
        def captured(code, name):
            self.cfg["hotkey"] = code
            self.hotkey_label.configure(text=f"{name or code}")
        HotkeyCaptureDialog(self.app, captured)

    def _save(self):
        cfg = dict(self.cfg)
        cfgmod.parse_server_url(self.server_var.get(), cfg)
        cfg["token"] = self.token_var.get().strip()
        cfg["hotkey_mode"] = self.mode_var.get()
        cfg["auto_stop"] = self.auto_stop_var.get()
        cfg["cleanup"] = self.cleanup_var.get()
        cfg["beeps"] = self.beeps_var.get()
        cfg["restore_clipboard"] = self.clip_var.get()
        cfg["show_pill"] = self.pill_var.get()
        cfg["launch_at_login"] = self.startup_var.get()
        cfg["debug"] = self.debug_var.get()
        cfg["language"] = self.lang_var.get()
        cfg["ui_language"] = self.ui_lang_var.get()
        cfg["first_run_done"] = True
        cfg["calibrate"] = False

        self.app.apply_config(cfg)
        self.win.destroy()
        if self.on_saved:
            self.on_saved()


class Wizard:
    """First-run setup: server → dictation key → microphone test."""

    def __init__(self, app):
        self.app = app
        self.cfg = dict(app.cfg)
        self.step = 0

        self.win = tk.Toplevel(app.root)
        self.win.title(app.tr("wizard_title"))
        self.win.geometry("540x400")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)

        self.title = ttk.Label(self.win, text=app.tr("wizard_welcome"),
                               font=("Segoe UI", 11), wraplength=480)
        self.title.pack(pady=(18, 8), padx=16)

        self.body = ttk.Frame(self.win)
        self.body.pack(fill="both", expand=True, padx=16)

        nav = ttk.Frame(self.win)
        nav.pack(fill="x", pady=12, padx=16)
        self.back_btn = ttk.Button(nav, text=app.tr("wizard_back"), command=self._back)
        self.back_btn.pack(side="left")
        self.next_btn = ttk.Button(nav, text=app.tr("wizard_next"), command=self._next)
        self.next_btn.pack(side="right")

        self._render()

    # -- steps ---------------------------------------------------------------
    def _clear(self):
        for child in self.body.winfo_children():
            child.destroy()

    def _render(self):
        self._clear()
        if self.step == 0:
            self._step_server()
        elif self.step == 1:
            self._step_hotkey()
        else:
            self._step_mic()
        self.back_btn.configure(state=("normal" if self.step > 0 else "disabled"))
        self.next_btn.configure(
            text=self.app.tr("wizard_finish") if self.step == 2 else self.app.tr("wizard_next"))

    def _step_server(self):
        tr = self.app.tr
        ttk.Label(self.body, text=tr("wizard_server_hint"), wraplength=480).pack(anchor="w")
        self.server_var = tk.StringVar(value=cfgmod.server_url(self.cfg))
        ttk.Entry(self.body, textvariable=self.server_var, width=56).pack(anchor="w", pady=(4, 10))
        ttk.Label(self.body, text=tr("wizard_token_hint"), wraplength=480).pack(anchor="w")
        self.token_var = tk.StringVar(value=self.cfg.get("token", ""))
        ttk.Entry(self.body, textvariable=self.token_var, width=56).pack(anchor="w", pady=(4, 10))
        row = ttk.Frame(self.body)
        row.pack(anchor="w")
        ttk.Button(row, text=tr("wizard_test"), command=self._test).pack(side="left")
        self.test_label = ttk.Label(row, text="", wraplength=300)
        self.test_label.pack(side="left", padx=10)

    def _step_hotkey(self):
        tr = self.app.tr
        ttk.Label(self.body, text=tr("wizard_hotkey_hint"), wraplength=480).pack(anchor="w")
        self.hotkey_status = ttk.Label(self.body, text="", font=("Segoe UI", 11))
        self.hotkey_status.pack(anchor="w", pady=10)
        ttk.Button(self.body, text=tr("settings_hotkey_change"), command=self._capture).pack(anchor="w")

    def _step_mic(self):
        tr = self.app.tr
        ttk.Label(self.body, text=tr("settings_hotkey") + ": "
                  + hotkeys_mod.describe_hotkey(self.cfg.get("hotkey")), wraplength=480).pack(anchor="w")
        ttk.Button(self.body, text=tr("wizard_mic_test"), command=self._mic_test).pack(anchor="w", pady=10)
        self.mic_label = ttk.Label(self.body, text="", wraplength=480)
        self.mic_label.pack(anchor="w")

    # -- navigation ----------------------------------------------------------
    def _back(self):
        if self.step > 0:
            self.step -= 1
            self._render()

    def _next(self):
        if self.step == 0:
            cfgmod.parse_server_url(self.server_var.get(), self.cfg)
            self.cfg["token"] = self.token_var.get().strip()
            if not self.cfg.get("server_host"):
                messagebox.showwarning(self.app.tr("wizard_title"),
                                       self.app.tr("wizard_server_hint"))
                return
            self.step = 1
            self._render()
        elif self.step == 1:
            self.step = 2
            self._render()
        else:
            self.cfg["first_run_done"] = True
            self.cfg["calibrate"] = False
            self.app.apply_config(self.cfg)
            self.win.destroy()

    # -- actions -------------------------------------------------------------
    def _test(self):
        self.test_label.configure(text="…")
        cfg = dict(self.cfg)
        cfgmod.parse_server_url(self.server_var.get(), cfg)
        cfg["token"] = self.token_var.get().strip()

        def run():
            from .api import ApiError, VozLabAPI
            try:
                health = VozLabAPI(cfgmod.server_url(cfg), cfg["token"]).health()
                msg = self.app.tr("wizard_test_ok", model=health.get("whisper_model", "?"),
                                  device=health.get("device", "?"))
                color = "#0a7d3f"
            except ApiError as e:
                key = {"unreachable": "err_server_unreachable", "bad_token": "err_bad_token"}.get(e.kind)
                msg = self.app.tr(key, error=e.detail) if key else self.app.tr("err_generic", error=e.detail)
                color = "#b91c1c"
            self.app.post(lambda: self.test_label.configure(text=msg, foreground=color))

        threading.Thread(target=run, daemon=True).start()

    def _capture(self):
        def captured(code, name):
            self.cfg["hotkey"] = code
            self.hotkey_status.configure(text=self.app.tr("wizard_hotkey_captured",
                                                          name=name or str(code)))
        HotkeyCaptureDialog(self.app, captured)

    def _mic_test(self):
        tr = self.app.tr
        self.mic_label.configure(text=tr("wizard_mic_working"))

        def run():
            try:
                from . import audio
                rec = audio.Recorder(max_seconds=3, auto_stop=False)
                rec.start()
                import time
                time.sleep(3)
                wav = rec.stop()
                if not wav:
                    raise audio.AudioError("no audio")
                out = self.app.api.transcribe(wav, cleanup=False, language="auto")
                text = out.get("text") or "(empty)"
                self.app.post(lambda: self.mic_label.configure(foreground="#0a7d3f",
                                                               text=tr("wizard_mic_result", text=text)))
            except Exception as e:  # noqa: BLE001
                self.app.post(lambda: self.mic_label.configure(foreground="#b91c1c",
                                                               text=tr("err_generic", error=e)))

        threading.Thread(target=run, daemon=True).start()
