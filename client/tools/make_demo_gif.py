#!/usr/bin/env python3
"""Render an animated demo GIF of the VozLab status pill.

    Xvfb :99 -screen 0 1280x800x24 &
    DISPLAY=:99 python tools/make_demo_gif.py          # -> docs/images/demo.gif

The frames come from the real UI (the same PillOverlay the app uses), so the
GIF always matches the product. Background is made transparent for GitHub.
"""

import os
import subprocess
import sys
import tempfile
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customtkinter as ctk  # noqa: E402
from PIL import Image  # noqa: E402

from vozlab import i18n  # noqa: E402
from vozlab.ui import pill as pill_mod  # noqa: E402
from vozlab.ui import theme  # noqa: E402

SCREEN = (1280, 800)
PILL_CENTER = (SCREEN[0] // 2, SCREEN[1] - 150)
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "..", "docs", "images", "demo.gif")
BACKDROP = (13, 17, 23)           # GitHub dark background, so the pill pops


def grab(path: str) -> None:
    subprocess.run(["import", "-window", "root", path], check=True)


def crop(path: str, box: tuple[int, int, int, int]) -> Image.Image:
    img = Image.open(path).convert("RGB").crop(box).convert("RGBA")
    data = []
    for r, g, b, _a in img.getdata():
        if r < 12 and g < 12 and b < 16:      # desktop / transparent key colour
            data.append((0, 0, 0, 0))
        else:
            data.append((r, g, b, 255))
    img.putdata(data)
    return img


def main() -> None:
    theme.setup()
    root = ctk.CTk()
    root.withdraw()
    root.geometry(f"{SCREEN[0]}x{SCREEN[1]}+0+0")
    tr = i18n.Translator("en")
    cfg = {"pill_position": "bottom-center"}
    overlay = pill_mod.PillOverlay(root, cfg)
    overlay.position = "bottom-center"
    # keep the pill inside the crop box regardless of the real screen size
    overlay._place = lambda: overlay.window.geometry(
        f"{overlay._measure()[0]}x{overlay._measure()[1]}"
        f"+{SCREEN[0] // 2 - overlay._measure()[0] // 2}+{SCREEN[1] - 150}")

    tmp = tempfile.mkdtemp(prefix="vozlab-gif-")
    frames: list[Image.Image] = []
    durations: list[int] = []
    box: list[tuple[int, int, int, int]] = []

    def capture(milliseconds: int, repeats: int = 1) -> None:
        for _ in range(repeats):
            root.update_idletasks()
            root.update()
            time.sleep(0.06)
            if not box:
                # crop tightly around the pill, discovered from its geometry
                geo = overlay.window.winfo_geometry()      # e.g. 240x48+520+650
                size, _, pos = geo.partition("+")
                width, _, height = size.partition("x")
                px, _, py = pos.partition("+")
                pad = 8
                box.append((int(px) - pad, int(py) - pad,
                            int(px) + int(width) + pad, int(py) + int(height) + pad))
            path = os.path.join(tmp, f"frame-{len(frames):03d}.png")
            grab(path)
            frames.append(crop(path, box[0]))
            durations.append(milliseconds)

    # 1. listening — the level meter reacts
    overlay.show(tr("state_listening"), "listening")
    for level in (0.30, 0.75, 0.45, 0.90, 0.35, 0.60, 0.20, 0.55):
        overlay.set_level(level)
        overlay._render()
        capture(90)

    # 2. transcribing — pulsing dots
    overlay.transcribing(tr("state_transcribing"))
    for phase in range(6):
        overlay._phase = phase
        overlay._render()
        capture(140)

    # 3. done — the text lands somewhere
    overlay.show("Remind me to call the client on Thursday.", "done")
    capture(1600)

    # 4. and it disappears, loop back to listening
    overlay.hide()
    capture(400)

    # One shared palette (dithered per-frame palettes shift colours and fuzz text)
    size = frames[0].size
    composites = []
    for f in frames:
        composites.append(
            Image.alpha_composite(Image.new("RGBA", size, BACKDROP + (255,)), f)
            .convert("RGB")
            .resize((size[0] * 2, size[1] * 2), Image.LANCZOS)
        )

    base = composites[0].quantize(colors=128, method=Image.MEDIANCUT)
    dither = getattr(Image, "Dither", Image).NONE
    quantized = [c.quantize(palette=base, dither=dither) for c in composites]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    quantized[0].save(
        OUT, save_all=True, append_images=quantized[1:],
        duration=durations, loop=0, disposal=2, optimize=True,
    )
    size_kb = os.path.getsize(OUT) / 1024
    print(f"wrote {OUT} ({len(frames)} frames, {size_kb:.0f} kB)")
    overlay.destroy()
    root.destroy()


if __name__ == "__main__":
    main()
