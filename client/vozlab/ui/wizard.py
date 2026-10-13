"""First-run wizard: server → dictation key → microphone."""

import threading
import time

import customtkinter as ctk

from .. import APP_NAME
from .. import config as cfgmod
from .. import hotkeys as hotkeys_mod
from ..api import ApiError, VozLabAPI
from . import theme, widgets


class Wizard:
    STEPS = 3

    def __init__(self, app):
        self.app = app
        self.cfg = dict(app.cfg)
        self.step = 0
        tr = app.tr

        self.win = ctk.CTkToplevel(app.root)
        self.win.title(f"{APP_NAME} — {tr('wizard_title')}")
        self.win.geometry("620x600")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)

        head = ctk.CTkFrame(self.win, fg_color="transparent")
        head.pack(fill="x", padx=theme.PAD_L, pady=(theme.PAD_L, 0))

        self.dots = []
        dot_row = ctk.CTkFrame(head, fg_color="transparent")
        dot_row.pack(anchor="w")
        for _ in range(self.STEPS):
            dot = ctk.CTkFrame(dot_row, width=26, height=5, corner_radius=3,
                               fg_color=theme.SURFACE_2)
            dot.pack(side="left", padx=(0, 6))
            self.dots.append(dot)

        self.title = ctk.CTkLabel(head, text="", font=theme.font(21, "bold"), anchor="w")
        self.title.pack(anchor="w", pady=(14, 2))
        self.subtitle = ctk.CTkLabel(head, text="", font=theme.font(13),
                                     text_color=theme.TEXT_MUTED, anchor="w",
                                     justify="left", wraplength=520)
        self.subtitle.pack(anchor="w")

        self.body = ctk.CTkFrame(self.win, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=theme.PAD_L, pady=theme.PAD)

        foot = ctk.CTkFrame(self.win, fg_color="transparent")
        foot.pack(fill="x", padx=theme.PAD_L, pady=(0, theme.PAD_L))
        self.back_btn = ctk.CTkButton(foot, text=tr("wizard_back"), width=100, height=40,
                                      corner_radius=theme.RADIUS_CONTROL, font=theme.font(13),
                                      fg_color="transparent", border_width=1,
                                      border_color=theme.BORDER, hover_color=theme.SURFACE_2,
                                      command=self._back)
        self.back_btn.pack(side="left")
        self.next_btn = ctk.CTkButton(foot, text=tr("wizard_next"), width=140, height=40,
                                      corner_radius=theme.RADIUS_CONTROL,
                                      font=theme.font(13, "bold"), fg_color=theme.ACCENT,
                                      hover_color=theme.ACCENT_HOVER, command=self._next)
        self.next_btn.pack(side="right")

        self._render()

    # -------------------------------------------------------------- layout ---
    def _clear(self):
        for child in self.body.winfo_children():
            child.destroy()

    def _render(self):
        self._clear()
        for i, dot in enumerate(self.dots):
            dot.configure(fg_color=theme.ACCENT if i <= self.step else theme.SURFACE_2)
        tr = self.app.tr
        self.back_btn.configure(state="normal" if self.step > 0 else "disabled")
        self.next_btn.configure(text=tr("wizard_finish") if self.step == self.STEPS - 1
                                else tr("wizard_next"))

        if self.step == 0:
            self.title.configure(text=tr("wizard_welcome_title"))
            self.subtitle.configure(text=tr("wizard_welcome"))
            self._step_server()
        elif self.step == 1:
            self.title.configure(text=tr("wizard_hotkey_title"))
            self.subtitle.configure(text=tr("wizard_hotkey_hint"))
            self._step_hotkey()
        else:
            self.title.configure(text=tr("wizard_mic_title"))
            self.subtitle.configure(text=tr("wizard_mic_hint"))
            self._step_mic()

    def _step_server(self):
        tr = self.app.tr
        card = widgets.Card(self.body, tr("group_connection"))
        card.pack(fill="x")
        self.server_field = widgets.Field(card.body, tr("settings_server"),
                                          cfgmod.server_url(self.cfg) or "http://",
                                          placeholder="http://192.168.0.23:8092", width=500)
        self.server_field.pack(fill="x")
        self.token_field = widgets.Field(card.body, tr("settings_token"),
                                         self.cfg.get("token", ""),
                                         placeholder=tr("wizard_token_hint"), width=500)
        self.token_field.pack(fill="x", pady=(theme.PAD_S, 0))

        row = ctk.CTkFrame(card.body, fg_color="transparent")
        row.pack(fill="x", pady=(theme.PAD_S, 0))
        self.test_btn = ctk.CTkButton(row, text=tr("wizard_test"), height=36, width=160,
                                      corner_radius=theme.RADIUS_CONTROL,
                                      fg_color=theme.SURFACE_2, border_width=1,
                                      border_color=theme.BORDER, hover_color=theme.BORDER,
                                      font=theme.font(12), command=self._test)
        self.test_btn.pack(side="left")
        self.test_label = ctk.CTkLabel(row, text="", font=theme.font(12),
                                       text_color=theme.TEXT_MUTED, wraplength=280,
                                       justify="left")
        self.test_label.pack(side="left", padx=12)

        ctk.CTkLabel(self.body, text=tr("wizard_token_where"), font=theme.font(11),
                     text_color=theme.TEXT_FAINT, justify="left", wraplength=520).pack(
            anchor="w", pady=(theme.PAD_S, 0))

    def _step_hotkey(self):
        tr = self.app.tr
        card = widgets.Card(self.body)
        card.pack(fill="x")
        box = ctk.CTkFrame(card.body, fg_color="transparent")
        box.pack(pady=theme.PAD_L)

        ctk.CTkLabel(box, text="⌨️", font=theme.font(40)).pack()
        self.capture_label = ctk.CTkLabel(box, text=tr("wizard_press_key"),
                                          font=theme.font(16, "bold"))
        self.capture_label.pack(pady=(8, 12))
        self.keycap = widgets.KeyCap(box, hotkeys_mod.describe_hotkey(self.cfg.get("hotkey")))
        self.keycap.pack()
        self.capture_hint = ctk.CTkLabel(box, text=tr("wizard_hotkey_captured_hint"),
                                         font=theme.font(11), text_color=theme.TEXT_FAINT,
                                         wraplength=420, justify="center")
        self.capture_hint.pack(pady=(12, 0))

        self._capture()

    def _step_mic(self):
        tr = self.app.tr
        card = widgets.Card(self.body)
        card.pack(fill="x")
        box = ctk.CTkFrame(card.body, fg_color="transparent")
        box.pack(fill="x", pady=theme.PAD_L)

        ctk.CTkLabel(box, text="🎙️", font=theme.font(40)).pack()
        self.mic_btn = ctk.CTkButton(box, text=tr("wizard_mic_test"), height=42, width=260,
                                     corner_radius=theme.RADIUS_CONTROL, font=theme.font(13, "bold"),
                                     fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                                     command=self._mic_test)
        self.mic_btn.pack(pady=12)
        self.level = ctk.CTkProgressBar(box, height=8, corner_radius=4,
                                        progress_color=theme.ACCENT, fg_color=theme.SURFACE_2)
        self.level.set(0)
        self.level.pack(fill="x", padx=40, pady=(4, 12))
        self.mic_label = ctk.CTkLabel(box, text="", font=theme.font(12),
                                      text_color=theme.TEXT_MUTED, wraplength=460, justify="center")
        self.mic_label.pack()

    # ------------------------------------------------------------- actions ---
    def _back(self):
        if self.step > 0:
            self.step -= 1
            self._render()

    def _next(self):
        if self.step == 0:
            cfgmod.parse_server_url(self.server_field.get(), self.cfg)
            self.cfg["token"] = self.token_field.get()
            if not self.cfg.get("server_host"):
                self.test_label.configure(text=self.app.tr("wizard_server_hint"),
                                          text_color=theme.WARN)
                return
        self.step += 1
        if self.step >= self.STEPS:
            self.cfg["first_run_done"] = True
            self.cfg["calibrate"] = False
            self.app.apply_config(self.cfg)
            self.win.destroy()
            return
        self._render()

    def _test(self):
        self.test_label.configure(text="…", text_color=theme.TEXT_MUTED)
        self.test_btn.configure(state="disabled")
        cfg = dict(self.cfg)
        cfgmod.parse_server_url(self.server_field.get(), cfg)
        token = self.token_field.get()

        def run():
            try:
                health = VozLabAPI(cfgmod.server_url(cfg), token).health()
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
            self.app.post(done)

        threading.Thread(target=run, daemon=True).start()

    def _capture(self):
        def run():
            result = hotkeys_mod.HotkeyManager.capture_next_key(timeout=45)
            if not result:
                return
            code, name = result
            self.cfg["hotkey"] = code

            def done():
                self.capture_label.configure(text=self.app.tr("wizard_hotkey_captured",
                                                              name=name or str(code)))
                self.keycap.set_text(name or str(code))
            self.app.post(done)

        threading.Thread(target=run, daemon=True).start()

    def _mic_test(self):
        tr = self.app.tr
        self.mic_btn.configure(state="disabled")
        self.mic_label.configure(text=tr("wizard_mic_working"), text_color=theme.TEXT_MUTED)

        def run():
            from .. import audio
            last = [0.0]

            def on_level(rms):
                now = time.time()
                if now - last[0] < 0.08:      # throttle UI updates
                    return
                last[0] = now
                self.app.post(lambda: self.level.set(min(1.0, rms / 0.08)))

            try:
                rec = audio.Recorder(max_seconds=3, auto_stop=False, on_level=on_level)
                rec.start()
                time.sleep(3)
                wav = rec.stop()
                self.app.post(lambda: self.level.set(0))
                if not wav:
                    raise audio.AudioError("no audio captured")
                out = self.app.api.transcribe(wav, cleanup=False, language="auto")
                text = (out.get("text") or "").strip() or "(empty)"
                self.app.post(lambda: self.mic_label.configure(
                    text=tr("wizard_mic_result", text=text), text_color=theme.OK))
            except Exception as err:  # noqa: BLE001
                self.app.post(lambda err=err: self.mic_label.configure(
                    text=tr("err_generic", error=err), text_color=theme.ERROR))
            finally:
                self.app.post(lambda: self.mic_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()
