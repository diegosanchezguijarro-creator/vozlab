#!/usr/bin/env python3
"""Render every VozLab window with demo data.

Useful for developing/screenshotting the UI without a Windows machine:

    python tools/ui_preview.py            # English
    python tools/ui_preview.py --lang es  # Spanish
    python tools/ui_preview.py --shot     # also save PNGs (needs `import`, ImageMagick)

On a headless box run it under a virtual display:

    Xvfb :99 -screen 0 1280x900x24 & DISPLAY=:99 python tools/ui_preview.py --shot
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customtkinter as ctk  # noqa: E402

from vozlab import VERSION  # noqa: E402
from vozlab import config as cfgmod  # noqa: E402
from vozlab import i18n  # noqa: E402
from vozlab.ui import about, pill, settings_window, theme, wizard  # noqa: E402

SHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "..", "docs", "images")

DEMO_CONFIG = {
    "server_host": "192.168.0.23", "server_port": 8092,
    "token": "demo-token-only-for-screenshots",
    "hotkey": 285, "hotkey_mode": "hold", "auto_stop": False,
    "cleanup": True, "language": "auto", "beeps": True,
    "restore_clipboard": True, "show_pill": True, "pill_position": "bottom-center",
    "ui_language": "auto", "launch_at_login": True, "debug": False,
    "style": "default", "per_app_profiles": True,
    "vocabulary": ["VozLab", "Diego", "qwen2.5"],
    "first_run_done": True,
}


class DemoServerAPI:
    """Stands in for a live server when rendering screenshots.

    The preview runs on a workstation with no VozLab server (or, worse, with one
    that answers 401 to the demo token), which used to put a red "token was
    rejected" banner in every screenshot. This returns a realistic connected
    server instead, so the images show the product working.
    """

    def __init__(self, *args, **kwargs):
        pass

    def health(self):
        return {"ok": True, "version": VERSION, "api": 1}

    def status(self):
        return {
            "name": "vozlab", "version": VERSION, "api": 1,
            "whisper_model": "small", "language": "auto",
            "cleanup": True, "cleanup_model": "qwen2.5:7b-instruct",
            "device": "cuda", "uptime_s": 3 * 3600 + 900, "requests": 248,
            "whisper_models_cached": ["faster-whisper-small", "faster-whisper-base"],
            "ollama_models": ["qwen2.5:7b-instruct", "llama3.1:8b"],
            "gpu": {"name": "NVIDIA GeForce RTX 4060", "memory_total_mb": 8188,
                    "memory_used_mb": 4820},
            "reloading": False, "tls": False,
            "auth": {"role": "device", "device": "diego-laptop"},
        }

    def get_settings(self):
        return {"vocabulary": ["VozLab", "Diego"], "styles": ["bullets", "casual", "concise",
                                                             "default", "formal"]}

    def logs(self, lines: int = 100):
        return [
            "2026-10-13 18:02:11 loaded 'small' on cuda (int8_float16) in 1.6s",
            "2026-10-13 18:02:11 cleanup model warm in 0.2s",
            "2026-10-13 18:02:14 discovery responder listening on udp/8093",
            "2026-10-13 18:04:52 settings updated: {'style': 'formal'}",
            "2026-10-13 18:07:03 cleanup rejected (invented 4 words (>2)); keeping raw transcript",
            "2026-10-13 18:11:40 self-test: 0.21s whisper, 0.24s cleanup",
        ][-lines:]

    def list_tokens(self):
        return [
            {"id": "a1b2c3d4", "name": "diego-laptop", "created": 1791800000,
             "last_used": 1791908000, "last_ip": "192.168.0.42", "age_days": 1.2, "used": True},
            {"id": "e5f6a7b8", "name": "office-desktop", "created": 1791000000,
             "last_used": None, "last_ip": None, "age_days": 10.5, "used": False},
        ]

    def patch_settings(self, changes):
        return {"ok": True, "applied": changes, "reloading": False}

    def preload_model(self, model=None):
        return {"ok": True, "model": model or "qwen2.5:7b-instruct", "seconds": 2.8}

    def self_test(self):
        return {"ok": True, "text": "If you can read this, the server works.",
                "raw_text": "VozLab self test. If you can read this, the server works.",
                "language": "en", "cleanup_error": None, "device": "cuda",
                "timings": {"whisper_s": 0.21, "cleanup_s": 0.24, "total_s": 0.45}}

    def transcribe(self, wav, cleanup=True, language="auto", style=""):
        return {"text": "Remind me to call the client on Thursday.",
                "raw_text": "remind me to call the client on thursday",
                "cleanup_used": True, "cleanup_rejected": None, "style": style or "default",
                "language": "en", "timings": {"whisper_s": 0.31, "cleanup_s": 0.26,
                                              "total_s": 0.57}}

    def create_token(self, name):
        return {"id": "99887766", "name": name, "token": "demo-token-shown-once"}

    def revoke_token(self, token_id):
        return {"ok": True, "revoked": token_id, "remaining": 1}


class FakeApp:
    """Just enough of VozLabApp for the windows to render."""

    def __init__(self, lang: str = "auto"):
        theme.setup()
        self.cfg = dict(cfgmod.DEFAULTS)
        self.cfg.update(DEMO_CONFIG)
        self.tr = i18n.Translator(lang)
        self.root = ctk.CTk()
        self.root.withdraw()
        self.api = DemoServerAPI()
        self.settings_window = None
        self.wizard = None
        self.overlay = None
        self.last_update_message = ""
        self.last_update_url = ""
        self.last_server_health = None
        self.last_text = ""
        # the windows build their own client: hand them the demo server
        settings_window.VozLabAPI = DemoServerAPI
        wizard.VozLabAPI = DemoServerAPI

    def post(self, fn):
        fn()          # synchronous in preview mode

    def apply_config(self, cfg):
        self.cfg = cfg

    def open_config_folder(self):
        pass

    def updater_script(self):
        return None

    def run_updater(self):
        print("  [preview] run_updater()")

    def check_for_updates(self, manual: bool = False):
        print(f"  [preview] check_for_updates(manual={manual})")


def screenshot(name: str, prefix: str = "") -> None:
    path = os.path.join(SHOT_DIR, f"{prefix}{name}.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # no shell: the path is passed as an argument, not interpolated into a command
    try:
        rc = subprocess.run(["import", "-window", "root", path],
                            capture_output=True, timeout=30).returncode
    except (OSError, subprocess.SubprocessError):
        rc = 1
    print(f"  {'saved' if rc == 0 else 'FAILED'} {path}")
    return rc


def sync(root) -> None:
    """Flush pending redraws so a screenshot captures the current frame."""
    try:
        root.update_idletasks()
        root.update()
    except Exception:
        pass


def main() -> None:
    lang = "auto"
    if "--lang" in sys.argv:
        lang = sys.argv[sys.argv.index("--lang") + 1]
    prefix = ""
    if "--prefix" in sys.argv:
        prefix = sys.argv[sys.argv.index("--prefix") + 1]
    take_shots = "--shot" in sys.argv

    app = FakeApp(lang)
    print(f"Rendering VozLab UI (language: {app.tr.language})")
    shot = lambda name: screenshot(name, prefix) if take_shots else None

    # 1. settings window — one screenshot per tab
    app.settings_window = settings_window.SettingsWindow(app)
    settings = app.settings_window
    settings._set_status(True, app.tr("status_connected", model="small", device="cuda"))
    settings.test_label.configure(
        text=app.tr("wizard_test_ok", model="small", device="cuda"), text_color=theme.OK)

    tabs = [app.tr(k) for k in ("tab_dictation", "tab_audio", "tab_formatting",
                                "tab_server", "tab_appearance", "tab_system")]
    names = ["settings-dictation", "settings-audio", "settings-formatting",
             "settings-server", "settings-appearance", "settings-system"]

    if take_shots:
        delay = 900
        for tab, name in zip(tabs, names):
            def pick(t=tab, n=name, d=delay):
                settings.tabs.set(t)
                settings.win.lift()
                sync(app.root)
                shot(n)
            app.root.after(delay, pick)
            delay += 900
        app.root.after(delay + 600, settings.win.destroy)
    else:
        app.root.after(2200, settings.win.destroy)

    # 2. wizard (all three steps)
    def wizard_steps():
        w = wizard.Wizard(app)
        app.wizard = w
        if take_shots:
            app.root.after(700, lambda: shot("wizard-server"))
        app.root.after(1600, lambda: (setattr(w, "step", 1), w._render()))
        if take_shots:
            app.root.after(2100, lambda: shot("wizard-key"))
        app.root.after(3000, lambda: (setattr(w, "step", 2), w._render()))
        if take_shots:
            app.root.after(3500, lambda: shot("wizard-mic"))
        app.root.after(4400, w.win.destroy)

    # 3. about
    def about_window():
        a = about.AboutWindow(app)
        if take_shots:
            app.root.after(700, lambda: shot("about"))
        app.root.after(1700, a.win.destroy)

    # 4. the pills
    def pills():
        p = pill.PillOverlay(app.root, app.cfg)
        app.overlay = p
        p.show(app.tr("state_listening"), "listening")
        for i, level in enumerate([0.03, 0.06, 0.02, 0.05]):
            p.set_level(level)
        if take_shots:
            app.root.after(600, lambda: shot("pill-listening"))
        app.root.after(1200, lambda: p.transcribing(app.tr("state_transcribing")))
        if take_shots:
            app.root.after(1800, lambda: shot("pill-transcribing"))
        app.root.after(2400, lambda: p.show(
            "Recuerdame llamar al cliente el jueves.", "done"))
        if take_shots:
            app.root.after(3000, lambda: shot("pill-done"))
        app.root.after(3600, p.destroy)

    app.root.after(9000, wizard_steps)
    app.root.after(13600, about_window)
    app.root.after(15600, pills)
    app.root.after(19800, app.root.quit)
    app.root.mainloop()
    print("done")


if __name__ == "__main__":
    main()
