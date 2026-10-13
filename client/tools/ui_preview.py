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

from vozlab import config as cfgmod  # noqa: E402
from vozlab import i18n  # noqa: E402
from vozlab.api import VozLabAPI  # noqa: E402
from vozlab.ui import about, pill, settings_window, theme, wizard  # noqa: E402

SHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "..", "docs", "images")

DEMO_CONFIG = {
    "server_host": "192.168.0.23", "server_port": 8092,
    "token": "3xKm9Qr2Lp8VtHzWnBc4YeSfUa1DgJ6o",
    "hotkey": 285, "hotkey_mode": "hold", "auto_stop": False,
    "cleanup": True, "language": "auto", "beeps": True,
    "restore_clipboard": True, "show_pill": True, "pill_position": "bottom-center",
    "ui_language": "auto", "launch_at_login": True, "debug": False,
    "first_run_done": True,
}


class FakeApp:
    """Just enough of VozLabApp for the windows to render."""

    def __init__(self, lang: str = "auto"):
        theme.setup()
        self.cfg = dict(cfgmod.DEFAULTS)
        self.cfg.update(DEMO_CONFIG)
        self.tr = i18n.Translator(lang)
        self.root = ctk.CTk()
        self.root.withdraw()
        self.api = VozLabAPI("http://192.168.0.23:8092", "demo")
        self.settings_window = None
        self.wizard = None
        self.overlay = None

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
