"""System tray icon, drawn programmatically (no asset files needed)."""

import threading

import pystray
from PIL import Image, ImageDraw

STATE_COLORS = {
    "idle": (59, 130, 246),        # blue
    "listening": (239, 68, 68),    # red
    "transcribing": (245, 158, 11),  # amber
    "error": (239, 68, 68),
    "offline": (107, 114, 128),    # gray
}


def make_icon(state: str = "idle", size: int = 64) -> Image.Image:
    """Draw a microphone glyph on a colored circle (or a pause glyph)."""
    if state == "paused":
        color = STATE_COLORS.get("idle", "#3B82F6")
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((2, 2, size - 2, size - 2), fill=color)
        bar_w = size * 0.14
        for offset in (-size * 0.14, size * 0.14):
            d.rounded_rectangle(
                (size / 2 + offset - bar_w / 2, size * 0.3,
                 size / 2 + offset + bar_w / 2, size * 0.7),
                radius=bar_w / 2, fill=(255, 255, 255, 255))
        return img

    color = STATE_COLORS.get(state, STATE_COLORS["idle"])
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, size - 2, size - 2), fill=color)

    # mic body
    cx = size / 2
    w = size * 0.22
    top, bottom = size * 0.22, size * 0.56
    d.rounded_rectangle((cx - w / 2, top, cx + w / 2, bottom),
                        radius=w / 2, fill=(255, 255, 255, 255))
    # mic cradle
    d.arc((cx - size * 0.22, bottom - size * 0.22, cx + size * 0.22, bottom + size * 0.22),
          start=0, end=180, fill=(255, 255, 255, 255), width=max(2, int(size * 0.05)))
    # stem
    d.line((cx, bottom + size * 0.2, cx, bottom + size * 0.28),
           fill=(255, 255, 255, 255), width=max(2, int(size * 0.05)))
    return img


class TrayIcon:
    """pystray wrapper. Menu callbacks are forwarded to the app."""

    def __init__(self, tr, on_dictate, on_settings, on_calibrate,
                 on_folder, on_about, on_quit, on_docs=None,
                 on_copy_last=None, on_toggle_pause=None):
        self.tr = tr
        self.state = "offline"
        self.paused = False
        on_docs = on_docs or (lambda: None)
        on_copy_last = on_copy_last or (lambda: None)
        on_toggle_pause = on_toggle_pause or (lambda: None)

        def paused(_item=None):
            return bool(self.paused)

        self._icon = pystray.Icon(
            "scribe",
            icon=make_icon(self.state),
            title=tr("app_name"),
            menu=pystray.Menu(
                pystray.MenuItem(lambda _i: tr("menu_dictate"), lambda *_: on_dictate(), default=True),
                pystray.MenuItem(lambda _i: tr("menu_copy_last"), lambda *_: on_copy_last()),
                pystray.Menu.SEPARATOR,
                # one Pause/Resume entry, enabled/disabled by the live state
                pystray.MenuItem(
                    lambda _i: tr("menu_resume") if self.paused
                    else tr("menu_pause", minutes=30),
                    lambda *_: on_toggle_pause(),
                    checked=lambda _i: self.paused,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(lambda _i: tr("menu_settings"), lambda *_: on_settings(),
                                 enabled=lambda _i: not paused()),
                pystray.MenuItem(lambda _i: tr("menu_calibrate"), lambda *_: on_calibrate(),
                                 enabled=lambda _i: not paused()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(lambda _i: tr("menu_docs"), lambda *_: on_docs()),
                pystray.MenuItem(lambda _i: tr("menu_folder"), lambda *_: on_folder()),
                pystray.MenuItem(lambda _i: tr("menu_about"), lambda *_: on_about()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(lambda _i: tr("menu_quit"), lambda *_: on_quit()),
            ),
        )

    def run(self) -> None:
        self._icon.run()

    def set_state(self, state: str, tooltip: str | None = None) -> None:
        self.state = state
        try:
            self._icon.icon = make_icon(state)
            if tooltip:
                self._icon.title = tooltip
            self._icon.update_menu()
        except Exception:
            pass

    def set_paused(self, paused: bool, tooltip: str | None = None) -> None:
        self.paused = bool(paused)
        self.set_state("paused" if self.paused else "idle", tooltip)

    def stop(self) -> None:
        try:
            self._icon.stop()
        except Exception:
            pass

    @staticmethod
    def run_in_thread(tray: "TrayIcon") -> threading.Thread:
        t = threading.Thread(target=tray.run, daemon=True)
        t.start()
        return t
