"""Floating status pill (Wispr-Flow style) — borderless always-on-top window."""

import tkinter as tk

BG = "#111827"
FG = "#f9fafb"
COLORS = {
    "listening": "#ef4444",
    "transcribing": "#f59e0b",
    "done": "#10b981",
    "error": "#ef4444",
    "info": "#3b82f6",
}


class PillOverlay:
    """Small status pill: shows state text, optionally the transcribed preview."""

    def __init__(self, root: tk.Tk, cfg: dict):
        self.root = root
        self.position = cfg.get("pill_position", "bottom-center")
        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        try:
            self.window.attributes("-alpha", 0.94)
        except tk.TclError:
            pass
        self.window.configure(bg=BG)

        self.dot = tk.Label(self.window, text="●", bg=BG, fg=COLORS["listening"],
                            font=("Segoe UI", 12))
        self.dot.pack(side="left", padx=(12, 6), pady=8)
        self.label = tk.Label(self.window, text="", bg=BG, fg=FG,
                              font=("Segoe UI", 10), justify="left", wraplength=420)
        self.label.pack(side="left", padx=(0, 14), pady=8)
        self.window.withdraw()
        self._hide_job = None

    # -- placement -----------------------------------------------------------
    def _place(self) -> None:
        self.window.update_idletasks()
        w = max(self.window.winfo_width(), 120)
        h = self.window.winfo_height()
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        margin = 80
        if self.position == "top-right":
            x, y = sw - w - 40, 40
        elif self.position == "bottom-right":
            x, y = sw - w - 40, sh - h - margin
        else:  # bottom-center
            x, y = (sw - w) // 2, sh - h - margin
        self.window.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    # -- public API ----------------------------------------------------------
    def show(self, text: str, state: str = "info", auto_hide_ms: int | None = None) -> None:
        self._cancel_hide()
        self.dot.configure(fg=COLORS.get(state, COLORS["info"]))
        self.label.configure(text=text)
        self._place()
        self.window.deiconify()
        self.window.lift()
        if auto_hide_ms:
            self._hide_job = self.root.after(auto_hide_ms, self.hide)

    def transcribing(self, text: str) -> None:
        self.show(text, "transcribing")

    def hide(self) -> None:
        self._cancel_hide()
        self.window.withdraw()

    def destroy(self) -> None:
        try:
            self.window.destroy()
        except tk.TclError:
            pass

    def _cancel_hide(self) -> None:
        if self._hide_job:
            try:
                self.root.after_cancel(self._hide_job)
            except Exception:
                pass
            self._hide_job = None
