# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — builds the VozLab Windows app (one-dir, windowed).

    pyinstaller vozlab.spec --noconfirm
"""
import sys

hiddenimports = [
    "pystray",
    "PIL.Image",
    "PIL.ImageDraw",
    "pyperclip",
    "sounddevice",
    "_sounddevice",
]

# tray backends are platform-specific
if sys.platform.startswith("win"):
    hiddenimports += ["pystray._win32"]
elif sys.platform == "darwin":
    hiddenimports += ["pystray._darwin"]
else:
    hiddenimports += ["pystray._xorg", "pystray._appindicator"]

a = Analysis(
    ["run_vozlab.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets/icon.ico", "assets"),
        ("assets/icon.png", "assets"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "tests"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VozLab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # tray app: no console window
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="VozLab",
)
