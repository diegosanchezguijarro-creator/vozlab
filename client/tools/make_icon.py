#!/usr/bin/env python3
"""Generate the VozLab app icon (assets/icon.ico + icon.png).

    pip install pillow
    python tools/make_icon.py
"""

import os

from PIL import Image, ImageDraw

BG = (37, 99, 235)      # blue-600
FG = (255, 255, 255)
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def mic_icon(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=int(size * 0.22), fill=BG)

    cx, w = size / 2, size * 0.26
    top, bottom = size * 0.20, size * 0.55
    d.rounded_rectangle((cx - w / 2, top, cx + w / 2, bottom), radius=w / 2, fill=FG)
    d.arc((cx - size * 0.24, bottom - size * 0.26, cx + size * 0.24, bottom + size * 0.22),
          start=0, end=180, fill=FG, width=int(size * 0.055))
    d.line((cx, bottom + size * 0.20, cx, bottom + size * 0.30), fill=FG, width=int(size * 0.055))
    d.line((cx - size * 0.12, bottom + size * 0.30, cx + size * 0.12, bottom + size * 0.30),
           fill=FG, width=int(size * 0.055))
    return img


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    icon = mic_icon()
    ico_path = os.path.join(OUT_DIR, "icon.ico")
    icon.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.save(os.path.join(OUT_DIR, "icon.png"))
    print(f"wrote {ico_path} and icon.png")


if __name__ == "__main__":
    main()
