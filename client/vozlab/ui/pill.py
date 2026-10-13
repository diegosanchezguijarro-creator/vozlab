"""Floating status pill — rounded, animated, always on top.

Raw Tk canvas (not CustomTkinter) so it can be borderless with rounded corners
and animated at 25 fps. On Windows `-transparentcolor` makes the corners really
transparent; elsewhere it degrades to a dark rectangle.
"""

import tkinter as tk

from . import theme

FRAME_MS = 40
BAR_COUNT = 4


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
    MAX_WIDTH = 540

    def __init__(self, root: tk.Tk, cfg: dict):
        self.root = root
        self.position = cfg.get("pill_position", "bottom-center")
        self._state = "info"
        self._text = ""
        self._visible = False
        self._alpha = 0.0
        self._fade_job = None
        self._anim_job = None
        self._hide_job = None
        self._levels = [0.0] * BAR_COUNT
        self._phase = 0

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
        self.window.withdraw()

    # -- public API ----------------------------------------------------------
    def show(self, text: str, state: str = "info", auto_hide_ms: int | None = None) -> None:
        self._cancel(self._hide_job)
        self._hide_job = None
        self._state = state
        self._text = text or ""
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
    def _measure(self) -> tuple[int, int]:
        width = 22 + 12 + 10 + (BAR_COUNT * 7 + 12) + 14 + len(self._text) * 6.6
        width = int(max(self.MIN_WIDTH, min(self.MAX_WIDTH, width)))
        return width, self.HEIGHT

    def _render(self) -> None:
        w, h = self._measure()
        self.canvas.configure(width=w, height=h)
        self.canvas.delete("all")

        _rounded_rect(self.canvas, 1, 1, w - 1, h - 1, h / 2 - 1,
                      fill=theme.PILL_BG, outline=theme.PILL_BORDER, width=1)

        color = theme.STATE_COLORS.get(self._state, theme.ACCENT)
        # status dot
        self.canvas.create_oval(17, h / 2 - 5, 27, h / 2 + 5, fill=color, outline="")

        # level meter / activity indicator
        x = 39
        if self._state == "listening":
            for i, level in enumerate(self._levels):
                bar_h = 6 + int(level * 22)
                self.canvas.create_rectangle(
                    x + i * 7, h / 2 - bar_h / 2, x + i * 7 + 4, h / 2 + bar_h / 2,
                    fill=color, outline="")
        elif self._state == "transcribing":
            for i in range(3):
                lit = (self._phase + i) % 6 < 3
                r = 3.2 if lit else 2.2
                cx = x + i * 10 + 3
                self.canvas.create_oval(cx - r, h / 2 - r, cx + r, h / 2 + r,
                                        fill=color if lit else theme.TEXT_FAINT, outline="")
        else:
            self.canvas.create_rectangle(x, h / 2 - 7, x + 4, h / 2 + 7, fill=color, outline="")

        text_x = x + max(BAR_COUNT * 7, 30) + 12
        self.canvas.create_text(text_x, h / 2, text=self._text, anchor="w",
                                fill=theme.TEXT, font=theme.font_tuple(12))

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
