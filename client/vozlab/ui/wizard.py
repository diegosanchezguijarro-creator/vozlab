"""First-run wizard: server → dictation key → microphone."""

import threading
import time

import customtkinter as ctk

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
        self.win.title(tr("wizard_title"))
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

        # --- find the server automatically ---------------------------------
        find_row = ctk.CTkFrame(card.body, fg_color="transparent")
        find_row.pack(fill="x", pady=(0, theme.PAD_S))
        self.find_btn = ctk.CTkButton(
            find_row, text=tr("wizard_find_server"), height=36, width=180,
            corner_radius=theme.RADIUS_CONTROL, fg_color=theme.SURFACE_2,
            border_width=1, border_color=theme.BORDER, hover_color=theme.BORDER,
            font=theme.font(12), command=self._find_servers)
        self.find_btn.pack(side="left")
        self.find_label = ctk.CTkLabel(find_row, text=tr("wizard_find_hint"),
                                       font=theme.font(11), text_color=theme.TEXT_FAINT,
                                       wraplength=300, justify="left")
        self.find_label.pack(side="left", padx=10)
        # created lazily: an empty CTkFrame keeps its default 200px height
        self.found_box = ctk.CTkFrame(card.body, fg_color="transparent")

        self.server_field = widgets.Field(card.body, tr("settings_server"),
                                          cfgmod.server_url(self.cfg) or "http://",
                                          placeholder="http://192.168.0.23:8092", width=500)
        self.server_field.pack(fill="x")
        self.token_field = widgets.Field(card.body, tr("settings_token"),
                                         self.cfg.get("token", ""),
                                         placeholder=tr("wizard_token_hint"), width=500)
        self.token_field.pack(fill="x", pady=(theme.PAD_S, 0))

        # --- certificate pinning (https only) ------------------------------
        self.pin_card = ctk.CTkFrame(card.body, fg_color=theme.SURFACE_2,
                                     corner_radius=theme.RADIUS_CONTROL,
                                     border_width=1, border_color=theme.BORDER)
        self.pin_label = ctk.CTkLabel(self.pin_card, text="", font=theme.font(11),
                                      text_color=theme.TEXT_MUTED, justify="left",
                                      wraplength=460, anchor="w")
        self.pin_label.pack(anchor="w", padx=12, pady=10)
        # packed only when there is a certificate to talk about

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

    # -- LAN discovery -------------------------------------------------------
    def _find_servers(self):
        """Broadcast a probe and list the servers that answer."""
        tr = self.app.tr
        from .. import discovery

        self.find_btn.configure(state="disabled")
        self.find_label.configure(text=tr("wizard_searching"), text_color=theme.TEXT_MUTED)

        def run():
            found = discovery.discover()

            def show():
                self.find_btn.configure(state="normal")
                for child in self.found_box.winfo_children():
                    child.destroy()
                if not found:
                    self.found_box.pack_forget()
                    self.find_label.configure(text=tr("wizard_find_none"),
                                              text_color=theme.WARN)
                    return
                self.found_box.pack(fill="x", pady=(theme.PAD_S, 0))
                self.find_label.configure(
                    text=tr("wizard_find_count", count=len(found)), text_color=theme.TEXT_MUTED)
                for entry in found:
                    label = f"{entry['url']}"
                    if entry.get("version"):
                        label += f"  ·  v{entry['version']}"
                    if entry.get("device"):
                        label += f"  ·  {entry['device']}"
                    ctk.CTkButton(
                        self.found_box, text=label, height=32, anchor="w",
                        font=theme.font(12), corner_radius=theme.RADIUS_CONTROL,
                        fg_color=theme.SURFACE_2, border_width=1, border_color=theme.BORDER,
                        hover_color=theme.BORDER,
                        command=lambda u=entry["url"]: self._use_found(u)).pack(
                        fill="x", pady=2)
            self.app.post(show)

        threading.Thread(target=run, daemon=True).start()

    def _use_found(self, url: str) -> None:
        self.server_field.set(url)
        self.find_label.configure(text=url, text_color=theme.OK)
        if url.startswith("https://"):
            self._offer_pinning(url)

    def _offer_pinning(self, url: str) -> None:
        """https: look at the certificate and remember it (trust on first use)."""
        tr = self.app.tr
        from .. import api as apimod

        self.pin_label.configure(text=tr("wizard_pin_checking"), text_color=theme.TEXT_MUTED)
        self.pin_card.pack(fill="x", pady=(theme.PAD_S, 0))
        cfg = dict(self.cfg)
        cfgmod.parse_server_url(url, cfg)

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
                self.pin_label.configure(
                    text=tr("wizard_pin_remembered",
                            fingerprint=apimod.format_fingerprint(fingerprint)),
                    text_color=theme.OK)
            self.app.post(show)

        threading.Thread(target=run, daemon=True).start()

    def _test(self):
        tr = self.app.tr
        self.test_label.configure(text="…", text_color=theme.TEXT_MUTED)
        self.test_btn.configure(state="disabled")
        cfg = dict(self.cfg)
        cfgmod.parse_server_url(self.server_field.get(), cfg)
        token = self.token_field.get()
        base = cfgmod.server_url(cfg)
        if base.startswith("https://") and not self.cfg.get("tls_pin"):
            # https without a pin: remember the certificate before trusting it
            self._offer_pinning(base)

        def run():
            api = VozLabAPI(base, token, fingerprint=self.cfg.get("tls_pin", ""))
            try:
                try:
                    info = api.status()
                except ApiError as e:
                    if e.kind != "server":       # older server without /status
                        raise
                    info = api.health()
                model = info.get("whisper_model") or "?"
                device = info.get("device") or "?"
                msg = tr("wizard_test_ok", model=model, device=device)
                color = theme.OK
                if info.get("tls"):
                    msg += "  ·  " + tr("wizard_pinned_ok")
            except ApiError as e:
                kind = {"unreachable": "err_server_unreachable",
                        "bad_token": "err_bad_token",
                        "bad_cert": "err_bad_cert"}.get(e.kind)
                msg = tr(kind, error=e.detail) if kind else tr("err_generic", error=e.detail)
                color = theme.ERROR

            def done():
                self.test_label.configure(text=msg, text_color=color)
                self.test_btn.configure(state="normal")
            self.app.post(done)

        threading.Thread(target=run, daemon=True).start()

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
