"""Global hotkey handling.

Important Windows detail: the low-level keyboard hook callback must return in a
few milliseconds, otherwise Windows silently unregisters the hook. So the hook
here only pushes events onto a queue; a worker thread does the real work.
"""

import queue
import threading

import keyboard

# Right ctrl is the default suggestion (scan code 285 = language independent)
DEFAULT_HOTKEY_CODE = 285

# Localized names accepted as "right ctrl" fallbacks
RIGHT_CTRL_ALIASES = {
    "right ctrl", "right control", "ctrl derecha", "control derecho",
    "ctrl droit", "control droit", "rechte strg", "strg rechts",
    "ctrl direito", "control direito", "ctrl destro", "control destro",
}


def describe_hotkey(hotkey) -> str:
    if hotkey is None:
        return "(not set)"
    if isinstance(hotkey, int) or str(hotkey).isdigit():
        if int(hotkey) == DEFAULT_HOTKEY_CODE:
            return "right Ctrl"
        return f"scan code {hotkey}"
    return str(hotkey)


class HotkeyManager:
    """Watches one hotkey via keyboard.hook and reports down/up on a worker thread."""

    def __init__(self, on_down=None, on_up=None, debug_log=None):
        self.on_down = on_down
        self.on_up = on_up
        self.debug_log = debug_log

        self.hotkey_code = None      # int scan code
        self.hotkey_name = None      # str name (alternative matching)
        self._queue = queue.Queue()
        self._worker = None
        self._running = False

    # -- configuration -------------------------------------------------------
    def set_hotkey(self, hotkey) -> None:
        if hotkey is None:
            self.hotkey_code, self.hotkey_name = None, None
        elif isinstance(hotkey, int) or str(hotkey).isdigit():
            self.hotkey_code, self.hotkey_name = int(hotkey), None
        else:
            self.hotkey_code, self.hotkey_name = None, str(hotkey)

    def matches(self, event) -> bool:
        name = (getattr(event, "name", "") or "").lower()
        if self.hotkey_code is not None:
            return event.scan_code == self.hotkey_code
        if self.hotkey_name is None:
            # nothing configured yet: accept a right-ctrl press so the user can
            # start dictating before going through calibration
            return name in RIGHT_CTRL_ALIASES
        if name == self.hotkey_name.lower():
            return True
        # configured name and event name are two spellings of the same key
        # (e.g. config says "right ctrl" but Windows reports "ctrl derecha")
        if self.hotkey_name.lower() in RIGHT_CTRL_ALIASES and name in RIGHT_CTRL_ALIASES:
            return True
        return False

    # -- lifecycle -----------------------------------------------------------
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._run_worker, daemon=True)
        self._worker.start()
        keyboard.hook(self._on_event)

    def stop(self) -> None:
        self._running = False
        try:
            keyboard.unhook_all()
        except Exception:
            pass

    def _on_event(self, event) -> None:
        """Runs on the keyboard hook thread — must stay fast."""
        if self.debug_log:
            self.debug_log(f"key name={event.name!r} scan={event.scan_code} type={event.event_type}")
        if self.matches(event):
            self._queue.put(event.event_type)

    def _run_worker(self) -> None:
        while self._running:
            try:
                event_type = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                if event_type == "down" and self.on_down:
                    self.on_down()
                elif event_type == "up" and self.on_up:
                    self.on_up()
            except Exception as e:  # keep the worker alive no matter what
                if self.debug_log:
                    self.debug_log(f"hotkey worker error: {type(e).__name__}: {e}")

    # -- calibration ---------------------------------------------------------
    @staticmethod
    def capture_next_key(timeout: float = 30.0) -> tuple[int, str] | None:
        """Block until the user presses a key; return (scan_code, name)."""
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            event = keyboard.read_event(suppress=False)
            if event.event_type == "down":
                return event.scan_code, (event.name or "")
        return None
