"""VozLab application: tray icon + hotkey + recorder + overlay, all wired up."""

import os
import queue
import subprocess
import sys
import threading
import time

import customtkinter as ctk
import keyboard
import pyperclip

from . import APP_NAME, VERSION
from . import (audio, config as cfgmod, hotkeys, i18n, log, platform_info, profiles,
               tray, updater)
from .api import ApiError, VozLabAPI
from .ui import about as about_ui
from .ui import pill as pill_ui
from .ui import settings_window, theme
from .ui import wizard as wizard_ui

AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "run_vozlab.py")
    return f'"{sys.executable}" "{script}"'


def set_launch_at_login(enabled: bool) -> None:
    """Add/remove the app from the current user's startup (Windows only)."""
    if not sys.platform.startswith("win"):
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _autostart_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


def _beep(freq: int = 800, ms: int = 80) -> None:
    try:
        import winsound
        winsound.Beep(freq, ms)
    except Exception:
        pass


class VozLabApp:
    def __init__(self):
        self.cfg = cfgmod.load()
        self.tr = i18n.Translator(self.cfg.get("ui_language", "auto"))

        theme.setup(self.cfg.get("theme", "dark"))
        self.root = ctk.CTk()
        self.root.withdraw()
        self._ui_queue: queue.Queue = queue.Queue()
        log.set_secrets([self.cfg.get("token")])

        self.state = "idle"
        self.recorder: audio.Recorder | None = None
        self.api = VozLabAPI(cfgmod.server_url(self.cfg), self.cfg.get("token", ""),
                             fingerprint=self.cfg.get("tls_pin", ""))
        self._last_level_post = 0.0

        self.overlay = pill_ui.PillOverlay(self.root, self.cfg) if self.cfg.get("show_pill") else None
        if self.overlay:
            self.overlay.on_click = lambda: self.post(self.copy_last_text)

        self.hotkeys = hotkeys.HotkeyManager(
            on_down=self._hotkey_down,
            on_up=self._hotkey_up,
            on_escape=self._escape_pressed,
            debug_log=self._log if self.cfg.get("debug") else None,
        )
        self.hotkeys.set_hotkey(self.cfg.get("hotkey"))

        self.tray = tray.TrayIcon(
            tr=self.tr,
            on_dictate=lambda: self.post(self.toggle_dictation),
            on_settings=lambda: self.post(self.open_settings),
            on_calibrate=lambda: self.post(self.open_calibration),
            on_folder=lambda: self.post(self.open_config_folder),
            on_docs=lambda: self.post(self.open_docs),
            on_about=lambda: self.post(self.open_about),
            on_copy_last=lambda: self.post(self.copy_last_text),
            on_toggle_pause=lambda: self.post(self.toggle_pause),
            on_quit=lambda: self.post(self.quit_app),
        )
        self.settings_window = None
        self.wizard = None
        self.last_update_message = ""
        self.last_update_url = ""
        self.last_server_health = None
        self.last_text = ""
        self._pause_until = 0.0

    # -- thread marshalling --------------------------------------------------
    def post(self, fn) -> None:
        """Run fn on the Tk main thread."""
        self._ui_queue.put(fn)

    def _pump(self) -> None:
        while True:
            try:
                fn = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                log.log(f"UI callback error: {type(e).__name__}: {e}")
        self.root.after(40, self._pump)

    def _log(self, *args) -> None:
        log.debug(" ".join(str(a) for a in args))

    # -- startup -------------------------------------------------------------
    def run(self) -> None:
        log.log(f"{APP_NAME} {VERSION} starting (config: {cfgmod.config_path()})")
        self.root.after(40, self._pump)
        tray.TrayIcon.run_in_thread(self.tray)
        self.hotkeys.start()
        self.check_server_async()
        self.root.after(4000, lambda: self.check_for_updates(manual=False))

        needs_setup = (not self.cfg.get("first_run_done")
                       or not self.cfg.get("token")
                       or not self.cfg.get("server_host"))
        if needs_setup:
            self.open_wizard()

        self.root.mainloop()

    def check_server_async(self) -> None:
        def run():
            try:
                health = self.api.health()
                self.post(lambda: self._server_ok(health))
            except ApiError as err:
                # bind as a default arg: `e` is deleted when the except block ends
                self.post(lambda err=err: self._server_fail(err))
        threading.Thread(target=run, daemon=True).start()

    def _server_ok(self, health: dict) -> None:
        self.last_server_health = health
        self._log("server ok", health)
        server_version = health.get("version") or ""
        if server_version and updater.version_mismatch(server_version, VERSION):
            log.log(f"server is v{server_version} but this app is v{VERSION} — "
                    f"update the server: docker compose pull && docker compose up -d")
            if self.overlay:
                self.overlay.show(self.tr("err_server_version", server=server_version,
                                          client=VERSION), "error", auto_hide_ms=6000)
        self.tray.set_state("idle", tooltip=self.tr("tray_tooltip",
                                                    key=hotkeys.describe_hotkey(self.cfg.get("hotkey"))))

    def check_for_updates(self, manual: bool = False) -> None:
        """Ask GitHub for a newer release (only when enabled or user-initiated)."""
        if not manual and not self.cfg.get("check_updates"):
            return

        def run():
            try:
                release = updater.check()
            except updater.UpdateError as err:
                log.log(f"update check failed: {err}")
                if manual:
                    self.post(lambda err=err: self._report_update(
                        self.tr("update_check_failed", error=err)))
                return
            if release:
                log.log(f"update available: {release['version']} (you have {VERSION})")
                self.post(lambda: self._report_update(
                    self.tr("update_available", version=release["version"]),
                    url=release["url"]))
            elif manual:
                self.post(lambda: self._report_update(
                    self.tr("update_up_to_date", version=VERSION)))

        threading.Thread(target=run, daemon=True).start()

    def _report_update(self, message: str, url: str = "") -> None:
        """Show the result in the tray tooltip + overlay, and remember it."""
        self.last_update_message = message
        self.last_update_url = url
        log.log(message)
        if self.overlay:
            self.overlay.show(message, "info", auto_hide_ms=6000)

    def updater_script(self) -> str | None:
        """Path to update.ps1 when this copy was installed by deploy.ps1."""
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            return None
        candidate = os.path.join(base, "Programs", "VozLab", "update.ps1")
        return candidate if os.path.exists(candidate) else None

    def run_updater(self) -> None:
        """Launch the updater script; it reinstalls and restarts the app."""
        script = self.updater_script()
        if not script:
            return
        log.log(f"running updater: {script}")
        try:
            subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                              "-File", script], shell=False)
        except Exception as e:  # noqa: BLE001
            self._notify_error(self.tr("err_generic", error=e))
            return
        self.root.after(1500, self.quit_app)

    def _server_fail(self, err: ApiError) -> None:
        self.tray.set_state("offline", tooltip=self.tr("state_offline"))
        if self.overlay and self.cfg.get("first_run_done"):
            msg = self.tr("err_bad_token") if err.kind == "bad_token" else self.tr("err_server_unreachable")
            self.overlay.show(msg, "error", auto_hide_ms=5000)

    # -- dictation flow ------------------------------------------------------
    def toggle_dictation(self) -> None:
        if self.state == "idle":
            self._start_recording()
        elif self.state == "listening":
            self._stop_and_transcribe()

    def _hotkey_down(self) -> None:
        if self.state == "transcribing" or self.paused:
            return
        if self.cfg.get("hotkey_mode") == "toggle":
            self.post(self.toggle_dictation)
        elif self.state == "idle":
            self.post(self._start_recording)

    def _hotkey_up(self) -> None:
        if self.cfg.get("hotkey_mode") != "toggle" and self.state == "listening":
            self.post(self._stop_and_transcribe)

    def _escape_pressed(self) -> None:
        """Esc while recording throws the recording away (nothing is sent)."""
        if self.state == "listening":
            self.post(self._cancel_recording)

    def _cancel_recording(self) -> None:
        if self.state != "listening" or not self.recorder:
            return
        self.recorder.cancel()
        self.recorder = None
        self.state = "idle"
        self.tray.set_state("idle")
        if self.overlay:
            self.overlay.show(self.tr("state_cancelled"), "info", auto_hide_ms=1200)

    def copy_last_text(self) -> None:
        """Copy the previous dictation again (tray menu / pill click)."""
        if not self.last_text:
            return
        try:
            pyperclip.copy(self.last_text)
        except Exception as e:  # noqa: BLE001
            log.log(f"could not copy the last dictation: {e}")
            return
        if self.overlay:
            self.overlay.show(self.tr("copied"), "done", auto_hide_ms=1200)

    def toggle_pause(self) -> None:
        """Pause/resume dictation (tray menu). Handy during calls or meetings."""
        self._pause_until = 0.0 if self._pause_until else time.time() + 30 * 60
        paused = bool(self._pause_until)
        self.tray.set_paused(paused, self.tr("tray_paused") if paused
                             else self.tr("tray_tooltip",
                                          key=hotkeys.describe_hotkey(self.cfg.get("hotkey"))))
        if paused:
            log.log("dictation paused for 30 minutes")
            if self.overlay:
                self.overlay.show(self.tr("paused_until", minutes=30), "info",
                                  auto_hide_ms=2500)
            if self.state == "listening":
                self._cancel_recording()
        else:
            log.log("dictation resumed")

    @property
    def paused(self) -> bool:
        return bool(self._pause_until) and time.time() < self._pause_until

    def _start_recording(self) -> None:
        if self.state != "idle":
            return
        self.recorder = audio.Recorder(
            max_seconds=self.cfg.get("max_seconds", 60),
            silence_ms=self.cfg.get("silence_ms", 1200),
            silence_rms=self.cfg.get("silence_rms", 0.012),
            auto_stop=self.cfg.get("auto_stop", False),
            on_auto_stop=lambda: self.post(self._stop_and_transcribe),
            on_level=self._on_level,
            device=audio.resolve_device(self.cfg.get("input_device")),
        )
        try:
            self.recorder.start()
        except audio.AudioError as e:
            self.state = "idle"
            self._notify_error(self.tr("err_mic", error=e))
            return

        self.state = "listening"
        self._beep(880, 70)
        self.tray.set_state("listening")
        if self.overlay:
            self.overlay.show(self.tr("state_listening"), "listening")

    def _on_level(self, rms: float) -> None:
        """Feed the pill's meter — called from the audio thread (throttled)."""
        now = time.time()
        if now - self._last_level_post < 0.06:
            return
        self._last_level_post = now
        if self.overlay:
            self.post(lambda: self.overlay.set_level(rms))

    def _stop_and_transcribe(self) -> None:
        if self.state != "listening" or not self.recorder:
            return
        wav = self.recorder.stop()
        duration = self.recorder.duration()
        self.recorder = None
        self._beep(660, 70)

        if not wav:
            self.state = "idle"
            self.tray.set_state("idle")
            if self.overlay:
                self.overlay.hide()
            return
        if duration < self.cfg.get("min_seconds", 0.4):
            self.state = "idle"
            self.tray.set_state("idle")
            self._notify_error(self.tr("err_too_short"))
            return

        self.state = "transcribing"
        self.tray.set_state("transcribing")
        if self.overlay:
            self.overlay.transcribing(self.tr("state_transcribing"))

        # decide the writing style *now*: the app in the foreground is where the
        # text is about to land
        style = profiles.style_for_now(self.cfg)
        self._log(f"style for this dictation: {style}")
        threading.Thread(target=self._transcribe_thread, args=(wav, style),
                         daemon=True).start()

    def _transcribe_thread(self, wav: bytes, style: str = "default") -> None:
        t0 = time.time()
        try:
            out = self.api.transcribe(
                wav,
                cleanup=self.cfg.get("cleanup", True),
                language=self.cfg.get("language", "auto"),
                style=style,
            )
        except ApiError as err:
            self.post(lambda err=err: self._transcribe_failed(err))
            return
        text = (out.get("text") or "").strip()
        elapsed = time.time() - t0
        self.post(lambda: self._transcribe_done(text, elapsed, out))

    def _transcribe_failed(self, err: ApiError) -> None:
        self.state = "idle"
        self.tray.set_state("offline" if err.kind == "unreachable" else "idle")
        key = {"unreachable": "err_server_unreachable", "bad_token": "err_bad_token"}.get(err.kind)
        self._notify_error(self.tr(key, error=err.detail) if key else self.tr("err_generic", error=err.detail))

    def _transcribe_done(self, text: str, elapsed: float, out: dict) -> None:
        self.state = "idle"
        self.tray.set_state("idle")
        if not text:
            self._notify_error(self.tr("err_empty_transcript"))
            return
        raw = out.get("raw_text") or ""
        if out.get("cleanup_rejected"):
            log.log(f"server rejected the AI formatting ({out['cleanup_rejected']}); "
                    f"kept the raw transcript")
        # Privacy: the words you dictate are never written to disk. Only the
        # debug log (opt-in, in Settings → System) records them, and the log is
        # what you would hand over for support.
        log.debug(f"transcribed in {elapsed:.2f}s raw={raw!r} final={text!r}")
        log.log(f"dictation done ({elapsed:.2f}s, {len(text)} chars, "
                f"{out.get('language') or '?'}"
                + (", formatted" if out.get("cleanup_used") else ", raw") + ")")
        self.last_text = text
        self._paste_text(text)
        if self.overlay:
            # confirmation only — the dictated words never appear on screen
            self.overlay.show(self.tr("state_done"), "done", auto_hide_ms=1500)

    # -- output --------------------------------------------------------------
    def _paste_text(self, text: str) -> None:
        try:
            previous = pyperclip.paste() if self.cfg.get("restore_clipboard", True) else None
        except Exception:
            previous = None
        try:
            pyperclip.copy(text)
            time.sleep(0.05)
            keyboard.send(platform_info.paste_shortcut())
        except Exception as e:  # noqa: BLE001
            self._notify_error(self.tr("err_generic", error=e))
            return
        if previous is not None:
            def restore():
                time.sleep(1.0)
                try:
                    pyperclip.copy(previous)
                except Exception:
                    pass
            threading.Thread(target=restore, daemon=True).start()

    def _beep(self, freq: int, ms: int) -> None:
        if self.cfg.get("beeps", False):
            _beep(freq, ms)

    def _notify_error(self, msg: str) -> None:
        log.log(msg)
        self._beep(300, 300)
        if self.overlay:
            self.overlay.show(msg, "error", auto_hide_ms=5000)

    # -- windows -------------------------------------------------------------
    def open_settings(self) -> None:
        if self.settings_window is not None and self.settings_window.win.winfo_exists():
            self.settings_window.win.lift()
            return
        self.settings_window = settings_window.SettingsWindow(self, on_saved=self.check_server_async)

    def open_wizard(self) -> None:
        if self.wizard is not None and getattr(self.wizard, "win", None) and self.wizard.win.winfo_exists():
            self.wizard.win.lift()
            return
        self.wizard = wizard_ui.Wizard(self)

    def open_calibration(self) -> None:
        def captured(code, name):
            cfg = dict(self.cfg)
            cfg["hotkey"] = code
            self.apply_config(cfg)
            self.tray.set_state(self.state)
            if self.overlay:
                self.overlay.show(self.tr("wizard_hotkey_captured", name=name or str(code)),
                                  "done", auto_hide_ms=2500)

        settings_window.HotkeyCaptureDialog(self, captured)

    def open_config_folder(self) -> None:
        path = cfgmod.config_dir()
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa: S606
            else:
                log.log(path)
        except Exception as e:  # noqa: BLE001
            self._notify_error(self.tr("err_generic", error=e))

    def open_about(self) -> None:
        about_ui.AboutWindow(self)

    def open_docs(self) -> None:
        import webbrowser

        from . import diagnostics
        webbrowser.open(diagnostics.DOCS_URL)

    def apply_config(self, cfg: dict) -> None:
        self.cfg = cfg
        cfgmod.save(cfg)
        log.set_secrets([cfg.get("token")])
        self.tr.set_language(cfg.get("ui_language", "auto"))
        self.api = VozLabAPI(cfgmod.server_url(cfg), cfg.get("token", ""),
                             fingerprint=cfg.get("tls_pin", ""))
        self.hotkeys.set_hotkey(cfg.get("hotkey"))
        self.hotkeys.debug_log = self._log if cfg.get("debug") else None
        try:
            set_launch_at_login(cfg.get("launch_at_login", False))
        except Exception as e:  # noqa: BLE001
            log.log(f"autostart update failed: {e}")

        # the pill is painted with raw canvas colors: rebuild it on a theme change
        theme_before = theme.current()
        theme.apply(cfg.get("theme", "dark"))
        if theme.current() != theme_before and self.overlay is not None:
            self.overlay.destroy()
            self.overlay = None
        self.root.configure(fg_color=theme.BG)

        if cfg.get("show_pill") and self.overlay is None:
            self.overlay = pill_ui.PillOverlay(self.root, cfg)
        elif not cfg.get("show_pill") and self.overlay is not None:
            self.overlay.destroy()
            self.overlay = None
        if self.overlay:
            self.overlay.position = cfg.get("pill_position", "bottom-center")
            self.overlay.style = cfg.get("pill_style", "full")

        self.tray.set_state(self.state)
        log.log(f"config saved to {cfgmod.config_path()}")

    def quit_app(self) -> None:
        self.hotkeys.stop()
        if self.overlay:
            self.overlay.destroy()
        self.tray.stop()
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass


def main() -> None:
    log.setup(cfgmod.load().get("debug", False))   # must run before any output
    if "--version" in sys.argv:
        print(f"{APP_NAME} {VERSION}")
        return
    app = VozLabApp()
    try:
        app.run()
    except KeyboardInterrupt:
        app.quit_app()
    except Exception as e:  # noqa: BLE001 — log crashes instead of dying silently
        log.log(f"fatal: {type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    main()
