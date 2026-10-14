"""Floating status pill — rounded, animated, always on top.

Raw Tk canvas (not CustomTkinter) so it can be borderless with rounded corners
and animated at 25 fps. On Windows `-transparentcolor` makes the corners really
transparent; elsewhere it degrades to a dark rectangle.
"""

import time
import tkinter as tk
import tkinter.font as tkfont

from . import theme

FRAME_MS = 40
BAR_COUNT = 4
TEXT_SIZE = 12
# Tk's default scaling is 96 dpi / 72 points; everything below is laid out in
# these "design pixels" and multiplied by the live DPI factor at draw time.
BASE_DPI = 96.0


def _ellipsize(text: str, max_px: int, measure) -> str:
    """Shrink `text` until `measure(text)` fits in `max_px` (adds … when cut)."""
    if max_px <= 0:
        return ""
    if measure(text) <= max_px:
        return text
    out = text
    while out and measure(out + "…") > max_px:
        out = out[:-1]
    return (out + "…") if out else ""


def _rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kwargs):
    """Draw a rounded rectangle using a smoothed polygon."""
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class PillOverlay:
    HEIGHT = 48
    MIN_WIDTH = 200
    MIN_WIDTH_MINIMAL = 120
    MAX_WIDTH = 540

    def __init__(self, root: tk.Tk, cfg: dict):
        self.root = root
        self.position = cfg.get("pill_position", "bottom-center")
        self.style = cfg.get("pill_style", "full")       # full | minimal
        self._state = "info"
        self._text = ""
        self._shown_text = ""
        self._visible = False
        self._alpha = 0.0
        self._fade_job = None
        self._anim_job = None
        self._hide_job = None
        self._timer_job = None
        self._started_at = 0.0
        self._levels = [0.0] * BAR_COUNT
        self._phase = 0
        self.on_click = None

        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        try:
            self.window.attributes("-alpha", 0.0)
            self.window.attributes("-transparentcolor", theme.PILL_TRANSPARENT)
            self._transparent = True
        except tk.TclError:
            self._transparent = False

        self.canvas = tk.Canvas(self.window, bg=theme.PILL_TRANSPARENT,
                                highlightthickness=0, bd=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", lambda _e: self._clicked())
        # real font metrics (and DPI) drive the layout, so the pill fits its text
        # on a 4K scaling laptop exactly like on a 100% desktop monitor
        self._font = tkfont.Font(family=theme.FONT_FAMILY, size=TEXT_SIZE,
                                 weight="normal")
        self.window.withdraw()

    # -- public API ----------------------------------------------------------
    def _clicked(self) -> None:
        """Clicking the pill copies the last dictation (handy when the paste missed)."""
        if self.on_click:
            self.on_click()

    def show(self, text: str, state: str = "info", auto_hide_ms: int | None = None) -> None:
        self._cancel(self._hide_job)
        self._hide_job = None
        self._state = state
        self._text = text or ""
        if state == "listening" and not self._started_at:
            self._started_at = time.time()
        elif state != "listening":
            self._started_at = 0.0
        self._render()
        self._place()
        if not self._visible:
            self.window.deiconify()
            self.window.lift()
            self._visible = True
            self._fade(0.96)
        self._start_animation()
        if auto_hide_ms:
            self._hide_job = self.root.after(auto_hide_ms, self.hide)

    def transcribing(self, text: str) -> None:
        self.show(text, "transcribing")

    def set_level(self, rms: float) -> None:
        """Feed the microphone level (RMS) for the live meter."""
        level = min(1.0, max(0.0, rms / 0.08))
        self._levels = self._levels[1:] + [level]

    def hide(self) -> None:
        self._cancel(self._hide_job)
        self._hide_job = None
        if not self._visible:
            return
        self._stop_animation()
        self._fade(0.0, then=self._after_fade_out)

    def destroy(self) -> None:
        self._cancel(self._fade_job)
        self._stop_animation()
        try:
            self.window.destroy()
        except tk.TclError:
            pass

    # -- drawing -------------------------------------------------------------
    def _unit(self) -> float:
        """Pixels per design pixel (1.0 at 96 dpi, 1.5 at 150% scaling)."""
        try:
            scaling = float(self.window.tk.call("tk", "scaling"))
        except Exception:  # noqa: BLE001 — never let a metrics error hide the pill
            return 1.0
        return min(3.0, max(1.0, scaling * 72.0 / BASE_DPI))

    def _text_left(self, u: float) -> int:
        """Where the label starts (after the dot, and the meter for `full`)."""
        return int(round((38 if self.style == "minimal" else 81) * u))

    def _text_pad(self, u: float) -> int:
        return int(round((12 if self.style == "minimal" else 16) * u))

    def _measure(self) -> tuple[int, int]:
        u = self._unit()
        text_left = self._text_left(u)
        pad = self._text_pad(u)
        min_width = int(round((self.MIN_WIDTH_MINIMAL if self.style == "minimal"
                               else self.MIN_WIDTH) * u))
        max_width = int(round(self.MAX_WIDTH * u))

        text = self._display_text()
        width = max(min_width, min(max_width, text_left + self._font.measure(text) + pad))
        # the label is one line: trim it (with …) instead of letting it clip
        self._shown_text = _ellipsize(text, width - text_left - pad, self._font.measure)
        height = max(int(round(self.HEIGHT * u)),
                     self._font.metrics("linespace") + int(round(12 * u)))
        return width, height

    def _display_text(self) -> str:
        return self._text + self._elapsed_suffix()

    def _elapsed_suffix(self) -> str:
        """Show how long we have been listening (long notes need reassurance)."""
        if self._state != "listening" or not self._started_at:
            return ""
        seconds = int(time.time() - self._started_at)
        return f"  {seconds}s" if seconds >= 3 else ""

    def _render(self) -> None:
        w, h = self._measure()
        self.canvas.configure(width=w, height=h)
        self.canvas.delete("all")

        u = self._unit()
        cy = h / 2

        _rounded_rect(self.canvas, 1, 1, w - 1, h - 1, h / 2 - 1,
                      fill=theme.PILL_BG, outline=theme.PILL_BORDER, width=1)

        color = theme.STATE_COLORS.get(self._state, theme.ACCENT)
        # status dot
        self.canvas.create_oval(17 * u, cy - 5 * u, 27 * u, cy + 5 * u,
                                fill=color, outline="")

        text = self._shown_text

        if self.style == "minimal":
            self.canvas.create_text(38 * u, cy, text=text, anchor="w",
                                    fill=theme.TEXT, font=theme.font_tuple(TEXT_SIZE))
            return

        # level meter / activity indicator
        x = 39 * u
        if self._state == "listening":
            for i, level in enumerate(self._levels):
                bar_h = (6 + level * 22) * u
                self.canvas.create_rectangle(
                    x + i * 7 * u, cy - bar_h / 2, x + i * 7 * u + 4 * u, cy + bar_h / 2,
                    fill=color, outline="")
        elif self._state == "transcribing":
            for i in range(3):
                lit = (self._phase + i) % 6 < 3
                r = (3.2 if lit else 2.2) * u
                cx = x + i * 10 * u + 3 * u
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                        fill=color if lit else theme.TEXT_FAINT, outline="")
        else:
            self.canvas.create_rectangle(x, cy - 7 * u, x + 4 * u, cy + 7 * u,
                                         fill=color, outline="")

        self.canvas.create_text(81 * u, cy, text=text, anchor="w",
                                fill=theme.TEXT, font=theme.font_tuple(TEXT_SIZE))

    def _start_animation(self) -> None:
        if self._anim_job or self._state not in ("listening", "transcribing"):
            return
        self._tick()

    def _stop_animation(self) -> None:
        self._cancel(self._anim_job)
        self._anim_job = None

    def _tick(self) -> None:
        if not self._visible or self._state not in ("listening", "transcribing"):
            self._anim_job = None
            return
        self._phase += 1
        if self._state == "listening":
            # decay so the meter falls back smoothly between buffers
            self._levels = [max(0.0, lvl * 0.72) for lvl in self._levels]
        self._render()
        self._anim_job = self.root.after(FRAME_MS, self._tick)

    # -- window --------------------------------------------------------------
    def _place(self) -> None:
        self.window.update_idletasks()
        w, h = self._measure()
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        margin = 90
        if self.position == "top-right":
            x, y = sw - w - 40, 40
        elif self.position == "bottom-right":
            x, y = sw - w - 40, sh - h - margin
        else:
            x, y = (sw - w) // 2, sh - h - margin
        self.window.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")

    def _after_fade_out(self) -> None:
        if self._alpha <= 0.01:
            self._visible = False
            self.window.withdraw()

    def _fade(self, target: float, then=None) -> None:
        self._cancel(self._fade_job)

        def step():
            delta = 0.12 if target > self._alpha else -0.12
            self._alpha = max(0.0, min(0.96, self._alpha + delta))
            try:
                self.window.attributes("-alpha", self._alpha)
            except tk.TclError:
                return
            if abs(self._alpha - target) < 0.06:
                if then:
                    then()
                self._fade_job = None
                return
            self._fade_job = self.root.after(16, step)

        step()

    @staticmethod
    def _cancel(job) -> None:
        if job:
            try:
                job.after_cancel(job)
            except Exception:
                pass
