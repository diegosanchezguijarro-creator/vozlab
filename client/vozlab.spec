# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — builds the VozLab Windows app (one-dir, windowed).

    pyinstaller vozlab.spec --noconfirm
"""
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = [
    "pystray",
    "PIL.Image",
    "PIL.ImageDraw",
    "pyperclip",
    "sounddevice",
    "_sounddevice",
]

# CustomTkinter ships theme JSON files and needs its submodules/deps collected
datas = collect_data_files("customtkinter")
datas += [("assets/icon.ico", "assets"), ("assets/icon.png", "assets")]
hiddenimports += collect_submodules("customtkinter")
hiddenimports += collect_submodules("darkdetect")

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
    datas=datas,
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
